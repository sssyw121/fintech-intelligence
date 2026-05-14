# fintech-intelligence — 메인 오케스트레이터

## 프로젝트 개요

핀테크 시장 동향을 자동으로 수집·분석·발송하는 주간 인텔리전스 파이프라인.
매주 월요일 09:00에 `scripts/scheduler.py`가 트리거되어 3개 서브 에이전트를 순차 실행한다.

```
[scheduler.py]
      │
      ▼
[1] news-collector   →  ./reports/collected/collected_YYYYMMDD_YYYYMMDD.json
      │
      ▼
[2] news-analyst     →  ./reports/analysis_YYYYMMDD.json
      │
      ▼
[3] news-reporter    →  텔레그램 HTML 메시지 발송
```

---

## 파이프라인 단계별 상세

### STEP 1 — 뉴스 수집 (`news-collector`)

**입력**: 없음 (실행 날짜 기준 자동 계산)  
**출력**: `./reports/collected/collected_YYYYMMDD_YYYYMMDD.json`

**수행 작업**
- 실행일 기준 직전 월요일~일요일 날짜 범위 계산
- 키워드 10개(`간편결제`, `오픈뱅킹`, `마이데이터`, `BNPL`, `토스`, `카카오페이`, `네이버페이`, `삼성페이`, `핀테크 규제`, `금융 AI`)로 웹 검색
- 기사 메타데이터(제목, URL, 날짜, 요약) 수집 및 JSON 저장

**실패 지점**
| 지점 | 원인 | 대응 |
|------|------|------|
| 검색 API 불응답 | 네트워크/할당량 | 3회 재시도 후 부분 결과로 진행 |
| 날짜 계산 오류 | 월요일 당일 실행 시 엣지케이스 | 당일이 월요일이면 이전 주 월~일 사용 |
| 파일 저장 실패 | 디렉토리 미존재 | `reports/collected/` 자동 생성 |

---

### STEP 2 — 뉴스 분석 (`news-analyst`)

**입력**: `./reports/collected/collected_YYYYMMDD_YYYYMMDD.json`  
**출력**: `./reports/analysis_YYYYMMDD.json`

**수행 작업**
- 수집된 기사를 3가지 관점으로 분석
  1. 빅테크 핀테크 서비스 경쟁 구도 변화
  2. 규제/정책 리스크
  3. 사용자 경험/UX 트렌드
- Top 3 이슈 선정 + 각 이슈별 기회(Opportunity) / 리스크(Risk) 도출
- 분석 결과 JSON 저장

**실패 지점**
| 지점 | 원인 | 대응 |
|------|------|------|
| 수집 파일 없음 | STEP 1 실패 | 오류 메시지 후 파이프라인 중단 |
| 기사 수 부족 (< 5건) | 검색 결과 빈약 | 경고 포함 후 가용 기사로 진행 |
| 분석 품질 저하 | LLM 응답 불안정 | 재시도 1회 후 결과 저장 |

---

### STEP 3 — 리포트 발송 (`news-reporter`)

**입력**: `./reports/analysis_YYYYMMDD.json`  
**출력**: 텔레그램 채널 HTML 메시지

**수행 작업**
- `templates/design.md` 템플릿 로드
- 분석 JSON → HTML 메시지 포매팅
- `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` 환경변수로 발송

**실패 지점**
| 지점 | 원인 | 대응 |
|------|------|------|
| 분석 파일 없음 | STEP 2 실패 | 오류 메시지 후 중단 |
| 텔레그램 API 오류 | 토큰 만료/잘못된 Chat ID | 오류 로그 출력 후 종료 |
| 메시지 길이 초과 | Telegram 4096자 제한 | 자동 분할 발송 |
| 환경변수 미설정 | `.env` 누락 | 명확한 오류 메시지 출력 |

---

## 환경 설정

```bash
# 환경변수 설정
cp .env.example .env
# .env에 TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID 입력

# 의존성 설치
pip install -r requirements.txt

# 수동 실행 (테스트용)
python scripts/scheduler.py --run-now

# 스케줄러 등록 (Windows Task Scheduler)
python scripts/scheduler.py --register
```

## 디렉토리 구조

```
fintech-intelligence/
├── CLAUDE.md                     # 오케스트레이터 (이 파일)
├── .claude/
│   └── agents/
│       ├── news-collector.md     # 서브 에이전트 1: 수집
│       ├── news-analyst.md       # 서브 에이전트 2: 분석
│       └── news-reporter.md      # 서브 에이전트 3: 발송
├── templates/
│   └── design.md                 # 텔레그램 HTML 템플릿
├── scripts/
│   └── scheduler.py              # 주간 자동 실행 스케줄러
├── reports/
│   ├── collected/                # 수집 원본 JSON
│   └── analysis_YYYYMMDD.json   # 분석 결과 JSON
├── .env.example                  # 환경변수 샘플
├── .gitignore
└── README.md
```
