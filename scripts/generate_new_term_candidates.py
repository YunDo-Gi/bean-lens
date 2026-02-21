"""Generate new canonical term candidates from unknown queue events.

This script is conservative: it only proposes review candidates and does not
modify dictionary files.
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
VALID_DOMAINS = {"process", "variety", "roast_level", "country", "flavor_note"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate new term candidates from unknown queue")
    parser.add_argument("--input", help="Path to unknown queue JSONL")
    parser.add_argument("--database-url", help="PostgreSQL DATABASE_URL for receiver DB")
    parser.add_argument("--days", type=int, default=7, help="Lookback window in days (default: 7)")
    parser.add_argument("--dictionary-version", default="v1", help="Dictionary version (default: v1)")
    parser.add_argument("--min-count", type=int, default=3, help="Minimum count to include (default: 3)")
    parser.add_argument(
        "--max-best-score",
        type=float,
        default=0.87,
        help="Only include rows whose best dictionary similarity is <= this score (default: 0.87)",
    )
    parser.add_argument("--top", type=int, default=200, help="Maximum output rows")
    parser.add_argument("--output", required=True, help="Path to output JSON")
    return parser.parse_args()


def normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKC", value).lower().strip()
    text = text.replace("_", " ").replace("-", " ")
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text


def is_single_value(raw: str) -> bool:
    return not any(sep in raw for sep in [",", "\n", ";", "/", "|", "·", "、"])


def parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str) and value:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def load_postgres(database_url: str) -> list[dict[str, Any]]:
    try:
        import psycopg
        from psycopg.rows import dict_row
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("psycopg is required for --database-url mode") from exc

    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select ts, domain, raw, confidence, reason, method, normalized_key, dictionary_version
                from unknown_queue_events
                """
            )
            rows = cur.fetchall()
    return [dict(row) for row in rows]


def load_terms(version: str) -> list[dict[str, Any]]:
    path = ROOT / "src" / "bean_lens" / "normalization" / "data" / version / "terms.json"
    if not path.exists():
        raise FileNotFoundError(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise RuntimeError("Invalid terms.json format")
    return data


def best_term_match(terms: list[dict[str, Any]], domain: str, raw: str) -> tuple[str | None, float, str | None]:
    normalized_raw = normalize_text(raw)
    best_score = 0.0
    best_key: str | None = None
    best_label: str | None = None
    for term in terms:
        if term.get("domain") != domain:
            continue
        for candidate in (term.get("key"), term.get("label_en"), term.get("label_ko")):
            if not isinstance(candidate, str):
                continue
            score = SequenceMatcher(None, normalized_raw, normalize_text(candidate)).ratio()
            if score > best_score:
                best_score = score
                best_key = term.get("key")
                best_label = term.get("label_en")
    return best_key, round(best_score, 4), best_label


def main() -> int:
    args = parse_args()
    if bool(args.input) == bool(args.database_url):
        raise SystemExit("Provide exactly one source: --input or --database-url")

    rows = load_jsonl(Path(args.input)) if args.input else load_postgres(args.database_url)
    since_utc = datetime.now(timezone.utc) - timedelta(days=args.days)
    terms = load_terms(args.dictionary_version)

    grouped: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {
            "count": 0,
            "latest_ts": None,
            "reasons": Counter(),
            "methods": Counter(),
            "avg_confidence": 0.0,
        }
    )

    for row in rows:
        ts = parse_datetime(row.get("ts"))
        if ts is None or ts < since_utc:
            continue
        domain = str(row.get("domain", "")).strip()
        raw = str(row.get("raw", "")).strip()
        if domain not in VALID_DOMAINS or not raw or not is_single_value(raw):
            continue

        key = (domain, raw)
        entry = grouped[key]
        entry["count"] += 1
        entry["reasons"][str(row.get("reason", "unknown"))] += 1
        entry["methods"][str(row.get("method", "unknown"))] += 1
        conf = row.get("confidence")
        if isinstance(conf, (int, float)):
            prev_sum = entry["avg_confidence"] * (entry["count"] - 1)
            entry["avg_confidence"] = (prev_sum + float(conf)) / entry["count"]
        ts_s = row.get("ts")
        if isinstance(ts_s, str) and (entry["latest_ts"] is None or ts_s > entry["latest_ts"]):
            entry["latest_ts"] = ts_s

    candidates: list[dict[str, Any]] = []
    for (domain, raw), entry in grouped.items():
        if entry["count"] < args.min_count:
            continue
        best_key, best_score, best_label = best_term_match(terms, domain, raw)
        if best_score > args.max_best_score:
            continue

        suggested_key = normalize_text(raw).replace(" ", "_")
        candidates.append(
            {
                "domain": domain,
                "raw": raw,
                "count": entry["count"],
                "avg_confidence": round(entry["avg_confidence"], 4),
                "latest_ts": entry["latest_ts"],
                "top_reason": entry["reasons"].most_common(1)[0][0],
                "top_method": entry["methods"].most_common(1)[0][0],
                "best_match": {
                    "key": best_key,
                    "label_en": best_label,
                    "score": best_score,
                },
                "suggested_term_template": {
                    "domain": domain,
                    "key": suggested_key,
                    "label_en": raw,
                    "label_ko": raw,
                },
            }
        )

    candidates.sort(key=lambda item: (-item["count"], item["best_match"]["score"], item["domain"], item["raw"]))
    limited = candidates[: args.top]

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(limited, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "input_records": len(rows),
                "grouped_candidates": len(candidates),
                "written_candidates": len(limited),
                "output": str(output_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
