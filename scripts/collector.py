# -*- coding: utf-8 -*-
"""
STEP 1: 핀테크 뉴스 수집
1차: Playwright로 네이버 뉴스 검색 크롤링 (n.news.naver.com 링크 우선)
2차: Google News RSS 폴백
"""

import json
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

import feedparser
from bs4 import BeautifulSoup

KST = ZoneInfo("Asia/Seoul")
PROJECT_ROOT = Path(__file__).parent.parent

KEYWORDS = [
    "간편결제", "오픈뱅킹", "마이데이터", "BNPL",
    "토스 핀테크", "카카오페이", "네이버페이", "삼성페이",
    "핀테크 규제", "금융 AI",
]

def get_period() -> tuple[date, date]:
    today = date.today()
    days_since_monday = today.weekday() or 7
    last_monday = today - timedelta(days=days_since_monday)
    return last_monday, last_monday + timedelta(days=6)


# ── Playwright 기반 네이버 뉴스 크롤링 ────────────────────────────────────────

def fetch_naver_playwright(keyword: str, since: date, until: date, limit: int = 5) -> list[dict]:
    """
    Node.js Playwright로 네이버 뉴스 크롤링 (Python asyncio 이벤트 루프 충돌 우회).
    node.js가 없으면 빈 리스트 반환 → RSS 폴백 진행.
    """
    import subprocess, json as _json, shutil
    from pathlib import Path as _Path

    # node 실행파일 탐색 (winget 기본 설치 경로 포함)
    node = shutil.which("node")
    if not node:
        for candidate in [
            r"C:\Program Files\nodejs\node.exe",
            r"C:\Program Files (x86)\nodejs\node.exe",
        ]:
            if _Path(candidate).exists():
                node = candidate
                break
    if not node:
        return []

    crawler = Path(__file__).parent / "_naver_crawler.js"
    payload = _json.dumps({
        "keyword": keyword,
        "since": str(since),
        "until": str(until),
        "limit": limit,
    }, ensure_ascii=False)

    try:
        result = subprocess.run(
            [node, str(crawler)],
            input=payload,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=35,
            cwd=str(PROJECT_ROOT),
        )
        if result.returncode == 0 and result.stdout.strip():
            return _json.loads(result.stdout)
        if result.stderr:
            print(f"  [WARN] Playwright JS 오류 ({keyword}): {result.stderr[:200]}")
    except subprocess.TimeoutExpired:
        print(f"  [WARN] Playwright 타임아웃 ({keyword})")
    except Exception as e:
        print(f"  [WARN] Playwright 실행 실패 ({keyword}): {e}")

    return []


# ── Google News RSS 폴백 ──────────────────────────────────────────────────────

def extract_summary_text(raw_summary: str) -> str:
    if not raw_summary:
        return ""
    try:
        soup = BeautifulSoup(raw_summary, "lxml")
        return soup.get_text(" ", strip=True)[:400]
    except Exception:
        return raw_summary[:300]


def fetch_keyword_rss(keyword: str, since: date, until: date) -> list[dict]:
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
            content = extract_summary_text(entry.get("summary", ""))

            if title:
                articles.append({
                    "title": title,
                    "url": link,
                    "source": source,
                    "published_date": pub_str,
                    "keyword": keyword,
                    "content": content,
                    "summary": content,
                })
    except Exception as e:
        print(f"  [WARN] RSS 수집 실패 ({keyword}): {e}")
    return articles


# ── 메인 실행 ─────────────────────────────────────────────────────────────────

def run(output_path: Path | None = None) -> Path:
    since, until = get_period()
    print(f"[collector] 수집 기간: {since} ~ {until}")

    raw: list[dict] = []

    for kw in KEYWORDS:
        # 1차: Playwright 네이버 뉴스
        arts = fetch_naver_playwright(kw, since, until)
        src = "Naver"

        # 2차: RSS 폴백 (Playwright 결과 없으면)
        if not arts:
            arts = fetch_keyword_rss(kw, since, until)
            src = "RSS"

        print(f"  {kw}: {len(arts)}건 ({src})")
        raw.extend(arts)
        time.sleep(0.5)

    # 제목 앞 40자 기준 중복 제거
    seen_titles: set[str] = set()
    unique: list[dict] = []
    for a in raw:
        key = a["title"][:40]
        if key not in seen_titles:
            seen_titles.add(key)
            unique.append(a)

    print(f"\n[collector] 중복 제거 후 {len(unique)}건")
    for a in unique[:3]:
        print(f"  샘플: {a['title'][:40]} | content: {len(a.get('content',''))}자 | url: {a['url'][:50]}")

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
