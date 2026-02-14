"""Command-line interface for bean-lens."""

import argparse
import json
import sys

from bean_lens import __version__, extract
from bean_lens.exceptions import AuthenticationError, BeanLensError


def main() -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="bean-lens",
        description="Extract coffee bean info from package images",
    )
    parser.add_argument("image", help="Path to coffee package image")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )
    parser.add_argument(
        "--api-key",
        help="Gemini API key (default: GEMINI_API_KEY env var)",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"bean-lens {__version__}",
    )

    args = parser.parse_args()

    try:
        result = extract(args.image, api_key=args.api_key)
    except AuthenticationError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except BeanLensError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if args.json:
        print(result.model_dump_json(indent=2, exclude_none=True))
    else:
        _print_formatted(result)

    return 0


def _print_formatted(result) -> None:
    """Print result in human-readable format."""
    print()
    print("  bean-lens")
    print()

    fields = [
        ("Roastery", result.roastery),
        ("Name", result.name),
        ("Origin", _format_origin(result.origin)),
        ("Variety", _format_list(result.variety)),
        ("Process", result.process),
        ("Roast Level", result.roast_level),
        ("Flavor Notes", _format_list(result.flavor_notes)),
        ("Roast Date", result.roast_date),
        ("Altitude", result.altitude),
    ]

    for label, value in fields:
        display = value if value else "-"
        print(f"  {label + ':':<14} {display}")

    print()


def _format_origin(origin) -> str | None:
    """Format origin as a single string."""
    if not origin:
        return None
    parts = [p for p in [origin.country, origin.region, origin.farm] if p]
    return " / ".join(parts) if parts else None


def _format_list(items: list[str] | None) -> str | None:
    """Format list as comma-separated string."""
    if not items:
        return None
    return ", ".join(items)


if __name__ == "__main__":
    sys.exit(main())
