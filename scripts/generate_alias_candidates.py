"""Generate dictionary alias candidates from unknown queue JSONL.

Usage:
  python scripts/generate_alias_candidates.py \
    --input /tmp/bean-lens-unknown.jsonl \
    --output data/review/alias_candidates.json
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

VALID_DOMAINS = {"process", "variety", "roast_level", "country", "flavor_note"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate alias candidates from unknown queue")
    parser.add_argument("--input", required=True, help="Path to unknown queue JSONL")
    parser.add_argument("--output", required=True, help="Path to output candidate JSON")
    parser.add_argument("--dictionary-version", default="v1", help="Dictionary version (default: v1)")
    parser.add_argument("--min-count", type=int, default=2, help="Minimum count to include candidate")
    parser.add_argument("--top", type=int, default=200, help="Maximum number of candidates to output")
    parser.add_argument(
        "--min-score",
        type=float,
        default=0.72,
        help="Minimum similarity score for suggested key",
    )
    parser.add_argument(
        "--include-low-confidence",
        action="store_true",
        help="Include low_confidence records in candidate generation",
    )
    return parser.parse_args()


def normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKC", value).lower().strip()
    text = text.replace("_", " ").replace("-", " ")
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text


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


def load_dictionary(version: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    base = ROOT / "src" / "bean_lens" / "normalization" / "data" / version
    terms_path = base / "terms.json"
    aliases_path = base / "aliases.json"
    if not terms_path.exists() or not aliases_path.exists():
        raise FileNotFoundError(f"Dictionary files not found for version '{version}' in {base}")

    terms = json.loads(terms_path.read_text(encoding="utf-8"))
    aliases = json.loads(aliases_path.read_text(encoding="utf-8"))
    return terms, aliases


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
    records = load_jsonl(Path(args.input))
    terms, aliases = load_dictionary(args.dictionary_version)

    existing_aliases: set[tuple[str, str]] = set()
    for alias in aliases:
        domain = alias.get("domain")
        value = alias.get("alias")
        if isinstance(domain, str) and isinstance(value, str):
            existing_aliases.add((domain, normalize_text(value)))

    grouped: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {
            "count": 0,
            "latest_ts": None,
            "reasons": Counter(),
            "methods": Counter(),
            "avg_confidence": 0.0,
        }
    )

    for row in records:
        domain = str(row.get("domain", "")).strip()
        raw = str(row.get("raw", "")).strip()
        reason = str(row.get("reason", ""))
        if domain not in VALID_DOMAINS or not raw:
            continue

        if reason == "low_confidence" and not args.include_low_confidence:
            continue

        key = (domain, raw)
        entry = grouped[key]
        entry["count"] += 1
        entry["reasons"][reason or "unknown"] += 1
        entry["methods"][str(row.get("method", "unknown"))] += 1

        conf = row.get("confidence")
        if isinstance(conf, (int, float)):
            prev_sum = entry["avg_confidence"] * (entry["count"] - 1)
            entry["avg_confidence"] = (prev_sum + float(conf)) / entry["count"]

        ts = row.get("ts")
        if isinstance(ts, str) and (entry["latest_ts"] is None or ts > entry["latest_ts"]):
            entry["latest_ts"] = ts

    candidates: list[dict[str, Any]] = []
    for (domain, raw), entry in grouped.items():
        if entry["count"] < args.min_count:
            continue

        already_exists = (domain, normalize_text(raw)) in existing_aliases
        best_key, best_score, best_label = best_term_match(terms, domain, raw)

        suggestion: dict[str, Any] | None = None
        if not already_exists and best_key and best_score >= args.min_score:
            suggestion = {
                "domain": domain,
                "key": best_key,
                "alias": raw,
                "match_type": "exact",
                "priority": 40,
            }

        candidates.append(
            {
                "domain": domain,
                "raw": raw,
                "count": entry["count"],
                "avg_confidence": round(entry["avg_confidence"], 4),
                "latest_ts": entry["latest_ts"],
                "top_reason": entry["reasons"].most_common(1)[0][0],
                "top_method": entry["methods"].most_common(1)[0][0],
                "already_exists": already_exists,
                "best_match": {
                    "key": best_key,
                    "label_en": best_label,
                    "score": best_score,
                },
                "suggested_alias": suggestion,
            }
        )

    candidates.sort(key=lambda item: (-item["count"], -item["best_match"]["score"], item["domain"], item["raw"]))
    limited = candidates[: args.top]

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(limited, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    summary = {
        "input_records": len(records),
        "grouped_candidates": len(candidates),
        "written_candidates": len(limited),
        "output": str(output_path),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
