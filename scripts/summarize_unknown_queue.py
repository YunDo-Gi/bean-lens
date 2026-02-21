"""Summarize unknown queue JSONL records.

Usage:
  python scripts/summarize_unknown_queue.py --input /tmp/bean-lens-unknown.jsonl
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize unknown queue records")
    parser.add_argument("--input", required=True, help="Path to unknown queue JSONL file")
    parser.add_argument("--top", type=int, default=50, help="Top records to show (default: 50)")
    parser.add_argument(
        "--format",
        choices=["json", "table"],
        default="table",
        help="Output format (default: table)",
    )
    parser.add_argument("--output", help="Optional output file path")
    return parser.parse_args()


def load_records(path: Path) -> list[dict]:
    if not path.exists():
        return []

    records: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def summarize(records: list[dict]) -> list[dict]:
    grouped: dict[tuple[str, str], dict] = defaultdict(
        lambda: {
            "count": 0,
            "latest_ts": None,
            "reason": None,
            "method": None,
            "avg_confidence": 0.0,
        }
    )

    for record in records:
        domain = str(record.get("domain", ""))
        raw = str(record.get("raw", ""))
        if not domain or not raw:
            continue

        key = (domain, raw)
        entry = grouped[key]
        entry["count"] += 1
        entry["reason"] = record.get("reason")
        entry["method"] = record.get("method")

        conf = record.get("confidence")
        if isinstance(conf, (int, float)):
            prev_sum = entry["avg_confidence"] * (entry["count"] - 1)
            entry["avg_confidence"] = (prev_sum + float(conf)) / entry["count"]

        ts = record.get("ts")
        if isinstance(ts, str) and (entry["latest_ts"] is None or ts > entry["latest_ts"]):
            entry["latest_ts"] = ts

    rows: list[dict] = []
    for (domain, raw), entry in grouped.items():
        rows.append(
            {
                "domain": domain,
                "raw": raw,
                "count": entry["count"],
                "reason": entry["reason"],
                "method": entry["method"],
                "avg_confidence": round(entry["avg_confidence"], 4),
                "latest_ts": entry["latest_ts"],
            }
        )

    rows.sort(key=lambda row: (-row["count"], row["domain"], row["raw"]))
    return rows


def render_table(rows: list[dict], top: int) -> str:
    head = "count | domain | raw | reason | method | avg_confidence | latest_ts"
    sep = "--- | --- | --- | --- | --- | --- | ---"
    lines = [head, sep]
    for row in rows[:top]:
        lines.append(
            f"{row['count']} | {row['domain']} | {row['raw']} | "
            f"{row['reason']} | {row['method']} | {row['avg_confidence']} | {row['latest_ts']}"
        )
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    path = Path(args.input)
    records = load_records(path)
    rows = summarize(records)

    if args.format == "json":
        output = json.dumps(rows[: args.top], ensure_ascii=False, indent=2)
    else:
        output = render_table(rows, args.top)

    if args.output:
        Path(args.output).write_text(output + "\n", encoding="utf-8")
    else:
        print(output)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
