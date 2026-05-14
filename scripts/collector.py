# -*- coding: utf-8 -*-
"""
STEP 1: 핀테크 뉴스 수집 + 기사 본문 추출
Google News RSS로 10개 키워드 기사를 수집하고, 각 기사의 실제 본문을 읽어 저장한다.
"""

import json
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

import feedparser
import requests
from bs4 import BeautifulSoup

KST = ZoneInfo("Asia/Seoul")
PROJECT_ROOT = Path(__file__).parent.parent

KEYWORDS = [
    "간편결제", "오픈뱅킹", "마이데이터", "BNPL",
    "토스 핀테크", "카카오페이", "네이버페이", "삼성페이",
    "핀테크 규제", "금융 AI",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def get_period() -> tuple[date, date]:
    today = date.today()
    days_since_monday = today.weekday() or 7
    last_monday = today - timedelta(days=days_since_monday)
    return last_monday, last_monday + timedelta(days=6)


def extract_summary_text(raw_summary: str) -> str:
    """RSS summary HTML에서 순수 텍스트 추출."""
    if not raw_summary:
        return ""
    try:
        soup = BeautifulSoup(raw_summary, "lxml")
        return soup.get_text(" ", strip=True)[:600]
    except Exception:
        return raw_summary[:300]


def fetch_naver_article(keyword: str, since: date, until: date) -> list[dict]:
    """네이버 뉴스 RSS (직접 기사 링크 제공)로 추가 수집."""
    url = f"https://news.naver.com/search/run.naver?query={quote(keyword)}&where=news"
    articles = []
    try:
        r = requests.get(
            f"https://rss.news.naver.com/rssSvc.nhn?oid=001",
            headers=HEADERS, timeout=6,
        )
    except Exception:
        pass
    return articles


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
                pub_str = str(pub_date)
            else:
                pub_str = str(until)

            title = entry.get("title", "").strip()
            link = entry.get("link", "")
            source = entry.get("source", {}).get("title", "")
            raw_summary = entry.get("summary", "")
            # RSS summary HTML → 텍스트 추출 (기사 첫 단락 포함)
            content = extract_summary_text(raw_summary)

            if title:
                articles.append({
                    "title": title,
                    "url": link,
                    "source": source,
                    "published_date": pub_str,
                    "keyword": keyword,
                    "summary": content,  # 텍스트로 정제된 요약
                    "content": content,  # analyst가 content 필드를 사용
                })
    except Exception as e:
        print(f"  [WARN] {keyword} RSS 수집 실패: {e}")
    return articles


def run(output_path: Path | None = None) -> Path:
    since, until = get_period()
    print(f"[collector] 수집 기간: {since} ~ {until}")

    # 1단계: RSS 수집
    raw: list[dict] = []
    for kw in KEYWORDS:
        arts = fetch_keyword(kw, since, until)
        print(f"  {kw}: {len(arts)}건")
        raw.extend(arts)
        time.sleep(0.3)

    # URL 기준 중복 제거
    seen_titles: set[str] = set()
    unique: list[dict] = []
    for a in raw:
        key = a["title"][:40]
        if key not in seen_titles:
            seen_titles.add(key)
            unique.append(a)

    print(f"\n[collector] 중복 제거 후 {len(unique)}건 (RSS summary 본문 포함)")
    for a in unique[:3]:
        print(f"  샘플: {a['title'][:40]} | content: {len(a.get('content',''))}자")

    out_dir = PROJECT_ROOT / "reports" / "collected"
    out_dir.mkdir(parents=True, exist_ok=True)
    if output_path is None:
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
    print(f"\n[collector] 완료: {output_path.name} ({len(unique)}건)")
    return output_path


if __name__ == "__main__":
    import os, sys
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    run()
