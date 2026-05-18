# -*- coding: utf-8 -*-
"""
fintech-intelligence 주간 스케줄러
매주 월요일 09:00 (KST) 에 파이프라인을 자동 실행합니다.

실행 방법:
  python -X utf8 scripts/scheduler.py              # 스케줄러 시작 (백그라운드 대기)
  python -X utf8 scripts/scheduler.py --run-now    # 즉시 1회 실행 (테스트용)
  python -X utf8 scripts/scheduler.py --register   # Windows 작업 스케줄러 등록
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
PYTHON = sys.executable


def load_env() -> None:
    env_file = PROJECT_ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def run_script(script: str) -> bool:
    """scripts/ 아래 Python 스크립트를 subprocess로 실행한다."""
    path = PROJECT_ROOT / "scripts" / script
    result = subprocess.run(
        [PYTHON, "-X", "utf8", str(path)],
        cwd=str(PROJECT_ROOT),
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )
    return result.returncode == 0


def run_pipeline() -> bool:
    load_env()

    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'='*50}")
    print(f"[{now} KST] 파이프라인 시작")
    print(f"{'='*50}\n")

    # STEP 1: 수집
    print("[STEP 1] collector.py 실행 중...")
    if not run_script("collector.py"):
        print("[FAIL] STEP 1 실패 - 파이프라인 중단")
        return False
    print("[OK] STEP 1 완료\n")

    # STEP 2: 분석
    print("[STEP 2] analyst.py 실행 중...")
    if not run_script("analyst.py"):
        print("[FAIL] STEP 2 실패 - 파이프라인 중단")
        return False
    print("[OK] STEP 2 완료\n")

    # STEP 3: 텔레그램 발송
    print("[STEP 3] reporter.py 실행 중...")
    if not run_script("reporter.py"):
        print("[FAIL] STEP 3 실패 - 발송 오류")
        return False
    print("[OK] STEP 3 완료\n")

    # STEP 4: HTML 브리핑 파일 저장
    print("[STEP 4] html_reporter.py 실행 중...")
    if not run_script("html_reporter.py"):
        print("[WARN] STEP 4 실패 - HTML 저장 오류 (파이프라인은 계속)")
    else:
        print("[OK] STEP 4 완료\n")

    print(f"{'='*50}")
    print("[SUCCESS] 전체 파이프라인 완료")
    print(f"{'='*50}\n")
    return True


def register_windows_task() -> None:
    task_name = "FintechIntelligenceWeekly"
    script_path = (PROJECT_ROOT / "scripts" / "scheduler.py").resolve()
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
      <Command>{PYTHON}</Command>
      <Arguments>-X utf8 "{script_path}" --run-now</Arguments>
      <WorkingDirectory>{PROJECT_ROOT}</WorkingDirectory>
    </Exec>
  </Actions>
  <Settings>
    <ExecutionTimeLimit>PT1H</ExecutionTimeLimit>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
  </Settings>
</Task>"""

    xml_path = PROJECT_ROOT / "scripts" / f"{task_name}.xml"
    xml_path.write_text(xml_content, encoding="utf-16")
    result = subprocess.run(
        ["schtasks", "/create", "/tn", task_name, "/xml", str(xml_path), "/f"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        print(f"[OK] Windows 작업 스케줄러 등록 완료: '{task_name}'")
        xml_path.unlink(missing_ok=True)
    else:
        print(f"[ERROR] 등록 실패:\n{result.stderr}")


def wait_for_monday_9am() -> None:
    print("[스케줄러] 다음 월요일 09:00 KST 대기 중... (Ctrl+C로 중단)")
    while True:
        now = datetime.now(KST)
        days = (7 - now.weekday()) % 7 or 7
        target = (now + timedelta(days=days)).replace(hour=9, minute=0, second=0, microsecond=0)
        wait = (target - now).total_seconds()
        print(f"  다음 실행: {target.strftime('%Y-%m-%d %H:%M:%S KST')} ({wait/3600:.1f}시간 후)")
        time.sleep(min(wait, 3600))
        now = datetime.now(KST)
        if now.weekday() == 0 and now.hour == 9 and now.minute < 5:
            run_pipeline()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-now", action="store_true")
    parser.add_argument("--register", action="store_true")
    args = parser.parse_args()

    if args.run_now:
        sys.exit(0 if run_pipeline() else 1)
    elif args.register:
        register_windows_task()
    else:
        wait_for_monday_9am()
