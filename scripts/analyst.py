# -*- coding: utf-8 -*-
"""
STEP 2: Claude AI 기반 핀테크 뉴스 분석
수집된 기사 본문을 Claude API로 분석해 PM 관점의 Top 3 이슈와 기회/리스크를 도출한다.
ANTHROPIC_API_KEY 없으면 키워드 기반 분석으로 대체.
"""

import json
import os
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
PROJECT_ROOT = Path(__file__).parent.parent

PERSPECTIVE_KEYWORDS = {
    "competition": ["토스", "카카오페이", "네이버페이", "삼성페이", "간편결제", "경쟁", "점유", "출시", "제휴"],
    "regulation":  ["규제", "금융위", "금감원", "정책", "법안", "오픈뱅킹", "마이데이터", "인허가", "의무화"],
    "ux_trend":    ["사용자", "경험", "편의", "간편", "bnpl", "후불", "ai", "금융ai", "혁신", "ui"],
}

PERSPECTIVE_LABELS = {
    "competition": "빅테크 핀테크 경쟁 구도",
    "regulation":  "규제/정책 리스크",
    "ux_trend":    "사용자 경험/UX 트렌드",
}


# ── 데이터 로드 ───────────────────────────────────────────────────────────────

def load_latest_collected() -> tuple[dict, Path]:
    files = sorted((PROJECT_ROOT / "reports" / "collected").glob("collected_*.json"))
    if not files:
        raise FileNotFoundError("수집 파일 없음. collector.py를 먼저 실행하세요.")
    path = files[-1]
    return json.loads(path.read_text(encoding="utf-8")), path


def build_article_text(articles: list[dict], max_articles: int = 25) -> str:
    """Claude에게 넘길 기사 텍스트 블록 생성."""
    lines = []
    for i, a in enumerate(articles[:max_articles]):
        content = (a.get("content") or a.get("summary") or "")[:600]
        url = a.get("real_url") or a.get("url", "")
        lines.append(
            f"[{i+1}] 키워드: {a['keyword']} | 출처: {a['source']} | 날짜: {a['published_date']}\n"
            f"    제목: {a['title']}\n"
            f"    URL: {url}\n"
            f"    내용: {content}"
        )
    return "\n\n".join(lines)


# ── Claude API 분석 ───────────────────────────────────────────────────────────

ANALYSIS_SCHEMA = """{
  "analysis_perspectives": {
    "competition": {
      "summary": "빅테크 경쟁 구도 3-4문장 요약 (구체적 사실 포함)",
      "key_findings": ["구체적 발견사항 1", "구체적 발견사항 2"]
    },
    "regulation": {
      "summary": "규제/정책 리스크 3-4문장 요약",
      "key_findings": ["발견사항 1", "발견사항 2"]
    },
    "ux_trend": {
      "summary": "UX 트렌드 3-4문장 요약",
      "key_findings": ["발견사항 1", "발견사항 2"]
    }
  },
  "top_issues": [
    {
      "rank": 1,
      "title": "이슈 제목 (50자 이내, 구체적 사실 포함)",
      "perspective": "competition 또는 regulation 또는 ux_trend",
      "description": "2-3문장. '회사A가 X를 발표했으며, 이는 Y 방향으로 경쟁이 전개될 것' 형식으로 구체적 수치/사실 포함",
      "opportunity": "구체적 비즈니스 기회 1문장. '~함으로써 ~을 달성할 기회'",
      "risk": "구체적 리스크 1문장. '~이 진행될 경우 ~의 위험'",
      "article_url": "이 이슈의 핵심 기사 URL",
      "related_articles": [
        {"title": "관련기사 제목", "url": "기사 URL"}
      ],
      "one_line_comment": "PM이라면 ~해야 한다 형식의 액션 지향 코멘트"
    },
    {"rank": 2, "title": "...", "perspective": "...", "description": "...", "opportunity": "...", "risk": "...", "article_url": "...", "related_articles": [], "one_line_comment": "..."},
    {"rank": 3, "title": "...", "perspective": "...", "description": "...", "opportunity": "...", "risk": "...", "article_url": "...", "related_articles": [], "one_line_comment": "..."}
  ],
  "weekly_summary": "이번 주 핀테크 시장 전체를 관통하는 한 줄 임팩트 문장 (구체적 수치/사실 포함)"
}"""


def run_with_claude(articles: list[dict], period: dict) -> dict:
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    articles_text = build_article_text(articles)

    prompt = f"""당신은 핀테크 시장을 분석하는 시니어 PM입니다.
아래는 {period['start']} ~ {period['end']} 수집된 핀테크 뉴스 기사입니다.

{articles_text}

다음 기준으로 PM 관점 분석을 수행하세요:
1. 기사 제목만 나열하지 말고, 실제 내용(본문)을 읽고 구체적 사실·수치 기반으로 작성
2. description은 "A가 B를 발표. C와의 D 경쟁이 E 방향으로 전개될 것" 형식
3. opportunity와 risk는 추상적 표현 금지. 반드시 기사 내용의 구체적 사실을 근거로
4. Top 3 이슈는 서로 다른 기사를 사용하고, 관점(competition/regulation/ux_trend)도 가능하면 분산
5. article_url은 해당 이슈의 가장 핵심적인 기사 URL을 정확히 기재
6. weekly_summary는 뉴스레터 첫 문장으로 쓸 수 있는 임팩트 있는 한 문장

반드시 아래 JSON 형식만 출력하세요 (설명, 마크다운 코드블록 없이 순수 JSON):
{ANALYSIS_SCHEMA}"""

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = msg.content[0].text.strip()
    # 혹시 코드블록이 있으면 제거
    if "```" in raw:
        parts = raw.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if part.startswith("{"):
                raw = part
                break

    return json.loads(raw)


# ── 키워드 기반 폴백 분석 ─────────────────────────────────────────────────────

def classify_articles(articles: list[dict]) -> dict[str, list[dict]]:
    buckets: dict[str, list[dict]] = {k: [] for k in PERSPECTIVE_KEYWORDS}
    for art in articles:
        text = f"{art['title']} {art.get('content', '')} {art.get('summary', '')}".lower()
        for persp, kws in PERSPECTIVE_KEYWORDS.items():
            if any(kw in text for kw in kws):
                buckets[persp].append(art)
    return buckets


def build_fallback_analysis(articles: list[dict], period: dict) -> dict:
    buckets = classify_articles(articles)
    sorted_persps = sorted(buckets, key=lambda k: len(buckets[k]), reverse=True)

    perspectives = {}
    for persp in PERSPECTIVE_KEYWORDS:
        arts = buckets[persp]
        titles = [a["title"] for a in arts[:5]]
        content_samples = " ".join(
            (a.get("content") or a.get("summary") or "")[:150]
            for a in arts[:3]
        )
        perspectives[persp] = {
            "summary": (
                f"{PERSPECTIVE_LABELS[persp]} 관련 {len(arts)}건 수집. "
                f"주요 기사: {', '.join(titles[:2])}. {content_samples[:200]}"
            ),
            "key_findings": titles[:3],
        }

    OPP_RISK = {
        "competition": (
            "경쟁사의 신규 서비스 출시 타이밍을 분석해 차별화 기능을 선제 기획할 기회",
            "빅테크의 공격적 확장으로 자사 서비스 점유율 하락 가능성",
        ),
        "regulation": (
            "규제 선제 준수로 신뢰도 확보 및 후발 경쟁사 대비 진입장벽 활용 기회",
            "규제 미대응 시 서비스 중단 또는 과징금·영업정지 리스크",
        ),
        "ux_trend": (
            "사용자 행동 변화를 전환율·리텐션 개선 기회로 연결해 핵심 지표 향상 가능",
            "UX 트렌드 대응 지연 시 경쟁 앱으로 사용자 이탈 및 DAU 하락 위험",
        ),
    }
    ONE_LINE = {
        "competition": "PM이라면 경쟁사 신기능 출시 주기를 추적해 자사 로드맵 우선순위를 조정해야 한다.",
        "regulation": "PM이라면 규제 변경사항을 법무팀과 즉시 공유하고 컴플라이언스 체크리스트를 갱신해야 한다.",
        "ux_trend": "PM이라면 UX 트렌드를 사용자 인터뷰에서 검증하고 다음 스프린트에 반영해야 한다.",
    }

    top_issues = []
    used_urls: set[str] = set()
    rank = 1
    for persp in sorted_persps:
        if rank > 3:
            break
        arts = [a for a in buckets[persp] if a.get("real_url") or a.get("url") not in used_urls]
        if not arts:
            continue
        top = arts[0]
        url = top.get("real_url") or top.get("url", "")
        used_urls.add(url)
        opp, risk = OPP_RISK[persp]
        top_issues.append({
            "rank": rank,
            "title": top["title"][:50],
            "perspective": persp,
            "description": (
                f"{top['title']}. "
                f"{(top.get('content') or top.get('summary') or '')[:200]}"
            ),
            "opportunity": opp,
            "risk": risk,
            "article_url": url,
            "related_articles": [
                {"title": a["title"], "url": a.get("real_url") or a.get("url", "")}
                for a in arts[1:3]
            ],
            "one_line_comment": ONE_LINE[persp],
        })
        rank += 1

    while len(top_issues) < 3:
        r = len(top_issues) + 1
        top_issues.append({
            "rank": r, "title": "기타 핀테크 동향",
            "perspective": "competition",
            "description": "이번 주 수집된 기타 핀테크 동향입니다.",
            "opportunity": "시장 변화에 선제 대응할 기회",
            "risk": "정보 부족으로 인한 의사결정 지연",
            "article_url": "",
            "related_articles": [],
            "one_line_comment": "PM이라면 주간 시장 모니터링 루틴을 강화해야 한다.",
        })

    top_titles = [i["title"] for i in top_issues[:2]]
    return {
        "analysis_perspectives": perspectives,
        "top_issues": top_issues,
        "weekly_summary": (
            f"이번 주 핀테크 시장은 {', '.join(top_titles)} 등이 주요 화두로, "
            f"총 {len(articles)}건의 기사가 수집됐습니다."
        ),
    }


# ── 메인 ──────────────────────────────────────────────────────────────────────

def run(output_path: Path | None = None) -> Path:
    collected, src_path = load_latest_collected()
    articles = collected.get("articles", [])
    period = collected.get("period", {})
    print(f"[analyst] 기사 {len(articles)}건 분석 중...")

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    core: dict = {}

    if api_key:
        print("[analyst] Claude API 분석 시작...")
        try:
            core = run_with_claude(articles, period)
            print("[analyst] Claude API 분석 완료")
        except Exception as e:
            print(f"[analyst] Claude API 오류 ({e}) → 키워드 분석으로 대체")
            core = build_fallback_analysis(articles, period)
    else:
        print("[analyst] ANTHROPIC_API_KEY 없음 → 키워드 기반 분석")
        core = build_fallback_analysis(articles, period)

    if output_path is None:
        (PROJECT_ROOT / "reports").mkdir(parents=True, exist_ok=True)
        output_path = PROJECT_ROOT / "reports" / f"analysis_{date.today().strftime('%Y%m%d')}.json"

    result = {
        "analyzed_at": datetime.now(KST).isoformat(),
        "source_file": src_path.name,
        "period": period,
        **core,
    }
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[analyst] 저장 완료: {output_path.name}")
    return output_path


if __name__ == "__main__":
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    run()
