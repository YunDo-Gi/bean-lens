"""Apply safe alias candidates to normalization dictionary.

This script intentionally applies only conservative alias updates:
- exact match aliases only
- must point to existing term key
- flavor_note domain is strict: typo-only candidates

Example:
  python scripts/apply_dictionary_candidates.py \
    --input data/review/alias_candidates.auto.json \
    --dictionary-version v1 \
    --min-count 3 \
    --min-score 0.9
"""

from __future__ import annotations

import argparse
import json
import re
import runpy
import unicodedata
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
VALID_DOMAINS = {"process", "variety", "roast_level", "country", "flavor_note"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply safe dictionary alias candidates")
    parser.add_argument("--input", required=True, help="Candidate JSON file")
    parser.add_argument("--dictionary-version", default="v1", help="Dictionary version (default: v1)")
    parser.add_argument("--min-count", type=int, default=3, help="Minimum count to apply (default: 3)")
    parser.add_argument("--min-score", type=float, default=0.9, help="Minimum similarity score (default: 0.9)")
    parser.add_argument(
        "--flavor-min-score",
        type=float,
        default=0.94,
        help="Minimum similarity for flavor_note (default: 0.94)",
    )
    parser.add_argument(
        "--max-additions",
        type=int,
        default=40,
        help="Safety cap for number of aliases added (default: 40)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Show changes without writing files")
    return parser.parse_args()


def normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKC", value).lower().strip()
    text = text.replace("_", " ").replace("-", " ")
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text


def is_single_value(raw: str) -> bool:
    return not any(sep in raw for sep in [",", "\n", ";", "/", "|", "·", "、"])


def load_candidates(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


def load_python_list(path: Path, key: str) -> list[dict[str, Any]]:
    namespace = runpy.run_path(str(path))
    data = namespace.get(key)
    if not isinstance(data, list):
        raise RuntimeError(f"Invalid or missing {key} in {path}")
    return data


def write_python_list(path: Path, key: str, data: list[dict[str, Any]], docstring: str) -> None:
    content = f'"""{docstring}"""\n\n{key} = ' + json.dumps(data, ensure_ascii=False, indent=4) + "\n"
    path.write_text(content, encoding="utf-8")


def main() -> int:
    args = parse_args()
    base = ROOT / "src" / "bean_lens" / "normalization" / "data" / args.dictionary_version
    terms_py = base / "terms.py"
    aliases_py = base / "aliases.py"
    terms_json = base / "terms.json"
    aliases_json = base / "aliases.json"

    terms = load_python_list(terms_py, "TERMS")
    aliases = load_python_list(aliases_py, "ALIASES")
    candidates = load_candidates(Path(args.input))

    valid_keys = {(item["domain"], item["key"]) for item in terms}
    existing_aliases = {(a["domain"], normalize_text(a["alias"])) for a in aliases}

    additions: list[dict[str, Any]] = []
    skipped = 0

    for row in candidates:
        if len(additions) >= args.max_additions:
            break
        if not isinstance(row, dict):
            skipped += 1
            continue

        domain = row.get("domain")
        raw = row.get("raw")
        count = row.get("count", 0)
        best_match = row.get("best_match", {})
        suggested = row.get("suggested_alias")

        if domain not in VALID_DOMAINS or not isinstance(raw, str) or not isinstance(suggested, dict):
            skipped += 1
            continue
        if not isinstance(count, int) or count < args.min_count:
            skipped += 1
            continue

        key = suggested.get("key")
        score = best_match.get("score", 0.0) if isinstance(best_match, dict) else 0.0
        if not isinstance(key, str) or (domain, key) not in valid_keys:
            skipped += 1
            continue
        if not isinstance(score, (int, float)):
            skipped += 1
            continue

        threshold = args.flavor_min_score if domain == "flavor_note" else args.min_score
        if float(score) < threshold:
            skipped += 1
            continue
        if not is_single_value(raw):
            skipped += 1
            continue

        signature = (domain, normalize_text(raw))
        if signature in existing_aliases:
            skipped += 1
            continue

        alias_row: dict[str, Any] = {
            "domain": domain,
            "key": key,
            "alias": raw,
            "match_type": "exact",
            "priority": 40,
        }

        if domain == "flavor_note":
            # flavor_note domain is strict: only typo aliases may be auto-added.
            alias_row["alias_kind"] = "typo"

        additions.append(alias_row)
        existing_aliases.add(signature)

    if additions and not args.dry_run:
        aliases.extend(additions)
        aliases.sort(
            key=lambda item: (
                str(item["domain"]),
                int(item.get("priority", 100)),
                normalize_text(str(item["alias"])),
            )
        )

        write_python_list(terms_py, "TERMS", terms, "Canonical dictionary terms for normalization v1.")
        write_python_list(aliases_py, "ALIASES", aliases, "Alias dictionary for normalization v1.")
        terms_json.write_text(json.dumps(terms, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        aliases_json.write_text(json.dumps(aliases, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    summary = {
        "input_candidates": len(candidates),
        "added_aliases": len(additions),
        "skipped_candidates": skipped,
        "dry_run": args.dry_run,
        "max_additions": args.max_additions,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if additions:
        print(json.dumps({"preview_additions": additions[:20]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
