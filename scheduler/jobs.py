
import json
import subprocess
import sys
import time

from pathlib import Path
from datetime import datetime, timezone
from apscheduler.schedulers.blocking import BlockingScheduler

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

RUN_LOG = LOG_DIR / "runs.jsonl"


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def run_collector(source, module):
    started_at = now_iso()
    start_time = time.time()

    print(f"Starting {source} collector...")

    status = "success"
    error = None

    try:
        result = subprocess.run(
            [sys.executable, "-m", module],
            capture_output=True,
            text=True,
            timeout=600
        )

        if result.stdout:
            print(result.stdout)

        if result.returncode != 0:
            status = "failed"
            error = result.stderr[-2000:]
            print(f"ERROR: {error}")

    except Exception as exc:
        status = "failed"
        error = str(exc)
        print(f"ERROR: {error}")

    duration = round(time.time() - start_time, 2)
    finished_at = now_iso()

    record = {
        "source": source,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_seconds": duration,
        "status": status,
        "error": error
    }

    with RUN_LOG.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(
        f"{source} completed | "
        f"Status: {status} | "
        f"Duration: {duration}s"
    )


def main():
    scheduler = BlockingScheduler(
        timezone="Asia/Bangkok"
    )
    run_collector("news", "collectors.news_collector")
    run_collector("youtube", "collectors.youtube_collector")

    scheduler.add_job(
        run_collector,
        "interval",
        minutes=5,
        args=["news", "collectors.news_collector"],
        id="news_job",
        max_instances=1,
        coalesce=True
    )

    scheduler.add_job(
        run_collector,
        "interval",
        hours=1,
        args=["youtube", "collectors.youtube_collector"],
        id="youtube_job",
        max_instances=1,
        coalesce=True
    )

    print("Scheduler started")
    print("News: every 5 minutes")
    print("YouTube: every 1 hour")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()


if __name__ == "__main__":
    main()
