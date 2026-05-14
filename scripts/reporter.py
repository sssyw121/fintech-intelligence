# -*- coding: utf-8 -*-
"""
STEP 3: 텔레그램 리포트 발송
분석 JSON을 HTML 메시지로 포매팅해 텔레그램으로 발송한다.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

KST = ZoneInfo("Asia/Seoul")
PROJECT_ROOT = Path(__file__).parent.parent


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

    RANK_EMOJI = {1: "①", 2: "②", 3: "③"}

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
        risk = issue.get("risk", "")

        lines += [
            "",
            f"<b>{RANK_EMOJI.get(rank, rank)}. {title}</b>",
            desc,
            f"💡 기회: {opp}",
            f"⚠️ 리스크: {risk}",
        ]
        if rank < 3:
            lines.append("─────────────────────")

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "📌 <b>PM 한줄 코멘트</b>",
    ]
    for issue in issues:
        rank = issue.get("rank", 0)
        comment = issue.get("one_line_comment", "")
        lines.append(f"{RANK_EMOJI.get(rank, rank)} {comment}")

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        f"<i>🤖 fintech-intelligence | 분석 시각: {analyzed_at}</i>",
    ]

    return "\n".join(lines)


def send(token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    parts = _split(text)
    for i, part in enumerate(parts, 1):
        payload = json.dumps(
            {"chat_id": chat_id, "text": part, "parse_mode": "HTML"},
            ensure_ascii=False,
        ).encode("utf-8")
        r = requests.post(
            url,
            data=payload,
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
        if idx == -1:
            idx = limit
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
