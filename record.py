import argparse
import csv
import os
import signal
import sys
import time
from datetime import date

from logger import get_power_info

DEFAULT_INTERVAL = 5
DEFAULT_FLUSH_INTERVAL = 30
DEFAULT_OUTPUT_DIR = os.path.expanduser("~/power-log")
HEADER = ["timestamp", "energy_rate_w", "percentage", "state", "charger_type"]


def run(interval, output_dir, flush_interval):
    os.makedirs(output_dir, exist_ok=True)

    buffer = []
    current_date = date.today()
    running = True

    def flush():
        nonlocal current_date
        if not buffer:
            return
        path = os.path.join(output_dir, f"{current_date}.csv")
        exists = os.path.exists(path)
        with open(path, "a") as f:
            writer = csv.writer(f)
            if not exists:
                writer.writerow(HEADER)
            writer.writerows(buffer)
        buffer.clear()

    def shutdown(signum, frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    next_tick = time.monotonic()
    last_flush = next_tick

    while running:
        now = time.monotonic()
        delay = next_tick - now
        if delay > 0:
            time.sleep(delay)

        info = get_power_info()
        row_date = date.fromtimestamp(info[0])

        if row_date != current_date:
            flush()
            current_date = row_date

        buffer.append(info)

        now = time.monotonic()
        if now - last_flush >= flush_interval:
            flush()
            last_flush = now

        next_tick += interval

    flush()


def main():
    parser = argparse.ArgumentParser(description="Log power stats to CSV")
    parser.add_argument(
        "--interval", "-i",
        type=float,
        default=DEFAULT_INTERVAL,
        help=f"Logging interval in seconds (default: {DEFAULT_INTERVAL})",
    )
    parser.add_argument(
        "--flush-interval", "-f",
        type=float,
        default=DEFAULT_FLUSH_INTERVAL,
        help=f"How often to flush buffer to disk in seconds (default: {DEFAULT_FLUSH_INTERVAL})",
    )
    parser.add_argument(
        "--output-dir", "-o",
        default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory for CSV files (default: {DEFAULT_OUTPUT_DIR})",
    )
    args = parser.parse_args()
    run(args.interval, args.output_dir, args.flush_interval)


if __name__ == "__main__":
    main()
