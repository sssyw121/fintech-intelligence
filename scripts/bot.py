# -*- coding: utf-8 -*-
"""
fintech-intelligence 텔레그램 양방향 봇
폴링 방식으로 사용자 명령을 수신하고 응답합니다.

실행:
  python -X utf8 scripts/bot.py

지원 명령어:
  /report  - 즉시 파이프라인 실행 후 리포트 발송
  /status  - 마지막 리포트 시각, 다음 예정 시각, 수집 파일 현황
  /help    - 명령어 안내
  자유 텍스트 - 수집된 뉴스 데이터 기반 질문 응답
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).parent.parent
KST = ZoneInfo("Asia/Seoul")
OFFSET_FILE = PROJECT_ROOT / "scripts" / ".bot_offset"
LOCK_FILE = PROJECT_ROOT / "scripts" / ".bot_lock"


def log(msg: str) -> None:
    try:
        print(f"[{datetime.now(KST).strftime('%H:%M:%S')}] {msg}", flush=True)
    except Exception:
        pass


try:
    import requests
except ImportError:
    log("[ERROR] requests 없음. pip install requests")
    sys.exit(1)


# ── 단일 인스턴스 보장 ────────────────────────────────────────────────────────

def acquire_lock() -> bool:
    if LOCK_FILE.exists():
        try:
            pid = int(LOCK_FILE.read_text().strip())
            # 해당 PID 프로세스가 살아있으면 중복 실행 거부
            import psutil
            if psutil.pid_exists(pid):
                return False
        except Exception:
            pass
    LOCK_FILE.write_text(str(os.getpid()))
    return True


def release_lock() -> None:
    try:
        LOCK_FILE.unlink(missing_ok=True)
    except Exception:
        pass


# ── 환경변수 로드 ─────────────────────────────────────────────────────────────

def load_env() -> tuple[str, str]:
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        with open(env_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    if not token or not chat_id:
        log("[ERROR] TELEGRAM_BOT_TOKEN 또는 TELEGRAM_CHAT_ID 미설정")
        sys.exit(1)

    return token, chat_id


# ── offset 영속화 (재시작 시 이전 메시지 재처리 방지) ─────────────────────────

def load_offset() -> int:
    try:
        return int(OFFSET_FILE.read_text().strip())
    except Exception:
        return 0


def save_offset(offset: int) -> None:
    try:
        OFFSET_FILE.write_text(str(offset))
    except Exception:
        pass


# ── 텔레그램 API 유틸 ─────────────────────────────────────────────────────────

def send_message(token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    for part in _split(text):
        payload = json.dumps(
            {"chat_id": chat_id, "text": part, "parse_mode": "HTML"},
            ensure_ascii=False,
        ).encode("utf-8")
        try:
            r = requests.post(
                url,
                data=payload,
                headers={"Content-Type": "application/json; charset=utf-8"},
                timeout=10,
            )
            r.raise_for_status()
        except requests.RequestException as e:
            log(f"[ERROR] 발송 실패: {e}")


def _split(text: str, limit: int = 4096) -> list[str]:
    if len(text) <= limit:
        return [text]
    parts = []
    while text:
        if len(text) <= limit:
            parts.append(text)
            break
        idx = text.rfind("\n", 0, limit)
        if idx == -1:
            idx = limit
        parts.append(text[:idx])
        text = text[idx:].lstrip("\n")
    return parts


def get_updates(token: str, offset: int) -> list[dict]:
    try:
        r = requests.get(
            f"https://api.telegram.org/bot{token}/getUpdates",
            params={"offset": offset, "timeout": 30},
            timeout=40,
        )
        r.raise_for_status()
        return r.json().get("result", [])
    except requests.RequestException:
        return []


# ── 명령어 핸들러 ─────────────────────────────────────────────────────────────

def handle_help(token: str, chat_id: str) -> None:
    send_message(token, chat_id,
        "📋 <b>fintech-intelligence 봇 명령어</b>\n"
        "──────────────────────\n\n"
        "/report - 즉시 핀테크 리포트 생성 및 발송\n"
        "/status - 시스템 상태 및 파일 현황 조회\n"
        "/help   - 이 안내 메시지\n\n"
        "💬 <b>자유 질문</b>\n"
        "텍스트를 입력하면 수집된 뉴스 데이터 기반으로 답변합니다.\n"
        "예) <i>이번 주 카카오페이 관련 동향 알려줘</i>"
    )


def handle_status(token: str, chat_id: str) -> None:
    lines = ["📊 <b>시스템 상태</b>\n──────────────────────\n"]

    collected_dir = PROJECT_ROOT / "reports" / "collected"
    collected_files = sorted(collected_dir.glob("collected_*.json")) if collected_dir.exists() else []
    if collected_files:
        latest = collected_files[-1]
        mtime = datetime.fromtimestamp(latest.stat().st_mtime, tz=KST).strftime("%Y-%m-%d %H:%M")
        lines.append(f"📥 <b>최근 수집</b>: {latest.name}\n   저장 시각: {mtime}")
    else:
        lines.append("📥 <b>최근 수집</b>: 없음 (아직 실행 안 됨)")

    analysis_files = sorted((PROJECT_ROOT / "reports").glob("analysis_*.json"))
    if analysis_files:
        latest_a = analysis_files[-1]
        mtime_a = datetime.fromtimestamp(latest_a.stat().st_mtime, tz=KST).strftime("%Y-%m-%d %H:%M")
        lines.append(f"\n📈 <b>최근 분석</b>: {latest_a.name}\n   저장 시각: {mtime_a}")
    else:
        lines.append("\n📈 <b>최근 분석</b>: 없음")

    now = datetime.now(KST)
    days_until_monday = (7 - now.weekday()) % 7 or 7
    next_run = (now + timedelta(days=days_until_monday)).replace(hour=9, minute=0, second=0, microsecond=0)
    lines.append(f"\n⏰ <b>다음 자동 발송</b>: {next_run.strftime('%Y-%m-%d (월) 09:00 KST')}")
    lines.append(f"\n🕐 <b>현재 시각</b>: {now.strftime('%Y-%m-%d %H:%M KST')}")

    send_message(token, chat_id, "\n".join(lines))


def handle_report(token: str, chat_id: str) -> None:
    send_message(token, chat_id, "⏳ 리포트 생성 중입니다. 잠시만 기다려주세요...")
    try:
        result = subprocess.run(
            [sys.executable, "-X", "utf8",
             str(PROJECT_ROOT / "scripts" / "scheduler.py"), "--run-now"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
            cwd=str(PROJECT_ROOT),
        )
        if result.returncode == 0:
            send_message(token, chat_id, "✅ 파이프라인 실행 완료! 리포트가 발송됩니다.")
        else:
            err = (result.stderr or result.stdout or "알 수 없는 오류")[:500]
            send_message(token, chat_id, f"❌ 파이프라인 오류:\n<code>{err}</code>")
    except subprocess.TimeoutExpired:
        send_message(token, chat_id, "❌ 시간 초과 (5분).")
    except Exception as e:
        send_message(token, chat_id, f"❌ 오류: {e}")


def handle_free_text(token: str, chat_id: str, question: str) -> None:
    send_message(token, chat_id, f"🔍 <b>{question}</b> 검색 중...")

    try:
        import feedparser
        from urllib.parse import quote

        feed = feedparser.parse(
            f"https://news.google.com/rss/search?q={quote(question)}&hl=ko&gl=KR&ceid=KR:ko"
        )
        entries = feed.entries[:5]
    except Exception:
        entries = []

    lines = [f"💬 <b>질문</b>: {question}\n"]

    # 로컬 분석 데이터가 있으면 우선 참조
    analysis_files = sorted((PROJECT_ROOT / "reports").glob("analysis_*.json"))
    if analysis_files:
        with open(analysis_files[-1], encoding="utf-8") as f:
            analysis = json.load(f)
        q_lower = question.lower()
        matched = [
            issue for issue in analysis.get("top_issues", [])
            if any(kw in q_lower for kw in (issue["title"] + issue.get("description", "")).lower().split())
        ] or analysis.get("top_issues", [])

        if matched:
            lines.append("📌 <b>주간 리포트 인사이트</b>")
            for issue in matched[:2]:
                lines.append(
                    f"\n<b>{issue['rank']}. {issue['title']}</b>\n"
                    f"{issue['description']}\n"
                    f"💡 기회: {issue['opportunity']}\n"
                    f"⚠️ 리스크: {issue['risk']}\n"
                    f"→ {issue['one_line_comment']}"
                )
            lines.append("")

    # 실시간 웹 검색 결과 추가
    if entries:
        lines.append("📰 <b>실시간 관련 뉴스</b>")
        for e in entries:
            title = e.get("title", "")
            link = e.get("link", "")
            source = e.get("source", {}).get("title", "")
            pub = e.get("published", "")[:10] if e.get("published") else ""
            lines.append(f'\n- <a href="{link}">{title}</a>')
            if source or pub:
                lines.append(f"  <i>{source} {pub}</i>")
    else:
        if not analysis_files:
            lines.append("📭 검색 결과가 없습니다. /report 명령으로 리포트를 먼저 생성해주세요.")

    send_message(token, chat_id, "\n".join(lines))


# ── 메인 폴링 루프 ────────────────────────────────────────────────────────────

def main() -> None:
    # 중복 실행 방지 (psutil 없으면 스킵)
    try:
        if not acquire_lock():
            log("[ERROR] 봇이 이미 실행 중입니다. 중복 실행 종료.")
            sys.exit(1)
    except Exception:
        pass

    token, chat_id = load_env()

    log(f"봇 시작 (폴링 모드) | Chat ID: {chat_id}")

    send_message(token, chat_id,
        "🤖 <b>fintech-intelligence 봇이 시작되었습니다.</b>\n"
        "/help 로 사용 가능한 명령어를 확인하세요."
    )

    # 파일에서 offset 복원 (재시작 시 이전 메시지 재처리 방지)
    offset = load_offset()
    # 이미 처리한 update_id 세트 (세션 내 중복 방지)
    seen_ids: set[int] = set()

    try:
        while True:
            updates = get_updates(token, offset)

            for update in updates:
                uid = update["update_id"]

                # offset 갱신 (항상)
                if uid >= offset:
                    offset = uid + 1
                    save_offset(offset)

                # 중복 처리 방지
                if uid in seen_ids:
                    continue
                seen_ids.add(uid)

                message = update.get("message", {})
                user_chat_id = str(message.get("chat", {}).get("id", ""))
                text = message.get("text", "").strip()

                if not text:
                    continue

                if user_chat_id != chat_id:
                    log(f"[무시] 미등록 Chat ID: {user_chat_id}")
                    continue

                log(f"[수신] {text}")

                if text.startswith("/report"):
                    handle_report(token, chat_id)
                elif text.startswith("/status"):
                    handle_status(token, chat_id)
                elif text.startswith("/help") or text.startswith("/start"):
                    handle_help(token, chat_id)
                else:
                    handle_free_text(token, chat_id, text)

            time.sleep(1)

    finally:
        release_lock()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("봇 종료")
        release_lock()
