// 네이버 뉴스 크롤러 (Node.js Playwright)
// stdin: JSON {"keyword": str, "since": "YYYY-MM-DD", "until": "YYYY-MM-DD", "limit": int}
// stdout: JSON list of article dicts

const { chromium } = require('playwright');

function parseDate(raw, fallback) {
  // "2026.05.14." 형식
  const m = raw.match(/(\d{4})[.](\d{2})[.](\d{2})/);
  if (m) return `${m[1]}-${m[2]}-${m[3]}`;
  // "05.14." 형식
  const m2 = raw.match(/(\d{2})[.](\d{2})[.]/);
  if (m2) return `${fallback.slice(0, 4)}-${m2[1]}-${m2[2]}`;
  // "N분 전", "N시간 전" → 오늘 날짜
  if (/분 전|시간 전/.test(raw)) {
    const now = new Date();
    const y = now.getFullYear();
    const mo = String(now.getMonth() + 1).padStart(2, '0');
    const d = String(now.getDate()).padStart(2, '0');
    return `${y}-${mo}-${d}`;
  }
  // "N일 전" → N일 전 날짜
  const mDays = raw.match(/(\d+)일 전/);
  if (mDays) {
    const past = new Date();
    past.setDate(past.getDate() - parseInt(mDays[1]));
    const y = past.getFullYear();
    const mo = String(past.getMonth() + 1).padStart(2, '0');
    const d = String(past.getDate()).padStart(2, '0');
    return `${y}-${mo}-${d}`;
  }
  return fallback;
}

async function crawl(keyword, since, until, limit = 5) {
  const ds = since.replace(/-/g, '.');
  const de = until.replace(/-/g, '.');
  const url = `https://search.naver.com/search.naver?where=news&query=${encodeURIComponent(keyword)}&sm=tab_opt&sort=1&pd=3&ds=${ds}&de=${de}`;

  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    locale: 'ko-KR',
  });

  let rawArticles = [];
  try {
    await page.goto(url, { timeout: 20000, waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(2000);

    // JS evaluate로 DOM 탐색 — n.news.naver.com 링크 기준으로 기사 추출
    rawArticles = await page.evaluate((lim) => {
      const naverLinks = [...document.querySelectorAll('a[href*="n.news.naver.com"]')];
      const articles = [];
      const seenUrls = new Set();

      // n.news 링크 없는 기사도 포함하기 위해 외부 기사 링크도 수집
      const externalLinks = [...document.querySelectorAll('a[href*="OutUrl=naver"], a[href*="cp=nv"]')]
        .filter(a => !a.href.includes('n.news.naver.com'));

      // n.news 링크 우선, 없으면 외부 링크로 폴백
      const allCandidates = [...naverLinks, ...externalLinks];
      const processedContainers = new Set();

      for (const naverA of allCandidates.slice(0, lim * 5)) {
        const isNaverNews = naverA.href.includes('n.news.naver.com');
        const naverUrl = isNaverNews ? naverA.href : '';
        const anchorUrl = naverA.href;
        if (seenUrls.has(anchorUrl)) continue;

        // 부모 방향으로 올라가면서 기사 컨테이너 찾기
        let container = naverA;
        let title = '';
        let titleUrl = '';
        let content = '';
        let source = '';
        let dateText = '';

        for (let depth = 0; depth < 10; depth++) {
          if (!container.parentElement) break;
          container = container.parentElement;

          const allLinks = [...container.querySelectorAll('a[href]')];
          // 외부 뉴스 기사 링크만 추출 (naver 내부 서비스/유틸 링크 제외)
          const NAVER_INTERNALS = [
            'n.news.naver.com', 'nid.naver.com', 'naver.com/keep',
            'keep.naver.com', 'naver.com/bookmark', 'help.naver.com',
            'search.naver.com', 'news.naver.com/search',
          ];
          const articleLinks = allLinks.filter(a => {
            const href = a.href;
            if (!href || href.startsWith('#')) return false;
            if (NAVER_INTERNALS.some(pat => href.includes(pat))) return false;
            if (href.includes('naver.com') && !href.includes('OutUrl=naver') && !href.includes('cp=nv')) return false;
            const text = a.innerText.trim();
            if (text.length < 8 || text === 'Keep에 저장' || text === '네이버뉴스') return false;
            return true;
          });

          if (articleLinks.length >= 1) {
            // 첫 번째 링크 = 제목
            const first = articleLinks[0];
            title = first.innerText.trim().split('\n')[0].trim();
            titleUrl = first.href;

            // 두 번째 링크 = 본문 요약 (있는 경우)
            if (articleLinks.length >= 2) {
              const desc = articleLinks[1].innerText.trim();
              if (desc.length > title.length) {
                content = desc.slice(0, 400);
              }
            }

            // 언론사 + 날짜: container 전체 텍스트 파싱
            const allText = container.innerText.trim();
            const textLines = allText.split('\n').map(l => l.trim()).filter(l => l.length > 0);

            // 날짜 패턴 찾기
            const timePatterns = /(\d{4}[.]\d{2}[.]\d{2}[.]?|\d{2}[.]\d{2}[.]|\d+분 전|\d+시간 전|\d+일 전)/;
            for (const line of textLines.slice(0, 8)) {
              if (timePatterns.test(line)) {
                dateText = line.match(timePatterns)[0];
                break;
              }
            }

            // 언론사: 날짜 줄 바로 앞 줄 (10자 이하 짧은 텍스트)
            const dateLineIdx = textLines.findIndex(l => timePatterns.test(l));
            if (dateLineIdx > 0) {
              const candidate = textLines[dateLineIdx - 1];
              if (candidate.length <= 30 && candidate !== title) source = candidate;
            }
            // 또는 첫 번째 짧은 줄
            if (!source) {
              const firstShort = textLines.find(l => l.length > 1 && l.length <= 20 && !timePatterns.test(l) && l !== '언론사 선정');
              if (firstShort && firstShort !== title) source = firstShort;
            }

            // 기사 컨테이너 발견
            break;
          }
        }

        if (!title || title.length < 5) continue;

        seenUrls.add(anchorUrl);
        // 컨테이너 중복 방지 (같은 기사 다른 링크로 중복 방지)
        const containerKey = container.innerText.trim().slice(0, 50);
        if (processedContainers.has(containerKey)) continue;
        processedContainers.add(containerKey);

        articles.push({ title, naverUrl, titleUrl, source, dateText, content });

        if (articles.length >= lim) break;
      }

      return articles;
    }, limit);

  } finally {
    await browser.close();
  }

  // 날짜 파싱, 제목 기반 중복 제거, 최종 포맷
  const seenTitles = new Set();
  const results = [];
  for (const a of rawArticles) {
    const key = a.title.slice(0, 30);
    if (seenTitles.has(key)) continue;
    seenTitles.add(key);
    results.push({
      title: a.title,
      url: a.naverUrl || a.titleUrl,
      source: a.source,
      published_date: parseDate(a.dateText || '', until),
      keyword,
      content: a.content,
      summary: a.content,
    });
  }
  return results;
}

async function main() {
  const chunks = [];
  for await (const chunk of process.stdin) chunks.push(chunk);
  const params = JSON.parse(chunks.join(''));
  const result = await crawl(params.keyword, params.since, params.until, params.limit || 5);
  process.stdout.write(JSON.stringify(result));
}

main().catch(err => {
  process.stderr.write(String(err) + '\n');
  process.exit(1);
});
