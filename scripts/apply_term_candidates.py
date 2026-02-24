"""Apply approved new term candidates to dictionary files.

This script applies only explicitly approved items.
It updates both Python dictionary sources and JSON mirrors.

Example:
  python scripts/apply_term_candidates.py \
    --candidates data/review/new_term_candidates.auto.json \
    --approved data/review/approved_term_candidates.json \
    --dictionary-version v2
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
    parser = argparse.ArgumentParser(description="Apply approved term candidates")
    parser.add_argument("--candidates", required=True, help="Path to generated new term candidates JSON")
    parser.add_argument("--approved", required=True, help="Path to approved term list JSON")
    parser.add_argument("--dictionary-version", default="v2", help="Dictionary version (default: v2)")
    parser.add_argument(
        "--allow-flavor-note",
        action="store_true",
        help="Allow flavor_note term additions (default: false)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Show planned changes without writing")
    return parser.parse_args()


def normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKC", value).lower().strip()
    text = text.replace("_", " ").replace("-", " ")
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text


def load_json(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def load_python_list(path: Path, key: str) -> list[dict[str, Any]]:
    namespace = runpy.run_path(str(path))
    value = namespace.get(key)
    if not isinstance(value, list):
        raise RuntimeError(f"Invalid {key} in {path}")
    return value


def write_python_list(path: Path, key: str, data: list[dict[str, Any]], docstring: str) -> None:
    content = f'"""{docstring}"""\n\n{key} = ' + json.dumps(data, ensure_ascii=False, indent=4) + "\n"
    path.write_text(content, encoding="utf-8")


def slug_key(raw: str) -> str:
    normalized = normalize_text(raw).replace(" ", "_")
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized


def main() -> int:
    args = parse_args()
    base = ROOT / "src" / "bean_lens" / "normalization" / "data" / args.dictionary_version
    terms_py = base / "terms.py"
    aliases_py = base / "aliases.py"
    terms_json = base / "terms.json"
    aliases_json = base / "aliases.json"

    terms = load_python_list(terms_py, "TERMS")
    aliases = load_python_list(aliases_py, "ALIASES")
    candidates_data = load_json(Path(args.candidates))
    approved_data = load_json(Path(args.approved))
    if not isinstance(candidates_data, list):
        raise SystemExit("candidates file must be a list")
    if not isinstance(approved_data, list):
        raise SystemExit("approved file must be a list")

    candidate_map: dict[tuple[str, str], dict[str, Any]] = {}
    for row in candidates_data:
        if not isinstance(row, dict):
            continue
        domain = row.get("domain")
        raw = row.get("raw")
        if isinstance(domain, str) and isinstance(raw, str):
            candidate_map[(domain, raw)] = row

    term_keys = {(t["domain"], t["key"]) for t in terms}
    alias_signatures = {(a["domain"], normalize_text(a["alias"])) for a in aliases}

    term_additions: list[dict[str, Any]] = []
    alias_additions: list[dict[str, Any]] = []
    skipped = 0

    for item in approved_data:
        if not isinstance(item, dict):
            skipped += 1
            continue
        domain = item.get("domain")
        raw = item.get("raw")
        if not isinstance(domain, str) or not isinstance(raw, str) or domain not in VALID_DOMAINS:
            skipped += 1
            continue
        if domain == "flavor_note" and not args.allow_flavor_note:
            skipped += 1
            continue

        candidate = candidate_map.get((domain, raw), {})
        suggested = candidate.get("suggested_term_template", {}) if isinstance(candidate, dict) else {}

        key = item.get("key") if isinstance(item.get("key"), str) else None
        label_en = item.get("label_en") if isinstance(item.get("label_en"), str) else None
        label_ko = item.get("label_ko") if isinstance(item.get("label_ko"), str) else None

        if not key and isinstance(suggested, dict):
            key = suggested.get("key") if isinstance(suggested.get("key"), str) else None
        if not key:
            key = slug_key(raw)
        if not label_en:
            label_en = raw
        if not label_ko:
            label_ko = raw

        term_row = {"domain": domain, "key": key, "label_en": label_en, "label_ko": label_ko}
        if (domain, key) not in term_keys:
            term_additions.append(term_row)
            term_keys.add((domain, key))

        sig = (domain, normalize_text(raw))
        if sig not in alias_signatures:
            alias_row = {
                "domain": domain,
                "key": key,
                "alias": raw,
                "match_type": "exact",
                "priority": 20,
            }
            if domain == "flavor_note":
                alias_row["alias_kind"] = "typo"
            alias_additions.append(alias_row)
            alias_signatures.add(sig)

        extra_aliases = item.get("aliases")
        if isinstance(extra_aliases, list):
            for alias_value in extra_aliases:
                if not isinstance(alias_value, str) or not alias_value.strip():
                    continue
                extra_sig = (domain, normalize_text(alias_value))
                if extra_sig in alias_signatures:
                    continue
                alias_row = {
                    "domain": domain,
                    "key": key,
                    "alias": alias_value,
                    "match_type": "exact",
                    "priority": 25,
                }
                if domain == "flavor_note":
                    alias_row["alias_kind"] = "typo"
                alias_additions.append(alias_row)
                alias_signatures.add(extra_sig)

    if not args.dry_run and (term_additions or alias_additions):
        terms.extend(term_additions)
        aliases.extend(alias_additions)

        terms.sort(key=lambda t: (str(t["domain"]), str(t["key"])))
        aliases.sort(key=lambda a: (str(a["domain"]), int(a.get("priority", 100)), normalize_text(str(a["alias"]))))

        write_python_list(
            terms_py,
            "TERMS",
            terms,
            f"Canonical dictionary terms for normalization {args.dictionary_version}.",
        )
        write_python_list(
            aliases_py,
            "ALIASES",
            aliases,
            f"Alias dictionary for normalization {args.dictionary_version}.",
        )
        terms_json.write_text(json.dumps(terms, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        aliases_json.write_text(json.dumps(aliases, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "approved_items": len(approved_data),
                "added_terms": len(term_additions),
                "added_aliases": len(alias_additions),
                "skipped_items": skipped,
                "dry_run": args.dry_run,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
