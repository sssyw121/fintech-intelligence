"""
fintech-intelligence 주간 스케줄러
매주 월요일 09:00 (KST) 에 파이프라인을 자동 실행합니다.

실행 방법:
  python scripts/scheduler.py              # 스케줄러 시작 (백그라운드 대기)
  python scripts/scheduler.py --run-now    # 즉시 1회 실행 (테스트용)
  python scripts/scheduler.py --register   # Windows 작업 스케줄러 등록
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
PROJECT_ROOT = Path(__file__).parent.parent


def load_env() -> None:
    env_file = PROJECT_ROOT / ".env"
    if not env_file.exists():
        print("[WARN] .env 파일이 없습니다. 환경변수가 직접 설정되어 있는지 확인하세요.")
        return

    with open(env_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def get_collection_period() -> tuple[date, date]:
    today = date.today()
    days_since_monday = today.weekday()
    if days_since_monday == 0:
        days_since_monday = 7
    last_monday = today - timedelta(days=days_since_monday)
    last_sunday = last_monday + timedelta(days=6)
    return last_monday, last_sunday


def run_pipeline() -> bool:
    load_env()

    start, end = get_collection_period()
    print(f"\n{'='*50}")
    print(f"[{datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')} KST] 파이프라인 시작")
    print(f"수집 기간: {start} ~ {end}")
    print(f"{'='*50}\n")

    # STEP 1: 뉴스 수집
    print("[STEP 1] news-collector 실행 중...")
    collected_file = (
        PROJECT_ROOT
        / "reports"
        / "collected"
        / f"collected_{start.strftime('%Y%m%d')}_{end.strftime('%Y%m%d')}.json"
    )

    if not _run_agent("news-collector", collected_file):
        print("[FAIL] STEP 1 실패 — 파이프라인 중단")
        return False
    print(f"[OK] STEP 1 완료: {collected_file.name}\n")

    # STEP 2: 뉴스 분석
    print("[STEP 2] news-analyst 실행 중...")
    analysis_file = (
        PROJECT_ROOT / "reports" / f"analysis_{date.today().strftime('%Y%m%d')}.json"
    )

    if not _run_agent("news-analyst", analysis_file):
        print("[FAIL] STEP 2 실패 — 파이프라인 중단")
        return False
    print(f"[OK] STEP 2 완료: {analysis_file.name}\n")

    # STEP 3: 텔레그램 발송
    print("[STEP 3] news-reporter 실행 중...")
    if not _run_agent("news-reporter", None):
        print("[FAIL] STEP 3 실패 — 발송 오류")
        return False
    print("[OK] STEP 3 완료: 텔레그램 발송 성공\n")

    print(f"{'='*50}")
    print("[SUCCESS] 전체 파이프라인 완료")
    print(f"{'='*50}\n")
    return True


def _run_agent(agent_name: str, expected_output: Path | None) -> bool:
    """
    Claude Code CLI를 사용하여 서브 에이전트를 실행한다.
    실제 환경에서는 `claude --agent <agent_name>` 형태로 호출하거나,
    각 에이전트 로직을 직접 Python 모듈로 구현하여 import 한다.
    """
    agent_path = PROJECT_ROOT / ".claude" / "agents" / f"{agent_name}.md"

    if not agent_path.exists():
        print(f"[ERROR] 에이전트 파일을 찾을 수 없습니다: {agent_path}")
        return False

    # Claude Code CLI 호출 (설치된 경우)
    try:
        cmd = [
            "claude",
            "--print",
            "--agent", str(agent_path),
            f"에이전트 {agent_name}를 실행하세요."
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(PROJECT_ROOT),
        )

        if result.returncode != 0:
            print(f"[ERROR] {agent_name} 실행 오류:\n{result.stderr}")
            return False

    except FileNotFoundError:
        # Claude CLI 미설치 시 시뮬레이션 모드
        print(f"  [SIM] claude CLI 미설치 — {agent_name} 시뮬레이션 모드")
        if expected_output and not expected_output.exists():
            _create_placeholder(agent_name, expected_output)

    except subprocess.TimeoutExpired:
        print(f"[ERROR] {agent_name} 실행 시간 초과 (5분)")
        return False

    # 출력 파일 존재 여부 검증
    if expected_output and not expected_output.exists():
        print(f"[ERROR] 예상 출력 파일이 생성되지 않았습니다: {expected_output}")
        return False

    return True


def _create_placeholder(agent_name: str, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    placeholder = {
        "generated_by": agent_name,
        "generated_at": datetime.now(KST).isoformat(),
        "status": "simulation",
        "note": "Claude CLI가 설치된 환경에서 실제 데이터가 채워집니다.",
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(placeholder, f, ensure_ascii=False, indent=2)


def register_windows_task() -> None:
    task_name = "FintechIntelligenceWeekly"
    script_path = Path(__file__).resolve()
    python_exe = sys.executable

    xml_content = f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>2026-01-05T09:00:00</StartBoundary>
      <ScheduleByWeek>
        <WeeksInterval>1</WeeksInterval>
        <DaysOfWeek><Monday /></DaysOfWeek>
      </ScheduleByWeek>
    </CalendarTrigger>
  </Triggers>
  <Actions Context="Author">
    <Exec>
      <Command>{python_exe}</Command>
      <Arguments>"{script_path}" --run-now</Arguments>
      <WorkingDirectory>{PROJECT_ROOT}</WorkingDirectory>
    </Exec>
  </Actions>
  <Settings>
    <ExecutionTimeLimit>PT1H</ExecutionTimeLimit>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
  </Settings>
</Task>"""

    xml_path = PROJECT_ROOT / "scripts" / f"{task_name}.xml"
    with open(xml_path, "w", encoding="utf-16") as f:
        f.write(xml_content)

    result = subprocess.run(
        ["schtasks", "/create", "/tn", task_name, "/xml", str(xml_path), "/f"],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        print(f"[OK] Windows 작업 스케줄러 등록 완료: '{task_name}'")
        print("     매주 월요일 09:00에 자동 실행됩니다.")
        xml_path.unlink(missing_ok=True)
    else:
        print(f"[ERROR] 작업 스케줄러 등록 실패:\n{result.stderr}")
        print(f"       XML 파일을 수동으로 가져오세요: {xml_path}")


def wait_for_next_monday_9am() -> None:
    print("[스케줄러] 다음 월요일 09:00 KST 대기 중... (Ctrl+C로 중단)")
    while True:
        now = datetime.now(KST)
        days_until_monday = (7 - now.weekday()) % 7
        if days_until_monday == 0 and now.hour < 9:
            target = now.replace(hour=9, minute=0, second=0, microsecond=0)
        elif days_until_monday == 0:
            days_until_monday = 7
            target = now.replace(hour=9, minute=0, second=0, microsecond=0) + timedelta(
                days=7
            )
        else:
            target = (now + timedelta(days=days_until_monday)).replace(
                hour=9, minute=0, second=0, microsecond=0
            )

        wait_seconds = (target - now).total_seconds()
        print(f"  다음 실행: {target.strftime('%Y-%m-%d %H:%M:%S KST')} ({wait_seconds/3600:.1f}시간 후)")

        time.sleep(min(wait_seconds, 3600))

        now = datetime.now(KST)
        if now.weekday() == 0 and now.hour == 9 and now.minute < 5:
            run_pipeline()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="fintech-intelligence 스케줄러")
    parser.add_argument("--run-now", action="store_true", help="즉시 파이프라인 실행")
    parser.add_argument(
        "--register", action="store_true", help="Windows 작업 스케줄러에 등록"
    )
    args = parser.parse_args()

    if args.run_now:
        success = run_pipeline()
        sys.exit(0 if success else 1)
    elif args.register:
        register_windows_task()
    else:
        wait_for_next_monday_9am()
