# fintech-intelligence

> AI 자동화로 핀테크 시장을 모니터링하는 PM 인텔리전스 시스템

---

## 한국어

### 프로젝트 소개

**fintech-intelligence**는 Claude AI 에이전트가 매주 핀테크 시장 뉴스를 자동 수집·분석하고, PM이 즉시 활용할 수 있는 인사이트를 텔레그램으로 발송하는 자동화 인텔리전스 시스템입니다.

핀테크 PM이 놓치기 쉬운 신호들—빅테크 간 경쟁 구도 변화, 규제 리스크, UX 트렌드—을 매주 월요일 아침 브리핑 형태로 받아볼 수 있습니다.

### 파이프라인 구조

```
[매주 월요일 09:00]
        │
        ▼
┌─────────────────┐
│  news-collector │  간편결제·오픈뱅킹·BNPL 등 10개 키워드
│  (수집 에이전트) │  직전 주 월~일 기사 수집
└────────┬────────┘
         │ collected_YYYYMMDD_YYYYMMDD.json
         ▼
┌─────────────────┐
│  news-analyst   │  3가지 관점 분석:
│  (분석 에이전트) │  ① 빅테크 경쟁 구도
└────────┬────────┘  ② 규제/정책 리스크
         │           ③ UX 트렌드
         │ analysis_YYYYMMDD.json
         ▼           + Top 3 이슈 · 기회/리스크
┌─────────────────┐
│  news-reporter  │  HTML 포매팅 후
│  (발송 에이전트) │  텔레그램 발송
└─────────────────┘
```

### 핵심 기능

| 기능 | 설명 |
|------|------|
| 자동 수집 | 10개 핀테크 키워드로 주간 뉴스 자동 검색 |
| AI 분석 | 3가지 PM 관점으로 뉴스 분류 및 인사이트 도출 |
| Top 3 이슈 | 기회·리스크 매핑이 포함된 우선순위 이슈 정리 |
| 자동 발송 | 매주 월요일 9시 텔레그램 HTML 리포트 발송 |
| 실패 복원력 | 단계별 에러 처리 및 부분 실패 시 계속 진행 |

### 실행 방법

#### 1. 환경 설정

```bash
# 저장소 클론
git clone https://github.com/your-username/fintech-intelligence.git
cd fintech-intelligence

# 환경변수 설정
cp .env.example .env
# .env 파일에 TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID 입력

# 의존성 설치
pip install requests python-dateutil
```

#### 2. 텔레그램 봇 설정

1. 텔레그램에서 `@BotFather` 검색
2. `/newbot` 명령으로 봇 생성 → `TELEGRAM_BOT_TOKEN` 획득
3. 생성한 봇과 대화 시작 → `@userinfobot`에 메시지 보내 `TELEGRAM_CHAT_ID` 확인
4. `.env` 파일에 두 값 입력

#### 3. 실행

```bash
# 즉시 실행 (테스트)
python scripts/scheduler.py --run-now

# Windows 작업 스케줄러 등록 (매주 월요일 09:00 자동 실행)
python scripts/scheduler.py --register

# 스케줄러 직접 실행 (백그라운드 대기 모드)
python scripts/scheduler.py
```

### 디렉토리 구조

```
fintech-intelligence/
├── CLAUDE.md                     # 오케스트레이터: 전체 파이프라인 지휘
├── .claude/
│   └── agents/
│       ├── news-collector.md     # 서브 에이전트 1: 뉴스 수집
│       ├── news-analyst.md       # 서브 에이전트 2: AI 분석
│       └── news-reporter.md      # 서브 에이전트 3: 텔레그램 발송
├── templates/
│   └── design.md                 # 텔레그램 HTML 메시지 템플릿
├── scripts/
│   └── scheduler.py              # 주간 자동 실행 스케줄러
├── reports/
│   ├── collected/                # 수집 원본 JSON (gitignore)
│   └── analysis_YYYYMMDD.json   # 분석 결과 JSON (gitignore)
├── .env.example                  # 환경변수 샘플
└── README.md
```

### 포트폴리오 어필 포인트

> **AI 자동화 + 데이터 기반 시장 분석 + PM 관점 인사이트 도출**

- **오케스트레이터-서브에이전트 아키텍처**: Claude AI의 멀티 에이전트 구조를 활용한 역할 분리 설계
- **PM 관점의 분석 프레임워크**: 단순 뉴스 요약이 아닌, 경쟁·규제·UX 3축으로 구조화된 인사이트
- **프로덕션 수준의 에러 처리**: 단계별 실패 지점 명시 및 부분 실패 시 파이프라인 계속 실행
- **실용적인 자동화**: Windows 작업 스케줄러 연동으로 완전 자동화 달성

---

## English

### Project Overview

**fintech-intelligence** is an automated PM intelligence system where Claude AI agents automatically collect and analyze weekly fintech market news, then deliver actionable insights to a Telegram channel every Monday morning.

This system captures signals that fintech PMs often miss—big tech competitive dynamics, regulatory risks, and UX trends—and packages them as a structured weekly briefing.

### Pipeline Architecture

```
[Every Monday at 09:00 KST]
           │
           ▼
  ┌─────────────────┐
  │  news-collector │  10 fintech keywords (mobile pay, open banking,
  │  (Collector)    │  BNPL, Toss, KakaoPay, NaverPay, SamsungPay...)
  └────────┬────────┘  Collects articles from the previous Mon–Sun
           │ collected_YYYYMMDD_YYYYMMDD.json
           ▼
  ┌─────────────────┐
  │  news-analyst   │  3-lens analysis:
  │  (Analyst)      │  ① Big-tech fintech competition
  └────────┬────────┘  ② Regulatory/policy risk
           │           ③ UX trends
           │ analysis_YYYYMMDD.json
           ▼           + Top 3 issues with Opportunity/Risk mapping
  ┌─────────────────┐
  │  news-reporter  │  HTML formatting →
  │  (Reporter)     │  Telegram message delivery
  └─────────────────┘
```

### Key Features

| Feature | Description |
|---------|-------------|
| Auto Collection | Weekly news search across 10 fintech keywords |
| AI Analysis | PM-perspective analysis across 3 strategic lenses |
| Top 3 Issues | Prioritized issues with opportunity & risk mapping |
| Auto Delivery | Every Monday at 9AM KST via Telegram HTML report |
| Resilience | Step-by-step error handling with partial failure recovery |

### Getting Started

#### 1. Setup

```bash
git clone https://github.com/your-username/fintech-intelligence.git
cd fintech-intelligence

cp .env.example .env
# Fill in TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env

pip install requests python-dateutil
```

#### 2. Telegram Bot Setup

1. Search for `@BotFather` on Telegram
2. Use `/newbot` to create a bot → get `TELEGRAM_BOT_TOKEN`
3. Start a conversation with your bot → message `@userinfobot` for `TELEGRAM_CHAT_ID`
4. Add both values to your `.env` file

#### 3. Run

```bash
# Immediate run (for testing)
python scripts/scheduler.py --run-now

# Register with Windows Task Scheduler (auto-runs every Monday at 09:00)
python scripts/scheduler.py --register

# Run scheduler in waiting mode
python scripts/scheduler.py
```

### Portfolio Highlights

> **AI Automation + Data-Driven Market Analysis + PM-Perspective Insight Generation**

- **Orchestrator-SubAgent Architecture**: Role-separated multi-agent design leveraging Claude AI's agentic capabilities
- **PM-Structured Analysis Framework**: Not just news summaries — structured insights across competition, regulation, and UX axes
- **Production-Grade Error Handling**: Step-level failure points documented with partial-failure recovery
- **Full Automation**: Windows Task Scheduler integration for zero-touch weekly delivery

### Tech Stack

- **AI**: Claude Code (Anthropic) — multi-agent orchestration
- **Delivery**: Telegram Bot API (HTML parse mode)
- **Scheduling**: Python scheduler + Windows Task Scheduler
- **Storage**: JSON flat files (no database required)

---

*Built as a PM portfolio project demonstrating AI-native workflow automation in the fintech domain.*
