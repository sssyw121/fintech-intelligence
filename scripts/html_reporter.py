# -*- coding: utf-8 -*-
"""
STEP 4: HTML 브리핑 파일 생성
templates/Daily Brief Newsletter.html + templates/tokens.css 디자인 시스템 기반으로
분석 JSON을 정적 HTML 리포트로 렌더링하여 reports/html/brief_YYYYMMDD.html 에 저장.
"""

import html as _html
import json
import os
import re
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
TEMPLATES    = PROJECT_ROOT / "templates"
HTML_OUT     = PROJECT_ROOT / "reports" / "html"

PERSPECTIVE = {
    "competition": ("경쟁 구도",  "competition"),
    "regulation":  ("규제 리스크", "regulation"),
    "ux_trend":    ("UX 트렌드",  "ux_trend"),
}
RISK_LABELS = [
    ("regulatory", "규제"),
    ("competition", "경쟁"),
    ("technology",  "기술"),
    ("user",        "사용자"),
    ("revenue",     "수익"),
]


# ── 유틸 ──────────────────────────────────────────────────────────────────────

def h(text: str) -> str:
    return _html.escape(str(text))


def _fmt_date(iso: str) -> str:
    return iso.replace("-", ".")


def _next_monday(ref: str) -> str:
    d = date.fromisoformat(ref)
    days = (7 - d.weekday()) % 7 or 7
    return (d + timedelta(days=days)).strftime("%Y-%m-%d")


def _parse_total_articles(source_file: str) -> int:
    try:
        path = PROJECT_ROOT / "reports" / "collected" / source_file
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8")).get("total_articles", 0)
    except Exception:
        pass
    return 0


def _split_desc(desc: str) -> tuple[str, str]:
    sentences = [s.strip() for s in desc.replace("。", ".").split(".") if len(s.strip()) > 10]
    if len(sentences) >= 2:
        return sentences[0] + ".", ". ".join(sentences[1:]) + "."
    return desc, ""


def _top_risks(risk_analysis: dict) -> list[tuple[str, str]]:
    items = [
        (label, risk_analysis[key])
        for key, label in RISK_LABELS
        if risk_analysis.get(key) and "제한적" not in risk_analysis[key]
    ]
    return items[:3]


def _tokens_css() -> str:
    p = TEMPLATES / "tokens.css"
    return p.read_text(encoding="utf-8") if p.exists() else ""


# ── 레이아웃 CSS (Daily Brief Newsletter.html <style> 섹션과 동일) ─────────────

_LAYOUT_CSS = """
/* ════════════ Page layout ════════════ */
body {
  min-height: 100vh;
  background:
    radial-gradient(1200px 600px at 80% -10%, #F0EEE7 0%, transparent 60%),
    var(--color-background-canvas);
}
.page {
  max-width: var(--layout-content-max);
  margin: 0 auto;
  padding: var(--space-8) var(--space-5) var(--space-12);
}
@media (max-width: 480px) {
  .page { padding: var(--space-5) var(--space-4) var(--space-10); }
}

/* ════════════ Top bar ════════════ */
.topbar {
  position: sticky; top: 0; z-index: 50;
  backdrop-filter: blur(14px) saturate(1.4);
  -webkit-backdrop-filter: blur(14px) saturate(1.4);
  background: rgba(250, 250, 248, 0.78);
  border-bottom: var(--border-hairline);
  margin: calc(var(--space-8) * -1) calc(var(--space-5) * -1) var(--space-8);
  padding: var(--space-3) var(--space-5);
  display: flex; align-items: center; justify-content: space-between; gap: var(--space-4);
}
.topbar-brand {
  display: flex; align-items: center; gap: var(--space-2);
  font-size: var(--font-size-sm); font-weight: var(--font-weight-medium);
  color: var(--color-text-primary); letter-spacing: var(--letter-spacing-tight);
}
.topbar-brand .dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: var(--color-text-primary); position: relative;
}
.topbar-brand .dot::after {
  content: ''; position: absolute; inset: -3px;
  border: 1px solid var(--color-text-primary); border-radius: 50%;
  opacity: 0.35; animation: pulse 2.4s var(--ease-out) infinite;
}
@keyframes pulse {
  0%, 100% { transform: scale(1); opacity: 0.35; }
  50% { transform: scale(1.3); opacity: 0; }
}

/* ════════════ Header ════════════ */
.header { margin-bottom: var(--space-8); }
.header-period {
  display: inline-flex; align-items: center; gap: var(--space-2);
  font-size: var(--font-size-xs); font-weight: var(--font-weight-medium);
  color: var(--color-text-tertiary); letter-spacing: var(--letter-spacing-wide);
  text-transform: uppercase; margin-bottom: var(--space-3);
}
.header-period::before {
  content: ''; width: 16px; height: 1px; background: var(--color-text-tertiary);
}
.header-title {
  font-size: var(--font-size-3xl); font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary); letter-spacing: var(--letter-spacing-tight);
  line-height: var(--line-height-tight); margin: 0 0 var(--space-3);
}
.header-summary {
  font-size: var(--font-size-md); color: var(--color-text-secondary);
  line-height: var(--line-height-relaxed); margin: 0; max-width: 56ch;
}
.header-summary mark {
  background: linear-gradient(180deg, transparent 60%, var(--color-accent-highlight) 60%);
  color: var(--color-text-primary); padding: 0 2px; font-weight: var(--font-weight-medium);
}

/* ════════════ Stats bar ════════════ */
.stats {
  display: grid; grid-template-columns: repeat(3, 1fr);
  gap: var(--space-2); margin-bottom: var(--space-8);
}
.stat {
  background: var(--color-background-primary); border: var(--border-hairline);
  border-radius: var(--border-radius-md); padding: var(--space-4);
  transition: transform var(--duration-base) var(--ease-out);
}
.stat:hover { transform: translateY(-2px); }
.stat-label {
  font-size: var(--font-size-xs); color: var(--color-text-tertiary);
  margin: 0 0 var(--space-1); display: flex; align-items: center; gap: 4px;
}
.stat-value {
  font-size: var(--font-size-2xl); font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary); letter-spacing: var(--letter-spacing-tight);
  margin: 0; font-feature-settings: 'tnum';
}
.stat-value .unit {
  font-size: var(--font-size-md); font-weight: var(--font-weight-regular);
  color: var(--color-text-tertiary); margin-left: 2px;
}
@media (max-width: 480px) {
  .stats { grid-template-columns: 1fr 1fr 1fr; gap: 6px; }
  .stat { padding: var(--space-3); }
  .stat-value { font-size: 18px; }
}

/* ════════════ Section header ════════════ */
.section-head {
  display: flex; align-items: center; justify-content: space-between;
  gap: var(--space-3); margin-bottom: var(--space-4); flex-wrap: wrap;
}
.section-title {
  font-size: var(--font-size-xs); font-weight: var(--font-weight-semibold);
  color: var(--color-text-tertiary); letter-spacing: var(--letter-spacing-wide);
  text-transform: uppercase; margin: 0;
  display: flex; align-items: center; gap: var(--space-2);
}
.section-title-num {
  display: inline-flex; width: 18px; height: 18px;
  align-items: center; justify-content: center;
  background: var(--color-text-primary); color: var(--color-background-primary);
  border-radius: 50%; font-size: 10px; font-weight: var(--font-weight-semibold);
}

/* ════════════ Issue card ════════════ */
.card {
  background: var(--color-background-primary); border: var(--border-hairline);
  border-radius: var(--border-radius-lg); padding: var(--space-5);
  margin-bottom: var(--space-3); position: relative;
  transition: transform var(--duration-base) var(--ease-out),
              box-shadow var(--duration-base) var(--ease-out),
              border-color var(--duration-base) var(--ease-out);
  animation: cardIn 0.6s var(--ease-out) both;
}
.card:hover {
  transform: translateY(-3px); box-shadow: var(--shadow-md);
  border-color: var(--color-border-secondary);
}
@keyframes cardIn {
  from { opacity: 0; transform: translateY(12px); }
  to   { opacity: 1; transform: translateY(0); }
}
.card-stagger-0 { animation-delay: 0.05s; }
.card-stagger-1 { animation-delay: 0.18s; }
.card-stagger-2 { animation-delay: 0.30s; }

.card-header {
  display: flex; align-items: center; gap: var(--space-2);
  margin-bottom: var(--space-3);
}
.rank-badge {
  display: inline-flex; width: 24px; height: 24px;
  align-items: center; justify-content: center;
  background: var(--color-background-secondary); color: var(--color-text-primary);
  border-radius: var(--border-radius-sm);
  font-size: var(--font-size-xs); font-weight: var(--font-weight-semibold);
}
.category-tag {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: var(--font-size-xs); font-weight: var(--font-weight-medium);
  padding: 3px 9px; border-radius: var(--border-radius-pill);
  letter-spacing: var(--letter-spacing-tight);
}
.category-tag[data-cat="competition"] {
  background: var(--color-cat-competition-bg); color: var(--color-cat-competition-fg);
}
.category-tag[data-cat="regulation"] {
  background: var(--color-cat-regulation-bg); color: var(--color-cat-regulation-fg);
}
.category-tag[data-cat="ux_trend"] {
  background: var(--color-cat-uxtrend-bg); color: var(--color-cat-uxtrend-fg);
}
.category-tag[data-cat="general"] {
  background: var(--color-cat-general-bg); color: var(--color-cat-general-fg);
}
.category-tag-dot {
  width: 5px; height: 5px; border-radius: 50%; background: currentColor;
}
.card-source {
  margin-left: auto; font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}
.card-title {
  font-size: var(--font-size-xl); font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary); letter-spacing: var(--letter-spacing-tight);
  line-height: var(--line-height-tight); margin: 0 0 var(--space-3);
}
.card-title a { color: inherit; text-decoration: none; }
.card-title a:hover { text-decoration: underline; }
.card-description {
  font-size: var(--font-size-base); color: var(--color-text-secondary);
  line-height: var(--line-height-relaxed); margin: 0 0 var(--space-4);
}
.card-divider {
  border: none; border-top: var(--border-hairline); margin: var(--space-4) 0;
}

/* PM block */
.pm-block {
  background: var(--color-background-secondary);
  border-radius: var(--border-radius-md);
  padding: var(--space-3) var(--space-4); margin-bottom: var(--space-3);
}
.pm-block-head {
  display: flex; align-items: center; justify-content: space-between;
  gap: var(--space-2); margin-bottom: var(--space-2);
}
.pm-block-label {
  font-size: var(--font-size-xs); font-weight: var(--font-weight-semibold);
  color: var(--color-text-tertiary); letter-spacing: var(--letter-spacing-wide);
  text-transform: uppercase; display: flex; align-items: center; gap: 6px; margin: 0;
}
.pm-body {
  font-size: var(--font-size-base); color: var(--color-text-secondary);
  line-height: var(--line-height-relaxed); margin: 0;
}
.pm-extra {
  margin-top: var(--space-2); padding-top: var(--space-2);
  border-top: var(--border-hairline);
  font-size: var(--font-size-sm); color: var(--color-text-tertiary);
  line-height: var(--line-height-relaxed); display: grid; gap: 4px;
}
.pm-extra .label {
  font-weight: var(--font-weight-semibold); color: var(--color-text-secondary);
  font-size: var(--font-size-xs); letter-spacing: var(--letter-spacing-wide);
  text-transform: uppercase; margin-top: var(--space-2);
}

/* Opportunity / Risk */
.op-grid {
  display: grid; grid-template-columns: 1fr 1fr;
  gap: var(--space-2); margin-bottom: var(--space-3);
}
@media (max-width: 480px) { .op-grid { grid-template-columns: 1fr; } }
.op-tile { border-radius: var(--border-radius-md); padding: var(--space-3); }
.op-tile.opp { background: var(--color-accent-opportunity-bg); color: var(--color-accent-opportunity-fg); }
.op-tile.risk { background: var(--color-accent-risk-bg); color: var(--color-accent-risk-fg); }
.op-tile-head {
  font-size: var(--font-size-xs); font-weight: var(--font-weight-semibold);
  display: flex; align-items: center; gap: 5px;
  margin-bottom: var(--space-1); letter-spacing: var(--letter-spacing-tight);
}
.op-tile.opp .op-tile-head { color: var(--color-accent-opportunity-tag); }
.op-tile.risk .op-tile-head { color: var(--color-accent-risk-tag); }
.op-tile-body { font-size: var(--font-size-sm); line-height: var(--line-height-normal); margin: 0; }

/* Action item */
.action {
  display: flex; align-items: flex-start; gap: var(--space-2);
  background: var(--color-accent-action-bg);
  border-radius: var(--border-radius-md);
  padding: var(--space-3) var(--space-4); color: var(--color-accent-action-fg);
}
.action-check {
  flex: 0 0 18px; width: 18px; height: 18px; border-radius: 4px;
  background: var(--color-accent-action-fg); color: var(--color-accent-action-bg);
  display: inline-flex; align-items: center; justify-content: center; margin-top: 1px;
}
.action-body { flex: 1; min-width: 0; }
.action-label {
  font-size: var(--font-size-xs); font-weight: var(--font-weight-semibold);
  letter-spacing: var(--letter-spacing-wide); text-transform: uppercase;
  margin: 0 0 2px; opacity: 0.7;
}
.action-text { font-size: var(--font-size-base); line-height: var(--line-height-normal); margin: 0; }

/* Card footer */
.card-footer {
  display: flex; align-items: center; justify-content: space-between;
  gap: var(--space-3); margin-top: var(--space-4);
  padding-top: var(--space-3); border-top: var(--border-hairline);
}
.card-footer-meta {
  display: flex; align-items: center; gap: var(--space-3);
  font-size: var(--font-size-xs); color: var(--color-text-tertiary);
}
.card-footer-meta-item { display: inline-flex; align-items: center; gap: 4px; }
.footer-link {
  text-decoration: none; color: var(--color-text-secondary);
  border-bottom: 1px solid transparent;
  transition: border-color var(--duration-fast) var(--ease-out);
}
.footer-link:hover { border-color: var(--color-text-secondary); }

/* ════════════ PM comment ════════════ */
.pm-comment {
  background: var(--color-text-primary); color: var(--color-background-canvas);
  border-radius: var(--border-radius-lg); padding: var(--space-6);
  margin-top: var(--space-8); margin-bottom: var(--space-6);
  position: relative; overflow: hidden;
}
.pm-comment::before {
  content: '"'; position: absolute; top: -32px; right: 24px;
  font-size: 180px; font-family: Georgia, serif;
  color: rgba(255, 255, 255, 0.06); line-height: 1; pointer-events: none;
}
.pm-comment-label {
  font-size: var(--font-size-xs); font-weight: var(--font-weight-semibold);
  letter-spacing: var(--letter-spacing-wide); text-transform: uppercase;
  opacity: 0.55; margin: 0 0 var(--space-3);
  display: flex; align-items: center; gap: var(--space-2);
}
.pm-comment-body {
  font-size: var(--font-size-md); line-height: var(--line-height-relaxed);
  margin: 0 0 var(--space-3); max-width: 60ch;
}
.pm-comment-body strong {
  font-weight: var(--font-weight-semibold);
  background: linear-gradient(180deg, transparent 62%, rgba(245, 197, 24, 0.7) 62%);
  padding: 0 2px;
}
.pm-comment-list { margin: 0; padding: 0; list-style: none; display: grid; gap: var(--space-2); }
.pm-comment-item {
  display: flex; align-items: flex-start; gap: var(--space-2);
  font-size: var(--font-size-base); line-height: var(--line-height-normal); opacity: 0.92;
}
.pm-comment-item-num {
  flex: 0 0 18px; width: 18px; height: 18px; border-radius: 50%;
  background: rgba(255,255,255,0.12);
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 10px; font-weight: var(--font-weight-semibold); margin-top: 2px;
}

/* ════════════ Footer ════════════ */
.footer {
  font-size: var(--font-size-xs); color: var(--color-text-tertiary);
  display: flex; justify-content: space-between; gap: var(--space-3);
  padding-top: var(--space-4); border-top: var(--border-hairline); flex-wrap: wrap;
}
"""


# ── 이슈 카드 렌더러 ──────────────────────────────────────────────────────────

def _render_card(issue: dict, stagger: int) -> str:
    rank         = issue.get("rank", stagger + 1)
    title        = issue.get("title", "")
    desc         = issue.get("description", "")
    opp          = issue.get("opportunity", "")
    comment      = issue.get("one_line_comment", "")
    url          = issue.get("article_url", "")
    persp        = issue.get("perspective", "general")
    risk_analysis = issue.get("risk_analysis", {})

    persp_label, persp_cat = PERSPECTIVE.get(persp, ("기타", "general"))
    short_term, long_term  = _split_desc(desc)
    risks                  = _top_risks(risk_analysis)

    # 기회 타일
    opp_tile = f"""
        <div class="op-tile opp">
          <div class="op-tile-head">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 2L15.09 8.26L22 9.27L17 14.14L18.18 21.02L12 17.77L5.82 21.02L7 14.14L2 9.27L8.91 8.26L12 2Z"/>
            </svg>
            기회
          </div>
          <p class="op-tile-body">{h(opp)}</p>
        </div>"""

    # 리스크 타일
    if risks:
        risk_lines = "<br>".join(
            f"<strong>{h(label)}:</strong> {h(val)}" for label, val in risks
        )
    else:
        # 전부 "제한적"이면 첫 항목이라도 표시
        risk_lines = ""
        for key, label in RISK_LABELS:
            val = risk_analysis.get(key, "")
            if val:
                risk_lines = f"<strong>{h(label)}:</strong> {h(val)}"
                break
    risk_tile = f"""
        <div class="op-tile risk">
          <div class="op-tile-head">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor">
              <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0zM12 9v4m0 4h.01"/>
            </svg>
            리스크
          </div>
          <p class="op-tile-body">{risk_lines}</p>
        </div>"""

    # PM 관점 의미 (단기/중장기)
    pm_extra = ""
    if short_term and long_term:
        pm_extra = f"""
          <div class="pm-extra">
            <span class="label">단기</span>
            {h(short_term)}
            <span class="label">중장기</span>
            {h(long_term)}
          </div>"""

    # 카드 푸터 링크
    footer_link = ""
    if url:
        footer_link = f'<span class="card-footer-meta-item"><a href="{h(url)}" target="_blank" rel="noopener" class="footer-link">원문 보기 →</a></span>'

    return f"""
  <div class="card card-stagger-{stagger}">
    <div class="card-header">
      <span class="rank-badge">{rank}</span>
      <span class="category-tag" data-cat="{h(persp_cat)}">
        <span class="category-tag-dot"></span>
        {h(persp_label)}
      </span>
      {('<span class="card-source"><a href="' + h(url) + '" target="_blank" rel="noopener" class="footer-link">원문</a></span>') if url else ''}
    </div>

    <h2 class="card-title">
      {('<a href="' + h(url) + '" target="_blank" rel="noopener">' + h(title) + '</a>') if url else h(title)}
    </h2>
    <p class="card-description">{h(desc)}</p>

    <hr class="card-divider">

    <div class="pm-block">
      <div class="pm-block-head">
        <p class="pm-block-label">
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 20h9M16.5 3.5a2.121 2.121 0 013 3L7 19l-4 1 1-4L16.5 3.5z"/>
          </svg>
          PM 관점 의미
        </p>
      </div>
      <p class="pm-body">{h(short_term) if short_term else h(desc)}</p>
      {pm_extra}
    </div>

    <div class="op-grid">
      {opp_tile}
      {risk_tile}
    </div>

    <div class="action">
      <div class="action-check">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <path d="M20 6L9 17l-5-5"/>
        </svg>
      </div>
      <div class="action-body">
        <p class="action-label">이번 주 액션 아이템</p>
        <p class="action-text">{h(comment)}</p>
      </div>
    </div>

    <div class="card-footer">
      <div class="card-footer-meta">
        <span class="card-footer-meta-item">이슈 {rank}</span>
        {footer_link}
      </div>
    </div>
  </div>"""


# ── PM 종합 코멘트 ─────────────────────────────────────────────────────────────

def _render_pm_comment(issues: list[dict]) -> str:
    persp_map = {"competition": "경쟁 구도", "regulation": "규제 리스크", "ux_trend": "UX 트렌드"}
    perspectives = [persp_map.get(i.get("perspective", ""), "") for i in issues]
    persp_str    = " · ".join(p for p in perspectives if p)

    titles   = [i.get("title", "") for i in issues]
    t1       = titles[0][:25] if titles else ""
    t2       = titles[1][:25] if len(titles) > 1 else ""
    title_str = f"'{h(t1)}', '{h(t2)}'" if t2 else f"'{h(t1)}'"

    def _clean(c: str) -> str:
        return c.replace("PM이라면 ", "").rstrip(".")

    action_items = [_clean(i.get("one_line_comment", "")) for i in issues if i.get("one_line_comment")]

    items_html = "".join(
        f"""
        <li class="pm-comment-item">
          <span class="pm-comment-item-num">{idx}</span>
          <span>{h(txt)}.</span>
        </li>"""
        for idx, txt in enumerate(action_items, 1)
    )

    return f"""
  <section class="pm-comment">
    <p class="pm-comment-label">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/>
      </svg>
      PM 종합 코멘트
    </p>
    <p class="pm-comment-body">
      이번 주 핀테크 시장은 <strong>{h(persp_str)}</strong> 세 축이 동시에 움직인 주였습니다.
      {title_str} 등 굵직한 이슈가 맞물리며 시장 전반의 긴장감이 높아졌습니다.
      지금 이 시점에 PM이라면 다음에 집중해야 합니다.
    </p>
    <ul class="pm-comment-list">
      {items_html}
    </ul>
  </section>"""


# ── 전체 HTML 렌더러 ──────────────────────────────────────────────────────────

def render_html(analysis: dict) -> str:
    period        = analysis.get("period", {})
    start         = period.get("start", "")
    end           = period.get("end", "")
    weekly_sum    = analysis.get("weekly_summary", "")
    issues        = analysis.get("top_issues", [])
    analyzed_at   = analysis.get("analyzed_at", "")[:16].replace("T", " ")
    source_file   = analysis.get("source_file", "")
    total_articles = _parse_total_articles(source_file)
    next_monday   = _next_monday(end) if end else ""

    period_label  = f"{_fmt_date(start)} — {_fmt_date(end)}" if start else ""
    title_tag     = f"핀테크 PM 주간 인텔리전스 · {period_label}"

    cards_html = "".join(_render_card(issue, i) for i, issue in enumerate(issues))
    pm_html    = _render_pm_comment(issues)

    next_pub_str  = f"{_fmt_date(next_monday)}(월) 09:00" if next_monday else "매주 월요일 09:00"

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{h(title_tag)}</title>
  <style>
{_tokens_css()}
{_LAYOUT_CSS}
  </style>
</head>
<body>
<div class="page">

  <!-- ── Top bar ── -->
  <div class="topbar">
    <div class="topbar-brand">
      <span class="dot"></span>
      fintech-intelligence
    </div>
    <span style="font-size:var(--font-size-xs);color:var(--color-text-tertiary);">
      분석 {analyzed_at}
    </span>
  </div>

  <!-- ── Header ── -->
  <header class="header">
    <div class="header-period">{h(period_label)}</div>
    <h1 class="header-title">핀테크 PM<br>주간 인텔리전스</h1>
    <p class="header-summary">{h(weekly_sum)}</p>
  </header>

  <!-- ── Stats bar ── -->
  <div class="stats">
    <div class="stat">
      <p class="stat-label">📦 수집 기사</p>
      <p class="stat-value">{total_articles}<span class="unit">건</span></p>
    </div>
    <div class="stat">
      <p class="stat-label">🔥 주요 이슈</p>
      <p class="stat-value">{len(issues)}<span class="unit">건</span></p>
    </div>
    <div class="stat">
      <p class="stat-label">✅ 액션 아이템</p>
      <p class="stat-value">{len(issues)}<span class="unit">개</span></p>
    </div>
  </div>

  <!-- ── Issue cards ── -->
  <div class="section-head">
    <h2 class="section-title">
      <span class="section-title-num">{len(issues)}</span>
      TOP 이슈
    </h2>
  </div>

  {cards_html}

  <!-- ── PM 종합 코멘트 ── -->
  {pm_html}

  <!-- ── Footer ── -->
  <footer class="footer">
    <span>수집 기사 {total_articles}건 · 분석 시각 {h(analyzed_at)} · 다음 발행 {h(next_pub_str)}</span>
    <span>🤖 fintech-intelligence</span>
  </footer>

</div>
</body>
</html>"""


# ── 환경변수 로드 ─────────────────────────────────────────────────────────────

def _load_env() -> tuple[str, str]:
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    return os.environ.get("TELEGRAM_BOT_TOKEN", ""), os.environ.get("TELEGRAM_CHAT_ID", "")


# ── GitHub Pages URL 계산 ─────────────────────────────────────────────────────

def _github_pages_url(rel_path: str) -> str | None:
    """git remote URL에서 GitHub Pages URL을 자동 계산한다."""
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, cwd=str(PROJECT_ROOT),
        )
        remote = result.stdout.strip()
        # https://github.com/OWNER/REPO  또는  git@github.com:OWNER/REPO.git
        m = re.search(r"github\.com[:/]([^/]+)/([^/\n]+?)(?:\.git)?$", remote)
        if not m:
            return None
        owner, repo = m.group(1), m.group(2)
        return f"https://{owner}.github.io/{repo}/{rel_path}"
    except Exception:
        return None


# ── GitHub push ───────────────────────────────────────────────────────────────

def _push_to_github(out_path: Path) -> str | None:
    """HTML 파일을 main 브랜치에 커밋·푸시하고 GitHub Pages URL을 반환한다."""
    try:
        rel = out_path.relative_to(PROJECT_ROOT).as_posix()

        # 스테이징
        r = subprocess.run(
            ["git", "add", rel],
            cwd=str(PROJECT_ROOT), capture_output=True, text=True,
        )
        if r.returncode != 0:
            print(f"[html_reporter] git add 실패: {r.stderr.strip()}")
            return None

        # 변경사항 없으면 스킵
        diff = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=str(PROJECT_ROOT),
        )
        if diff.returncode == 0:
            print("[html_reporter] 변경 없음 — 동일 파일이 이미 커밋됨")
            return _github_pages_url(rel)

        # 커밋
        date_tag = out_path.stem.replace("brief_", "")
        r = subprocess.run(
            ["git", "commit", "-m", f"report: weekly brief {date_tag}"],
            cwd=str(PROJECT_ROOT), capture_output=True, text=True,
        )
        if r.returncode != 0:
            print(f"[html_reporter] git commit 실패: {r.stderr.strip()}")
            return None

        # main 브랜치에 push
        r = subprocess.run(
            ["git", "push", "origin", "HEAD:main"],
            cwd=str(PROJECT_ROOT), capture_output=True, text=True,
        )
        if r.returncode != 0:
            print(f"[html_reporter] git push 실패: {r.stderr.strip()}")
            return None

        url = _github_pages_url(rel)
        print(f"[html_reporter] GitHub push 완료 → {url}")
        return url

    except Exception as e:
        print(f"[html_reporter] push 오류: {e}")
        return None


# ── 텔레그램 링크 발송 ────────────────────────────────────────────────────────

def _send_telegram_link(token: str, chat_id: str, url: str, period_label: str) -> None:
    try:
        import requests
    except ImportError:
        print("[html_reporter] requests 없음 — 링크 발송 스킵")
        return

    text = (
        f"🌐 <b>HTML 브리핑 리포트</b>\n"
        f"<i>{period_label}</i>\n\n"
        f'<a href="{url}">📄 브라우저에서 보기 →</a>\n\n'
        f"<i>* GitHub Pages 배포 직후에는 1~2분 후 접속 가능합니다.</i>"
    )
    payload = json.dumps(
        {"chat_id": chat_id, "text": text, "parse_mode": "HTML",
         "disable_web_page_preview": False},
        ensure_ascii=False,
    ).encode("utf-8")
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=10,
        )
        r.raise_for_status()
        print(f"[html_reporter] 텔레그램 링크 발송 완료")
    except Exception as e:
        print(f"[html_reporter] 텔레그램 링크 발송 실패: {e}")


# ── 파일 저장 ─────────────────────────────────────────────────────────────────

def load_latest_analysis() -> dict:
    files = sorted((PROJECT_ROOT / "reports").glob("analysis_*.json"))
    if not files:
        raise FileNotFoundError("분석 파일 없음. analyst.py를 먼저 실행하세요.")
    return json.loads(files[-1].read_text(encoding="utf-8"))


def run() -> Path:
    token, chat_id = _load_env()

    analysis = load_latest_analysis()
    analyzed_at = analysis.get("analyzed_at", "")
    date_str = analyzed_at[:10].replace("-", "") if analyzed_at else \
               __import__("datetime").date.today().strftime("%Y%m%d")

    period  = analysis.get("period", {})
    period_label = f"{_fmt_date(period.get('start',''))} — {_fmt_date(period.get('end',''))}"

    HTML_OUT.mkdir(parents=True, exist_ok=True)
    out_path = HTML_OUT / f"brief_{date_str}.html"
    out_path.write_text(render_html(analysis), encoding="utf-8")
    print(f"[html_reporter] HTML 저장 완료: {out_path}")

    # GitHub push → 텔레그램 링크 발송
    url = _push_to_github(out_path)
    if url and token and chat_id:
        _send_telegram_link(token, chat_id, url, period_label)
    elif not url:
        print("[html_reporter] GitHub push 실패 — 텔레그램 링크 발송 스킵")

    return out_path


if __name__ == "__main__":
    run()
