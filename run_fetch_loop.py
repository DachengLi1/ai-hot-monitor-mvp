#!/usr/bin/env python3
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from fetch_sources import FETCH_INTERVAL_MINUTES, run_once

ROOT = Path(__file__).resolve().parent


def update_token_usage():
    script = ROOT / "update_token_usage.py"
    if not script.exists():
        return
    try:
        subprocess.run([sys.executable, str(script)], cwd=str(ROOT), timeout=180, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as exc:
        print(f"[loop] token usage update failed: {exc}", flush=True)


def main():
    print(f"[loop] AI Hot Monitor fetch loop started. Interval = {FETCH_INTERVAL_MINUTES} minutes.", flush=True)
    while True:
        cycle_started = datetime.now()
        try:
            dashboard = run_once()
            update_token_usage()
            print(
                f"[loop] fetch complete @ {dashboard['generated_at']} | total_items={dashboard['stats']['total_items']} | sources_ok={dashboard['stats']['sources_ok']}/{dashboard['stats']['sources_total']}",
                flush=True,
            )
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            print(f"[loop] fetch failed: {exc}", flush=True)

        next_run = cycle_started + timedelta(minutes=FETCH_INTERVAL_MINUTES)
        print(f"[loop] next fetch around {next_run.isoformat(timespec='seconds')}", flush=True)

        for _ in range(FETCH_INTERVAL_MINUTES * 60):
            time.sleep(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("[loop] stopped", flush=True)
        sys.exit(0)
