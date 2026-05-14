# -*- coding: utf-8 -*-
"""
네이버 뉴스 크롤러 (Playwright async) — subprocess로 호출됨.
stdin: JSON {"keyword": str, "since": "YYYY-MM-DD", "until": "YYYY-MM-DD", "limit": int}
stdout: JSON list of article dicts
"""

import asyncio
import json
import re
import sys
from urllib.parse import quote


async def crawl(keyword: str, since: str, until: str, limit: int = 5) -> list[dict]:
    from playwright.async_api import async_playwright

    ds = since.replace("-", ".")
    de = until.replace("-", ".")
    url = (
        f"https://search.naver.com/search.naver"
        f"?where=news&query={quote(keyword)}&sm=tab_opt&sort=1&pd=3&ds={ds}&de={de}"
    )

    articles = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="ko-KR",
        )
        await page.goto(url, timeout=20000, wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)

        # 기사 목록 컨테이너: ul.list_news > li
        items = await page.query_selector_all("ul.list_news li.bx")
        if not items:
            items = await page.query_selector_all("ul.list_news li")
        if not items:
            items = await page.query_selector_all(".group_news li")

        for item in items[:limit]:
            # 제목: 기사 원본 링크 (news_tit 클래스) 또는 첫 번째 외부 a 태그
            title = ""
            title_url = ""
            naver_url = ""

            # 1. 제목 링크 (원본 기사)
            title_el = await item.query_selector("a.news_tit")
            if not title_el:
                # 대안 선택자
                title_el = await item.query_selector("a[class*='tit']")
            if title_el:
                title = (await title_el.inner_text()).strip()
                title_url = (await title_el.get_attribute("href")) or ""

            # 2. 네이버 뉴스 링크 (n.news.naver.com)
            naver_el = await item.query_selector("a[href*='n.news.naver.com']")
            if naver_el:
                naver_url = (await naver_el.get_attribute("href")) or ""

            # 제목이 없으면 item 전체 텍스트 첫 줄 사용
            if not title:
                full_text = (await item.inner_text()).strip()
                lines = [l.strip() for l in full_text.split("\n") if l.strip() and len(l.strip()) > 10]
                if lines:
                    title = lines[0][:100]

            if not title or len(title) < 5:
                continue

            # URL: n.news.naver.com 우선, 없으면 원본 URL
            final_url = naver_url or title_url
            if not final_url:
                continue

            # 언론사
            source = ""
            press_el = await item.query_selector(".press")
            if press_el:
                source = (await press_el.inner_text()).strip()

            # 날짜
            pub_date = until
            date_el = await item.query_selector(".date")
            if date_el:
                raw_date = (await date_el.inner_text()).strip()
                pub_date = _parse_date(raw_date, until)

            # 요약
            content = ""
            desc_el = await item.query_selector(".news_dsc, .dsc_wrap, .api_txt_lines")
            if desc_el:
                content = (await desc_el.inner_text()).strip()[:400]

            articles.append({
                "title": title,
                "url": final_url,
                "source": source,
                "published_date": pub_date,
                "keyword": keyword,
                "content": content,
                "summary": content,
            })

        await browser.close()
    return articles


def _parse_date(raw: str, fallback: str) -> str:
    m = re.search(r"(\d{4})[.](\d{2})[.](\d{2})", raw)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m2 = re.search(r"(\d{2})[.](\d{2})[.]", raw)
    if m2:
        year = fallback[:4]
        return f"{year}-{m2.group(1)}-{m2.group(2)}"
    return fallback


if __name__ == "__main__":
    params = json.loads(sys.stdin.read())
    result = asyncio.run(crawl(
        keyword=params["keyword"],
        since=params["since"],
        until=params["until"],
        limit=params.get("limit", 5),
    ))
    print(json.dumps(result, ensure_ascii=False))
