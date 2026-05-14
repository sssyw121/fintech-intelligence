# -*- coding: utf-8 -*-
"""
STEP 1: 핀테크 뉴스 수집
Google News RSS로 10개 키워드의 직전 주 기사를 수집해 JSON으로 저장한다.
"""

import json
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from urllib.parse import quote

import feedparser
import requests

KST = ZoneInfo("Asia/Seoul")
PROJECT_ROOT = Path(__file__).parent.parent

KEYWORDS = [
    "간편결제",
    "오픈뱅킹",
    "마이데이터",
    "BNPL",
    "토스 핀테크",
    "카카오페이",
    "네이버페이",
    "삼성페이",
    "핀테크 규제",
    "금융 AI",
]


def get_period() -> tuple[date, date]:
    today = date.today()
    days_since_monday = today.weekday() or 7
    last_monday = today - timedelta(days=days_since_monday)
    last_sunday = last_monday + timedelta(days=6)
    return last_monday, last_sunday


def fetch_keyword(keyword: str, since: date, until: date) -> list[dict]:
    url = (
        f"https://news.google.com/rss/search"
        f"?q={quote(keyword)}&hl=ko&gl=KR&ceid=KR:ko"
    )
    articles = []
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries[:8]:
            pub = entry.get("published_parsed")
            if pub:
                pub_date = date(pub.tm_year, pub.tm_mon, pub.tm_mday)
                if not (since <= pub_date <= until):
                    continue
                pub_str = f"{pub_date}"
            else:
                pub_str = str(until)

            title = entry.get("title", "").strip()
            link = entry.get("link", "")
            source = entry.get("source", {}).get("title", "")
            summary = entry.get("summary", "")[:200].strip()

            if title:
                articles.append({
                    "title": title,
                    "url": link,
                    "source": source,
                    "published_date": pub_str,
                    "keyword": keyword,
                    "summary": summary,
                })
    except Exception as e:
        print(f"[WARN] {keyword} 수집 실패: {e}")
    return articles


def run(output_path: Path | None = None) -> Path:
    since, until = get_period()
    print(f"[collector] 수집 기간: {since} ~ {until}")

    all_articles = []
    for kw in KEYWORDS:
        arts = fetch_keyword(kw, since, until)
        print(f"  {kw}: {len(arts)}건")
        all_articles.extend(arts)
        time.sleep(0.5)

    # 중복 URL 제거
    seen = set()
    unique = []
    for a in all_articles:
        if a["url"] not in seen:
            seen.add(a["url"])
            unique.append(a)

    if output_path is None:
        out_dir = PROJECT_ROOT / "reports" / "collected"
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = out_dir / f"collected_{since.strftime('%Y%m%d')}_{until.strftime('%Y%m%d')}.json"

    result = {
        "collected_at": datetime.now(KST).isoformat(),
        "period": {"start": str(since), "end": str(until)},
        "total_articles": len(unique),
        "articles": unique,
    }
    if len(unique) < 5:
        result["warning"] = "수집된 기사 수가 부족합니다."

    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[collector] 저장 완료: {output_path.name} ({len(unique)}건)")
    return output_path


if __name__ == "__main__":
    run()
