"""Export FastAPI OpenAPI schema to YAML without external dependencies.

Usage:
  PYTHONPATH=src .venv/bin/python scripts/export_openapi_yaml.py \
    --output openapi/bean-lens-api.yaml
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
from pathlib import Path
from typing import Any

SAFE_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export OpenAPI YAML")
    parser.add_argument(
        "--output",
        default="openapi/bean-lens-api.yaml",
        help="Output YAML path (default: openapi/bean-lens-api.yaml)",
    )
    return parser.parse_args()


def yaml_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    return json.dumps(value, ensure_ascii=False)


def yaml_key(key: str) -> str:
    return key if SAFE_KEY.match(key) else json.dumps(key, ensure_ascii=False)


def dump_yaml(value: Any, indent: int = 0) -> list[str]:
    prefix = "  " * indent

    if isinstance(value, dict):
        lines: list[str] = []
        if not value:
            return [f"{prefix}{{}}"]
        for k, v in value.items():
            key = yaml_key(str(k))
            if isinstance(v, (dict, list)):
                lines.append(f"{prefix}{key}:")
                lines.extend(dump_yaml(v, indent + 1))
            else:
                lines.append(f"{prefix}{key}: {yaml_scalar(v)}")
        return lines

    if isinstance(value, list):
        if not value:
            return [f"{prefix}[]"]
        lines = []
        for item in value:
            if isinstance(item, (dict, list)):
                lines.append(f"{prefix}-")
                lines.extend(dump_yaml(item, indent + 1))
            else:
                lines.append(f"{prefix}- {yaml_scalar(item)}")
        return lines

    return [f"{prefix}{yaml_scalar(value)}"]


def main() -> int:
    args = parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    repo_root = Path(__file__).resolve().parent.parent
    api_index = repo_root / "api" / "index.py"
    spec = importlib.util.spec_from_file_location("bean_lens_api_index", api_index)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load API module from {api_index}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    app = module.app

    schema = app.openapi()
    lines = dump_yaml(schema)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"written: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
