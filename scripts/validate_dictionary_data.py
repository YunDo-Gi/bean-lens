"""Validate normalization dictionary consistency.

Checks:
1. Python sources and JSON mirrors are identical for terms/aliases.
2. Alias keys reference existing term keys in the same domain.
3. Duplicate alias entries (domain + normalized alias) are not present.
"""

from __future__ import annotations

import json
import re
import runpy
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
V1_DIR = ROOT / "src" / "bean_lens" / "normalization" / "data" / "v1"


def normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKC", value).lower().strip()
    text = text.replace("_", " ").replace("-", " ")
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text


def fail(message: str) -> None:
    print(f"[dictionary-check] ERROR: {message}")
    raise SystemExit(1)


def load_python_constant(path: Path, key: str) -> list[dict]:
    namespace = runpy.run_path(str(path))
    if key not in namespace or not isinstance(namespace[key], list):
        fail(f"Missing or invalid constant '{key}' in {path}")
    return namespace[key]


def load_json(path: Path) -> list[dict]:
    if not path.exists():
        fail(f"Missing JSON file: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        fail(f"JSON file must contain a list: {path}")
    return data


def assert_py_json_mirror(py_data: list[dict], json_data: list[dict], label: str) -> None:
    if py_data != json_data:
        fail(
            f"{label}.py and {label}.json are out of sync. "
            f"Run mirror update before commit."
        )


def validate_alias_references(terms: list[dict], aliases: list[dict]) -> None:
    valid_keys = {(item["domain"], item["key"]) for item in terms}
    for alias in aliases:
        ref = (alias.get("domain"), alias.get("key"))
        if ref not in valid_keys:
            fail(f"Alias references unknown term key: {ref}")


def validate_duplicate_aliases(aliases: list[dict]) -> None:
    seen: dict[tuple[str, str], str] = {}
    for alias in aliases:
        domain = alias.get("domain")
        raw = alias.get("alias")
        key = alias.get("key")
        if not isinstance(domain, str) or not isinstance(raw, str):
            fail(f"Invalid alias entry: {alias}")
        if not isinstance(key, str):
            fail(f"Invalid alias key: {alias}")

        signature = (domain, normalize_text(raw))
        if signature in seen and seen[signature] != key:
            fail(
                f"Conflicting alias detected for domain/text {signature}: "
                f"{seen[signature]} vs {key}"
            )
        seen[signature] = key


def main() -> int:
    terms_py = load_python_constant(V1_DIR / "terms.py", "TERMS")
    terms_json = load_json(V1_DIR / "terms.json")
    aliases_py = load_python_constant(V1_DIR / "aliases.py", "ALIASES")
    aliases_json = load_json(V1_DIR / "aliases.json")

    assert_py_json_mirror(terms_py, terms_json, "terms")
    assert_py_json_mirror(aliases_py, aliases_json, "aliases")
    validate_alias_references(terms_py, aliases_py)
    validate_duplicate_aliases(aliases_py)

    print("[dictionary-check] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
