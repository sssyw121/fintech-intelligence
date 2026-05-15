# -*- coding: utf-8 -*-
"""
STEP 3: 텔레그램 브리핑 발송
분석 JSON을 PM 브리핑 형식(헤더 → 지표 → Top3 카드 → 종합 코멘트 → 푸터)으로
포매팅해 텔레그램으로 분할 발송한다.
"""

import json
import os
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

KST = ZoneInfo("Asia/Seoul")
PROJECT_ROOT = Path(__file__).parent.parent

RANK_BADGE  = {1: "①", 2: "②", 3: "③"}
PERSPECTIVE = {
    "competition": "[경쟁 구도]",
    "regulation":  "[규제 리스크]",
    "ux_trend":    "[UX 트렌드]",
}
RISK_LABELS = {
    "regulatory": "📋 규제",
    "competition": "⚔️ 경쟁",
    "technology":  "🔧 기술",
    "user":        "👤 사용자",
    "revenue":     "💰 수익",
}


# ── 환경변수·파일 로드 ────────────────────────────────────────────────────────

def load_env() -> tuple[str, str]:
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    token   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        raise EnvironmentError("TELEGRAM_BOT_TOKEN 또는 TELEGRAM_CHAT_ID 미설정")
    return token, chat_id


def load_latest_analysis() -> dict:
    files = sorted((PROJECT_ROOT / "reports").glob("analysis_*.json"))
    if not files:
        raise FileNotFoundError("분석 파일 없음. analyst.py를 먼저 실행하세요.")
    return json.loads(files[-1].read_text(encoding="utf-8"))


# ── 날짜 포매터 ───────────────────────────────────────────────────────────────

def _fmt_date(iso: str) -> str:
    """'2026-05-11' → '2026.05.11'"""
    return iso.replace("-", ".")


def _next_monday(ref: str) -> str:
    """ref(YYYY-MM-DD) 기준 다음 월요일"""
    d = date.fromisoformat(ref)
    days_ahead = (7 - d.weekday()) % 7 or 7
    return (d + timedelta(days=days_ahead)).strftime("%Y-%m-%d")


# ── 이슈 카드 포매터 ──────────────────────────────────────────────────────────

def _format_issue_card(issue: dict) -> str:
    rank        = issue.get("rank", 0)
    title       = issue.get("title", "")
    desc        = issue.get("description", "")
    opp         = issue.get("opportunity", "")
    comment     = issue.get("one_line_comment", "")
    article_url = issue.get("article_url", "")
    risk_analysis = issue.get("risk_analysis", {})

    badge    = RANK_BADGE.get(rank, str(rank))
    cat_tag  = PERSPECTIVE.get(issue.get("perspective", ""), "")

    lines = []

    # ① 번호 배지 + 카테고리 태그
    lines.append(f"<b>{badge} {cat_tag}</b>")

    # ② 이슈 제목
    if article_url:
        lines.append(f'<b><a href="{article_url}">{title}</a></b>')
    else:
        lines.append(f"<b>{title}</b>")

    lines.append("")

    # ③ 무슨 일이 있었나
    lines.append("📰 <b>무슨 일이 있었나</b>")
    lines.append(desc)
    if article_url:
        lines.append(f'📎 <a href="{article_url}">원문 보기</a>')

    lines.append("")

    # ④ PM 관점 의미 — description에서 전략적 의미 추출 (단기/중장기 구분)
    lines.append("🎯 <b>PM 관점 의미</b>")
    desc_sentences = [s.strip() for s in desc.replace("。", ".").split(".") if len(s.strip()) > 10]
    if len(desc_sentences) >= 2:
        lines.append(f"<i>단기:</i> {desc_sentences[0]}.")
        mid = ". ".join(desc_sentences[1:])
        lines.append(f"<i>중장기:</i> {mid}.")
    else:
        lines.append(desc)

    lines.append("")

    # ⑤ 기회 / 리스크
    lines.append("⚡ <b>기회 / 리스크</b>")
    lines.append(f"💡 기회: {opp}")

    # risk_analysis 5분류에서 핵심 2~3가지 선별 (값이 있는 항목 우선)
    risk_items = [
        (label, risk_analysis[key])
        for key, label in RISK_LABELS.items()
        if risk_analysis.get(key) and "제한적" not in risk_analysis[key]
    ]
    # 상위 3개만 표시
    for label, val in risk_items[:3]:
        lines.append(f"⚠️ {label} 리스크: {val}")
    # 모두 제한적이면 전부 표시
    if not risk_items:
        for key, label in RISK_LABELS.items():
            val = risk_analysis.get(key, "")
            if val:
                lines.append(f"⚠️ {label}: {val}")
                break

    lines.append("")

    # ⑥ 이번 주 액션 아이템
    lines.append("✅ <b>이번 주 액션 아이템</b>")
    lines.append(comment)

    return "\n".join(lines)


# ── 전체 메시지 포매터 ────────────────────────────────────────────────────────

def format_message(analysis: dict) -> str:
    period       = analysis.get("period", {})
    start        = period.get("start", "")
    end          = period.get("end", "")
    weekly_sum   = analysis.get("weekly_summary", "")
    issues       = analysis.get("top_issues", [])
    analyzed_at  = analysis.get("analyzed_at", "")[:16].replace("T", " ")
    source_file  = analysis.get("source_file", "")
    total_articles = _parse_total_articles(source_file, PROJECT_ROOT)
    action_count = len(issues)
    next_pub     = _next_monday(end) if end else ""

    # ── 헤더 ─────────────────────────────────────────────
    parts = []
    header = "\n".join([
        f"📅 <b>{_fmt_date(start)} — {_fmt_date(end)}</b>",
        "📊 <b>핀테크 PM 주간 인텔리전스</b>",
        f"💡 {weekly_sum}",
    ])
    parts.append(header)

    # ── 요약 지표 ─────────────────────────────────────────
    indicator = (
        f"📦 수집 기사 <b>{total_articles}건</b>  |  "
        f"🔥 주요 이슈 <b>3건</b>  |  "
        f"✅ 액션 아이템 <b>{action_count}개</b>"
    )
    parts.append(indicator)

    # ── TOP 3 이슈 카드 ────────────────────────────────────
    parts.append("━━━━━━━━━━━━━━━━━━━━\n🔥 <b>TOP 3 이슈</b>")
    for i, issue in enumerate(issues):
        card = _format_issue_card(issue)
        parts.append(card)
        if i < len(issues) - 1:
            parts.append("━━━━━━━━━━━━━━━━━━━━")

    # ── PM 종합 코멘트 ─────────────────────────────────────
    parts.append("━━━━━━━━━━━━━━━━━━━━")
    parts.append("📌 <b>PM 종합 코멘트</b>")
    overall = _build_overall_comment(issues, weekly_sum)
    parts.append(overall)

    # ── 푸터 ─────────────────────────────────────────────
    parts.append("━━━━━━━━━━━━━━━━━━━━")
    next_pub_str = f"{_fmt_date(next_pub)}(월) 09:00" if next_pub else "매주 월요일 09:00"
    footer = "\n".join([
        f"<i>📌 수집 기사 {total_articles}건 · 분석 시각 {analyzed_at} · 다음 발행 {next_pub_str}</i>",
        "<i>🤖 fintech-intelligence</i>",
    ])
    parts.append(footer)

    return "\n\n".join(parts)


def _parse_total_articles(source_file: str, root: Path) -> int:
    """수집 파일에서 기사 총 수 추출."""
    try:
        collected_dir = root / "reports" / "collected"
        path = collected_dir / source_file
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return data.get("total_articles", 0)
    except Exception:
        pass
    return 0


def _build_overall_comment(issues: list[dict], weekly_sum: str) -> str:
    """Top 3 이슈를 관통하는 종합 코멘트 생성."""
    perspectives = [PERSPECTIVE.get(i.get("perspective", ""), "") for i in issues]
    titles   = [i.get("title", "") for i in issues]
    comments = [i.get("one_line_comment", "") for i in issues]

    perspective_str = " · ".join(p.strip("[]") for p in perspectives if p)

    # 액션 동사구만 추출 (불필요한 조사 연결 방지)
    def _action(c: str) -> str:
        return c.replace("PM이라면 ", "").rstrip(".")

    action1 = _action(comments[0]) if comments else ""
    action_last = _action(comments[-1]) if len(comments) > 1 else ""

    title1 = titles[0][:25] if titles else ""
    title2 = titles[1][:25] if len(titles) > 1 else ""
    title_str = f"'{title1}', '{title2}'" if title2 else f"'{title1}'"

    def _clean(c: str) -> str:
        return c.replace("PM이라면 ", "").rstrip(".")

    c1 = _clean(comments[0]) if comments else ""
    c2 = _clean(comments[-1]) if len(comments) > 1 else ""

    para = (
        f"이번 주 핀테크 시장은 <b>{perspective_str}</b> 세 축이 동시에 움직인 주였습니다. "
        f"{title_str} 등 굵직한 이슈가 맞물리며 시장 전반의 긴장감이 높아졌습니다. "
        f"지금 이 시점에 PM이라면 두 가지를 챙겨야 합니다. "
        f"첫째, {c1}. "
        f"둘째, {c2}."
    )
    return para


# ── 텔레그램 발송 ─────────────────────────────────────────────────────────────

def send(token: str, chat_id: str, text: str) -> None:
    url   = f"https://api.telegram.org/bot{token}/sendMessage"
    parts = _split(text)
    for i, part in enumerate(parts, 1):
        payload = json.dumps(
            {"chat_id": chat_id, "text": part,
             "parse_mode": "HTML", "disable_web_page_preview": True},
            ensure_ascii=False,
        ).encode("utf-8")
        r = requests.post(
            url, data=payload,
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=10,
        )
        r.raise_for_status()
        print(f"[reporter] 발송 완료 ({i}/{len(parts)}) — {len(part)}자")
        if i < len(parts):
            time.sleep(0.5)


def _split(text: str, limit: int = 4096) -> list[str]:
    if len(text) <= limit:
        return [text]
    parts = []
    while text:
        if len(text) <= limit:
            parts.append(text)
            break
        idx = text.rfind("\n", 0, limit)
        idx = idx if idx != -1 else limit
        parts.append(text[:idx])
        text = text[idx:].lstrip("\n")
    return parts


# ── 메인 ──────────────────────────────────────────────────────────────────────

def run() -> None:
    token, chat_id = load_env()
    analysis = load_latest_analysis()
    msg = format_message(analysis)
    print(f"[reporter] 메시지 길이: {len(msg)}자")
    send(token, chat_id, msg)
    print("[reporter] 텔레그램 발송 완료")


if __name__ == "__main__":
    run()
