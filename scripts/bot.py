"""
fintech-intelligence 텔레그램 양방향 봇
폴링 방식으로 사용자 명령을 수신하고 응답합니다.

실행:
  python scripts/bot.py

지원 명령어:
  /report  — 즉시 파이프라인 실행 후 리포트 발송
  /status  — 마지막 리포트 시각, 다음 예정 시각, 수집 파일 현황
  /help    — 명령어 안내
  자유 텍스트 — 수집된 뉴스 데이터 기반 질문 응답
"""

import json
import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

KST = ZoneInfo("Asia/Seoul")

try:
    import requests
except ImportError:
    print("[ERROR] requests 모듈이 없습니다. 설치: pip install requests")
    sys.exit(1)


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
        print("[ERROR] TELEGRAM_BOT_TOKEN 또는 TELEGRAM_CHAT_ID가 설정되지 않았습니다.")
        sys.exit(1)

    return token, chat_id


# ── 텔레그램 API 유틸 ─────────────────────────────────────────────────────────

def send_message(token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    parts = _split(text)
    for part in parts:
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
            print(f"[ERROR] 메시지 발송 실패: {e}")


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
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    try:
        r = requests.get(
            url,
            params={"offset": offset, "timeout": 30},
            timeout=40,
        )
        r.raise_for_status()
        return r.json().get("result", [])
    except requests.RequestException:
        return []


# ── 명령어 핸들러 ─────────────────────────────────────────────────────────────

def handle_help(token: str, chat_id: str) -> None:
    text = (
        "📋 <b>fintech-intelligence 봇 명령어</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "/report — 지금 즉시 핀테크 리포트 생성 및 발송\n"
        "/status — 시스템 상태 및 파일 현황 조회\n"
        "/help   — 이 안내 메시지\n\n"
        "💬 <b>자유 질문</b>\n"
        "명령어 없이 텍스트를 입력하면 수집된 뉴스 데이터를 기반으로 답변합니다.\n"
        "예) <i>이번 주 카카오페이 관련 동향 알려줘</i>\n"
        "예) <i>BNPL 규제 리스크 정리해줘</i>"
    )
    send_message(token, chat_id, text)


def handle_status(token: str, chat_id: str) -> None:
    lines = ["📊 <b>시스템 상태</b>\n━━━━━━━━━━━━━━━━━━━━\n"]

    # 수집 파일 현황
    collected_dir = PROJECT_ROOT / "reports" / "collected"
    collected_files = sorted(collected_dir.glob("collected_*.json")) if collected_dir.exists() else []
    if collected_files:
        latest = collected_files[-1]
        stat = latest.stat()
        mtime = datetime.fromtimestamp(stat.st_mtime, tz=KST).strftime("%Y-%m-%d %H:%M")
        lines.append(f"📥 <b>최근 수집</b>: {latest.name}\n   저장 시각: {mtime}")
    else:
        lines.append("📥 <b>최근 수집</b>: 없음 (아직 실행 안 됨)")

    # 분석 파일 현황
    analysis_files = sorted((PROJECT_ROOT / "reports").glob("analysis_*.json"))
    if analysis_files:
        latest_a = analysis_files[-1]
        mtime_a = datetime.fromtimestamp(latest_a.stat().st_mtime, tz=KST).strftime("%Y-%m-%d %H:%M")
        lines.append(f"\n📈 <b>최근 분석</b>: {latest_a.name}\n   저장 시각: {mtime_a}")
    else:
        lines.append("\n📈 <b>최근 분석</b>: 없음")

    # 다음 예정 시각 계산
    now = datetime.now(KST)
    days_until_monday = (7 - now.weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7
    next_run = (now + timedelta(days=days_until_monday)).replace(
        hour=9, minute=0, second=0, microsecond=0
    )
    lines.append(f"\n⏰ <b>다음 자동 발송</b>: {next_run.strftime('%Y-%m-%d (월) 09:00 KST')}")
    lines.append(f"\n🕐 <b>현재 시각</b>: {now.strftime('%Y-%m-%d %H:%M KST')}")

    send_message(token, chat_id, "\n".join(lines))


def handle_report(token: str, chat_id: str) -> None:
    send_message(token, chat_id, "⏳ 리포트 생성 중입니다. 잠시만 기다려주세요...")
    try:
        from scheduler import run_pipeline
        success = run_pipeline()
        if not success:
            send_message(token, chat_id, "❌ 파이프라인 실행 중 오류가 발생했습니다.\n로그를 확인해주세요.")
    except Exception as e:
        send_message(token, chat_id, f"❌ 오류: {e}")


def handle_free_text(token: str, chat_id: str, question: str) -> None:
    # 수집된 최근 데이터를 로드하여 컨텍스트로 제공
    context_lines = []

    collected_files = sorted(
        (PROJECT_ROOT / "reports" / "collected").glob("collected_*.json")
    ) if (PROJECT_ROOT / "reports" / "collected").exists() else []

    analysis_files = sorted((PROJECT_ROOT / "reports").glob("analysis_*.json"))

    if analysis_files:
        with open(analysis_files[-1], encoding="utf-8") as f:
            analysis = json.load(f)
        context_lines.append(f"[분석 데이터 - {analysis.get('period', {}).get('start', '')} ~ {analysis.get('period', {}).get('end', '')}]")
        context_lines.append(f"주간 요약: {analysis.get('weekly_summary', '')}")
        for issue in analysis.get("top_issues", []):
            context_lines.append(
                f"이슈{issue['rank']}: {issue['title']} | 기회: {issue['opportunity']} | 리스크: {issue['risk']}"
            )

    if not context_lines:
        send_message(
            token, chat_id,
            "📭 아직 수집된 데이터가 없습니다.\n/report 명령으로 먼저 리포트를 생성해주세요."
        )
        return

    context = "\n".join(context_lines)
    question_lower = question.lower()

    # 키워드 기반 간단 응답 (Claude API 키 없는 환경용)
    response_lines = [f"💬 <b>질문</b>: {question}\n"]

    # 관련 이슈 필터링
    keywords = ["카카오", "토스", "네이버", "삼성", "bnpl", "오픈뱅킹", "마이데이터", "규제", "ai", "ux"]
    matched_issues = []

    if analysis_files:
        for issue in analysis.get("top_issues", []):
            issue_text = (issue["title"] + issue["description"] + issue.get("opportunity", "") + issue.get("risk", "")).lower()
            if any(kw in question_lower for kw in keywords if kw in issue_text) or \
               any(kw in question_lower for kw in [w.lower() for w in issue["title"].split()]):
                matched_issues.append(issue)

        if not matched_issues:
            matched_issues = analysis.get("top_issues", [])

    if matched_issues:
        response_lines.append("📌 <b>관련 인사이트</b>")
        for issue in matched_issues[:2]:
            response_lines.append(
                f"\n<b>{issue['rank']}. {issue['title']}</b>\n"
                f"{issue['description']}\n"
                f"💡 기회: {issue['opportunity']}\n"
                f"⚠️ 리스크: {issue['risk']}\n"
                f"→ {issue['one_line_comment']}"
            )
    else:
        response_lines.append(f"수집된 데이터 요약:\n{context}")

    response_lines.append(
        "\n\n<i>💡 더 정확한 AI 분석을 원하시면 ANTHROPIC_API_KEY를 .env에 추가하세요.</i>"
    )

    send_message(token, chat_id, "\n".join(response_lines))


# ── 메인 폴링 루프 ────────────────────────────────────────────────────────────

def main() -> None:
    token, chat_id = load_env()

    print(f"[{datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')} KST] 봇 시작 (폴링 모드)")
    print(f"  봇: @lians_ai_bot | Chat ID: {chat_id}")
    print("  Ctrl+C로 종료\n")

    send_message(token, chat_id,
        "🤖 <b>fintech-intelligence 봇이 시작되었습니다.</b>\n"
        "/help 로 사용 가능한 명령어를 확인하세요."
    )

    offset = 0

    while True:
        updates = get_updates(token, offset)

        for update in updates:
            offset = update["update_id"] + 1
            message = update.get("message", {})
            user_chat_id = str(message.get("chat", {}).get("id", ""))
            text = message.get("text", "").strip()

            if not text:
                continue

            # 등록된 Chat ID만 응답
            if user_chat_id != chat_id:
                print(f"[무시] 미등록 Chat ID: {user_chat_id}")
                continue

            print(f"[수신] {text}")

            if text.startswith("/report"):
                handle_report(token, chat_id)
            elif text.startswith("/status"):
                handle_status(token, chat_id)
            elif text.startswith("/help") or text.startswith("/start"):
                handle_help(token, chat_id)
            else:
                handle_free_text(token, chat_id, text)

        time.sleep(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[종료] 봇을 종료합니다.")
