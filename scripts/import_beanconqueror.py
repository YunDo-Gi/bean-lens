"""Build import candidates from Beanconqueror source data.

Usage:
  python scripts/import_beanconqueror.py --source /path/to/Beanconqueror

This script reads Beanconqueror's roast enum and cupping flavor tree,
and emits candidate term/alias JSON files for manual review.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def slugify(value: str) -> str:
    text = value.strip().lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text


def parse_roast_aliases(roasts_ts_path: Path) -> list[dict[str, str | int]]:
    section = None
    aliases: list[dict[str, str | int]] = []

    section_to_key = {
        "LIGHT": "light",
        "MEDIUM": "medium",
        "DARK": "dark",
    }

    for line in roasts_ts_path.read_text(encoding="utf-8").splitlines():
        section_match = re.search(r"//\s*(LIGHT|MEDIUM|DARK)\s*$", line)
        if section_match:
            section = section_match.group(1)
            continue

        value_match = re.search(r"=\s*'([^']+)'", line)
        if not value_match:
            continue

        value = value_match.group(1).strip()
        if value in {"Unknown", "Custom"}:
            continue
        if section not in section_to_key:
            continue

        aliases.append(
            {
                "domain": "roast_level",
                "key": section_to_key[section],
                "alias": value,
                "match_type": "exact",
                "priority": 25,
            }
        )

    return aliases


def _collect_leaf_nodes(node: dict, leaves: list[str]) -> None:
    children = node.get("children") or []
    if not children:
        name = node.get("name")
        if isinstance(name, str) and name.strip():
            leaves.append(name.strip())
        return

    for child in children:
        if isinstance(child, dict):
            _collect_leaf_nodes(child, leaves)


def parse_flavor_terms(cupping_flavors_path: Path) -> tuple[list[dict[str, str]], list[dict[str, str | int]]]:
    payload = json.loads(cupping_flavors_path.read_text(encoding="utf-8"))
    leaves: list[str] = []

    for item in payload:
        if isinstance(item, dict):
            _collect_leaf_nodes(item, leaves)

    # Deduplicate preserving order.
    seen: set[str] = set()
    deduped: list[str] = []
    for leaf in leaves:
        normalized = leaf.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(leaf)

    terms: list[dict[str, str]] = []
    aliases: list[dict[str, str | int]] = []
    for leaf in deduped:
        key = slugify(leaf)
        terms.append(
            {
                "domain": "flavor_note",
                "key": key,
                "label_en": leaf,
                "label_ko": leaf,
            }
        )
        aliases.append(
            {
                "domain": "flavor_note",
                "key": key,
                "alias": leaf,
                "match_type": "exact",
                "priority": 30,
            }
        )

    return terms, aliases


def main() -> int:
    parser = argparse.ArgumentParser(description="Import Beanconqueror dictionary candidates")
    parser.add_argument("--source", required=True, help="Path to Beanconqueror repository root")
    parser.add_argument(
        "--output-dir",
        default="data/imports/beanconqueror",
        help="Directory to write generated candidate JSON files",
    )

    args = parser.parse_args()
    source_root = Path(args.source).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    roasts_ts = source_root / "src/enums/beans/roasts.ts"
    cupping_flavors_json = source_root / "src/data/cupping-flavors/cupping-flavors.json"

    if not roasts_ts.exists():
        raise FileNotFoundError(f"Missing file: {roasts_ts}")
    if not cupping_flavors_json.exists():
        raise FileNotFoundError(f"Missing file: {cupping_flavors_json}")

    roast_aliases = parse_roast_aliases(roasts_ts)
    flavor_terms, flavor_aliases = parse_flavor_terms(cupping_flavors_json)

    (output_dir / "roast_aliases.json").write_text(
        json.dumps(roast_aliases, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "flavor_terms.json").write_text(
        json.dumps(flavor_terms, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "flavor_aliases.json").write_text(
        json.dumps(flavor_aliases, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    summary = {
        "roast_aliases": len(roast_aliases),
        "flavor_terms": len(flavor_terms),
        "flavor_aliases": len(flavor_aliases),
        "output_dir": str(output_dir),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
