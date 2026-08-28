"""Create deterministic weekly checkpoints for any requested backfill range."""
import argparse
import json
import pathlib
from datetime import date, timedelta


def weekly_partitions(start, end):
    first = date.fromisoformat(start)
    last = date.fromisoformat(end)
    if first > last:
        raise ValueError("Backfill start must not be after end")
    parts = []
    cursor = first
    while cursor <= last:
        week_end = cursor + timedelta(days=6 - cursor.weekday())
        partition_end = min(last, week_end)
        parts.append({"label": f"{cursor.isoformat()}_to_{partition_end.isoformat()}", "start": cursor.isoformat(), "end": partition_end.isoformat()})
        cursor = partition_end + timedelta(days=1)
    return parts


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--github-output")
    args = parser.parse_args()
    value = json.dumps(weekly_partitions(args.start, args.end), separators=(",", ":"))
    if args.github_output:
        with pathlib.Path(args.github_output).open("a") as handle:
            handle.write(f"matrix={value}\n")
    else:
        print(value)
