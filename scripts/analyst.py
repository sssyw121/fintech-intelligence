# -*- coding: utf-8 -*-
"""
STEP 2: 핀테크 뉴스 분석
수집된 기사를 3가지 관점으로 분석해 Top 3 이슈와 기회/리스크를 도출한다.
ANTHROPIC_API_KEY가 있으면 Claude API 사용, 없으면 키워드 기반 분석.
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
    "competition": ["토스", "카카오페이", "네이버페이", "삼성페이", "간편결제", "경쟁", "점유", "출시", "파트너"],
    "regulation": ["규제", "금융위", "금감원", "정책", "법", "오픈뱅킹", "마이데이터", "의무", "허가"],
    "ux_trend": ["사용자", "ux", "ui", "경험", "편의", "간편", "bnpl", "후불", "ai", "금융ai"],
}

PERSPECTIVE_LABELS = {
    "competition": "빅테크 핀테크 경쟁 구도",
    "regulation": "규제/정책 리스크",
    "ux_trend": "사용자 경험/UX 트렌드",
}


def load_latest_collected() -> tuple[dict, Path]:
    collected_dir = PROJECT_ROOT / "reports" / "collected"
    files = sorted(collected_dir.glob("collected_*.json"))
    if not files:
        raise FileNotFoundError("수집 파일 없음. collector.py를 먼저 실행하세요.")
    path = files[-1]
    data = json.loads(path.read_text(encoding="utf-8"))
    return data, path


def classify_articles(articles: list[dict]) -> dict[str, list[dict]]:
    buckets: dict[str, list[dict]] = {k: [] for k in PERSPECTIVE_KEYWORDS}
    for art in articles:
        text = (art["title"] + " " + art["summary"]).lower()
        for persp, kws in PERSPECTIVE_KEYWORDS.items():
            if any(kw in text for kw in kws):
                buckets[persp].append(art)
    return buckets


def summarize_perspective(persp: str, articles: list[dict]) -> dict:
    if not articles:
        return {"summary": "해당 기간 관련 기사가 없습니다.", "key_findings": []}

    titles = [a["title"] for a in articles[:10]]
    findings = titles[:3]
    summary = f"이번 주 {PERSPECTIVE_LABELS[persp]} 관련 기사 {len(articles)}건 수집. " \
              f"주요 기사: {', '.join(titles[:2])}."
    return {"summary": summary, "key_findings": findings}


def build_top_issues(buckets: dict[str, list[dict]]) -> list[dict]:
    issues = []
    rank = 1

    # 기사 수 기준으로 관점 정렬
    sorted_persps = sorted(buckets.keys(), key=lambda k: len(buckets[k]), reverse=True)

    for persp in sorted_persps:
        if rank > 3:
            break
        arts = buckets[persp]
        if not arts:
            continue

        top_art = arts[0]
        related = [a["title"] for a in arts[:3]]

        opp, risk = _derive_opp_risk(persp, arts)

        issues.append({
            "rank": rank,
            "title": top_art["title"][:60],
            "perspective": persp,
            "description": f"{PERSPECTIVE_LABELS[persp]} 관련 {len(arts)}건의 기사가 수집됐습니다. "
                           f"대표 기사: {top_art['title']}",
            "opportunity": opp,
            "risk": risk,
            "related_articles": related,
            "one_line_comment": _one_line(persp),
        })
        rank += 1

    # 3개 미만이면 나머지 채우기
    while len(issues) < 3:
        issues.append({
            "rank": len(issues) + 1,
            "title": "기타 핀테크 동향",
            "perspective": "competition",
            "description": "이번 주 수집된 기사 중 추가 주목할 만한 동향입니다.",
            "opportunity": "시장 변화에 선제적으로 대응할 기회",
            "risk": "정보 부족으로 인한 의사결정 지연 가능성",
            "related_articles": [],
            "one_line_comment": "PM이라면 시장 신호를 놓치지 말고 주간 모니터링을 강화해야 한다.",
        })

    return issues[:3]


def _derive_opp_risk(persp: str, articles: list[dict]) -> tuple[str, str]:
    if persp == "competition":
        return (
            "경쟁사 동향을 분석해 차별화된 기능/UX를 선제적으로 기획할 기회",
            "빅테크의 공격적 확장으로 자사 서비스 점유율 하락 가능성",
        )
    elif persp == "regulation":
        return (
            "규제 선제 준수로 신뢰도 확보 및 시장 진입 장벽 활용 기회",
            "규제 미대응 시 서비스 중단 또는 과징금 리스크",
        )
    else:
        return (
            "사용자 니즈 변화에 맞춘 UX 개선으로 전환율 및 리텐션 향상 기회",
            "UX 트렌드 대응 지연 시 사용자 이탈 및 경쟁 앱으로 전환 리스크",
        )


def _one_line(persp: str) -> str:
    if persp == "competition":
        return "PM이라면 경쟁사 신기능 출시 타임라인을 추적해 로드맵에 반영해야 한다."
    elif persp == "regulation":
        return "PM이라면 규제 변화를 법무팀과 공유하고 컴플라이언스 체크리스트를 업데이트해야 한다."
    else:
        return "PM이라면 사용자 인터뷰를 통해 UX 트렌드가 자사 페인포인트와 연결되는지 검증해야 한다."


def run_with_claude(articles: list[dict], period: dict) -> dict:
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    articles_text = "\n".join(
        f"- [{a['keyword']}] {a['title']} ({a['source']}, {a['published_date']}): {a['summary']}"
        for a in articles[:30]
    )

    prompt = f"""다음은 {period['start']} ~ {period['end']} 기간의 핀테크 뉴스 기사 목록입니다.

{articles_text}

아래 JSON 형식으로 분석 결과를 출력하세요. JSON 외의 다른 텍스트는 출력하지 마세요.

{{
  "analysis_perspectives": {{
    "competition": {{"summary": "3-5문장 요약", "key_findings": ["발견1", "발견2"]}},
    "regulation": {{"summary": "3-5문장 요약", "key_findings": ["발견1", "발견2"]}},
    "ux_trend": {{"summary": "3-5문장 요약", "key_findings": ["발견1", "발견2"]}}
  }},
  "top_issues": [
    {{
      "rank": 1,
      "title": "이슈 제목 (60자 이내)",
      "perspective": "competition|regulation|ux_trend 중 하나",
      "description": "3-5문장 설명",
      "opportunity": "구체적 비즈니스 기회 1문장",
      "risk": "구체적 리스크 1문장",
      "related_articles": ["기사 제목1", "기사 제목2"],
      "one_line_comment": "PM이라면 ~해야 한다 형식의 액션 지향 코멘트"
    }},
    {{"rank": 2, ...}},
    {{"rank": 3, ...}}
  ],
  "weekly_summary": "이번 주 핀테크 시장 전체를 관통하는 한 줄 요약"
}}"""

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = msg.content[0].text.strip()
    # JSON 블록 추출
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw)


def run(output_path: Path | None = None) -> Path:
    collected, src_path = load_latest_collected()
    articles = collected.get("articles", [])
    period = collected.get("period", {})

    print(f"[analyst] 기사 {len(articles)}건 분석 중...")

    analysis_core: dict = {}

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if api_key:
        print("[analyst] Claude API 사용")
        try:
            analysis_core = run_with_claude(articles, period)
        except Exception as e:
            print(f"[analyst] Claude API 실패 ({e}), 키워드 분석으로 대체")
            api_key = ""

    if not api_key:
        print("[analyst] 키워드 기반 분석")
        buckets = classify_articles(articles)
        perspectives = {k: summarize_perspective(k, v) for k, v in buckets.items()}
        top_issues = build_top_issues(buckets)
        top_titles = [i["title"] for i in top_issues]
        weekly_summary = (
            f"이번 주 핀테크 시장은 {', '.join(top_titles[:2])} 등이 주요 화두였으며, "
            f"총 {len(articles)}건의 기사가 수집됐습니다."
        )
        analysis_core = {
            "analysis_perspectives": perspectives,
            "top_issues": top_issues,
            "weekly_summary": weekly_summary,
        }

    if output_path is None:
        (PROJECT_ROOT / "reports").mkdir(parents=True, exist_ok=True)
        output_path = PROJECT_ROOT / "reports" / f"analysis_{date.today().strftime('%Y%m%d')}.json"

    result = {
        "analyzed_at": datetime.now(KST).isoformat(),
        "source_file": src_path.name,
        "period": period,
        **analysis_core,
    }

    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[analyst] 저장 완료: {output_path.name}")
    return output_path


if __name__ == "__main__":
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

    # .env 로드
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

    run()
