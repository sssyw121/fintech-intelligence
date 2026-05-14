# -*- coding: utf-8 -*-
"""
STEP 3: 텔레그램 리포트 발송
분석 JSON을 HTML로 포매팅해 링크·요약 포함 텔레그램 메시지를 발송한다.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

KST = ZoneInfo("Asia/Seoul")
PROJECT_ROOT = Path(__file__).parent.parent
RANK_EMOJI = {1: "①", 2: "②", 3: "③"}


def load_env() -> tuple[str, str]:
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        raise EnvironmentError("TELEGRAM_BOT_TOKEN 또는 TELEGRAM_CHAT_ID 미설정")
    return token, chat_id


def load_latest_analysis() -> dict:
    files = sorted((PROJECT_ROOT / "reports").glob("analysis_*.json"))
    if not files:
        raise FileNotFoundError("분석 파일 없음. analyst.py를 먼저 실행하세요.")
    return json.loads(files[-1].read_text(encoding="utf-8"))


def format_message(analysis: dict) -> str:
    period = analysis.get("period", {})
    start = period.get("start", "")
    end = period.get("end", "")
    weekly_summary = analysis.get("weekly_summary", "")
    issues = analysis.get("top_issues", [])
    analyzed_at = analysis.get("analyzed_at", "")[:16].replace("T", " ")

    lines = [
        "📊 <b>핀테크 인텔리전스 위클리</b>",
        f"<i>{start} ~ {end}</i>",
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "🗞 <b>이번 주 헤드라인</b>",
        weekly_summary,
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "🔥 <b>Top 3 이슈</b>",
    ]

    for issue in issues:
        rank = issue.get("rank", 0)
        title = issue.get("title", "")
        desc = issue.get("description", "")
        opp = issue.get("opportunity", "")
        article_url = issue.get("article_url", "")
        related = issue.get("related_articles", [])
        emoji = RANK_EMOJI.get(rank, str(rank))

        # 이슈 제목 (링크 포함)
        if article_url:
            title_line = f'<b>{emoji}. <a href="{article_url}">{title}</a></b>'
        else:
            title_line = f"<b>{emoji}. {title}</b>"

        risk_analysis = issue.get("risk_analysis", {})
        lines += ["", title_line, desc, f"💡 기회: {opp}"]

        # 5분류 리스크 분석
        if risk_analysis:
            RISK_LABELS = {
                "regulatory": "📋 규제", "competition": "⚔️ 경쟁",
                "technology": "🔧 기술", "user": "👤 사용자", "revenue": "💰 수익",
            }
            risk_lines = []
            for key, label in RISK_LABELS.items():
                val = risk_analysis.get(key, "")
                if val:
                    risk_lines.append(f"  {label}: {val}")
            if risk_lines:
                lines.append("⚠️ <b>리스크 분석</b>")
                lines.extend(risk_lines)
        elif issue.get("risk"):
            lines.append(f"⚠️ 리스크: {issue['risk']}")

        # 관련 기사 링크
        if related:
            rel_links = " | ".join(
                f'<a href="{r["url"]}">{r["title"][:25]}...</a>'
                for r in related[:2]
                if r.get("url") and r.get("title")
            )
            if rel_links:
                lines.append(f"📎 관련: {rel_links}")

        if rank < 3:
            lines.append("─────────────────────")

    # PM 한줄 코멘트
    lines += ["", "━━━━━━━━━━━━━━━━━━━━", "📌 <b>PM 한줄 코멘트</b>"]
    for issue in issues:
        rank = issue.get("rank", 0)
        comment = issue.get("one_line_comment", "")
        lines.append(f"{RANK_EMOJI.get(rank, rank)} {comment}")

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        f"<i>🤖 fintech-intelligence | {analyzed_at}</i>",
    ]

    return "\n".join(lines)


def send(token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    parts = _split(text)
    for i, part in enumerate(parts, 1):
        payload = json.dumps(
            {"chat_id": chat_id, "text": part, "parse_mode": "HTML",
             "disable_web_page_preview": True},
            ensure_ascii=False,
        ).encode("utf-8")
        r = requests.post(
            url, data=payload,
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=10,
        )
        r.raise_for_status()
        print(f"[reporter] 발송 완료 ({i}/{len(parts)})")


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


def run() -> None:
    token, chat_id = load_env()
    analysis = load_latest_analysis()
    msg = format_message(analysis)
    print(f"[reporter] 메시지 길이: {len(msg)}자")
    send(token, chat_id, msg)
    print("[reporter] 텔레그램 발송 완료")


if __name__ == "__main__":
    run()
