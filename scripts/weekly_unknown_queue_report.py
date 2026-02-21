"""Generate weekly unknown-queue report (Markdown/JSON).

Supports:
1) JSONL input from UNKNOWN_QUEUE_PATH
2) PostgreSQL input from receiver_app table unknown_queue_events

Examples:
  python scripts/weekly_unknown_queue_report.py \
    --input /tmp/bean-lens-unknown.jsonl \
    --days 7 \
    --output data/review/unknown_queue_weekly.md

  python scripts/weekly_unknown_queue_report.py \
    --database-url "$DATABASE_URL" \
    --days 7 \
    --output data/review/unknown_queue_weekly.md
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
VALID_DOMAINS = ("process", "roast_level", "country", "variety", "flavor_note")


@dataclass(frozen=True)
class Event:
    ts: datetime
    domain: str
    raw: str
    reason: str
    method: str
    confidence: float
    normalized_key: str | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate weekly unknown queue report")
    parser.add_argument("--input", help="Path to unknown queue JSONL")
    parser.add_argument("--database-url", help="PostgreSQL DATABASE_URL for receiver DB")
    parser.add_argument("--days", type=int, default=7, help="Lookback window in days (default: 7)")
    parser.add_argument("--top", type=int, default=20, help="Top raw values per domain (default: 20)")
    parser.add_argument("--dictionary-version", default="v1", help="Dictionary version (default: v1)")
    parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Report format (default: markdown)",
    )
    parser.add_argument("--output", help="Optional output file path")
    return parser.parse_args()


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str) and value:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKC", value).lower().strip()
    text = text.replace("_", " ").replace("-", " ")
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
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


def _load_postgres(database_url: str) -> list[dict[str, Any]]:
    try:
        import psycopg
        from psycopg.rows import dict_row
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("psycopg is required for --database-url mode") from exc

    query = """
        select ts, domain, raw, confidence, reason, method, normalized_key
        from unknown_queue_events
    """
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
    return [dict(row) for row in rows]


def _rows_to_events(rows: list[dict[str, Any]], since_utc: datetime) -> list[Event]:
    events: list[Event] = []
    for row in rows:
        ts = _parse_datetime(row.get("ts"))
        domain = str(row.get("domain", "")).strip()
        raw = str(row.get("raw", "")).strip()
        reason = str(row.get("reason", "")).strip() or "unknown"
        method = str(row.get("method", "")).strip() or "unknown"
        conf = row.get("confidence")
        confidence = float(conf) if isinstance(conf, (int, float)) else 0.0
        normalized_key = row.get("normalized_key")
        normalized_key = normalized_key if isinstance(normalized_key, str) else None

        if ts is None or ts < since_utc:
            continue
        if domain not in VALID_DOMAINS or not raw:
            continue

        events.append(
            Event(
                ts=ts,
                domain=domain,
                raw=raw,
                reason=reason,
                method=method,
                confidence=confidence,
                normalized_key=normalized_key,
            )
        )
    return events


def _load_term_candidates(version: str) -> dict[str, list[str]]:
    path = ROOT / "src" / "bean_lens" / "normalization" / "data" / version / "terms.json"
    if not path.exists():
        return {}
    terms = json.loads(path.read_text(encoding="utf-8"))
    by_domain: dict[str, list[str]] = defaultdict(list)
    for term in terms:
        domain = term.get("domain")
        if domain not in VALID_DOMAINS:
            continue
        for value in (term.get("key"), term.get("label_en"), term.get("label_ko")):
            if isinstance(value, str):
                by_domain[str(domain)].append(value)
    return by_domain


def _find_typo_hint(raw: str, candidates: list[str]) -> tuple[str | None, float]:
    normalized_raw = _normalize_text(raw)
    best_match: str | None = None
    best_score = 0.0
    for candidate in candidates:
        score = SequenceMatcher(None, normalized_raw, _normalize_text(candidate)).ratio()
        if score > best_score:
            best_score = score
            best_match = candidate
    return best_match, round(best_score, 4)


def summarize(events: list[Event], *, top: int, dictionary_version: str) -> dict[str, Any]:
    domain_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    method_counts: Counter[str] = Counter()
    grouped_raw: dict[str, Counter[str]] = defaultdict(Counter)
    grouped_reason: dict[str, Counter[str]] = defaultdict(Counter)
    compound_counts: Counter[str] = Counter()

    for ev in events:
        domain_counts[ev.domain] += 1
        reason_counts[ev.reason] += 1
        method_counts[ev.method] += 1
        grouped_raw[ev.domain][ev.raw] += 1
        grouped_reason[ev.domain][ev.reason] += 1
        if any(sep in ev.raw for sep in [",", "\n", ";", "/", "|", "·", "、"]):
            compound_counts[ev.domain] += 1

    terms_by_domain = _load_term_candidates(dictionary_version)
    typo_hints: list[dict[str, Any]] = []
    for domain, counter in grouped_raw.items():
        for raw, count in counter.most_common(top * 3):
            best, score = _find_typo_hint(raw, terms_by_domain.get(domain, []))
            if best is None:
                continue
            if score < 0.88 or score >= 1.0:
                continue
            typo_hints.append(
                {
                    "domain": domain,
                    "raw": raw,
                    "count": count,
                    "suggested_term": best,
                    "score": score,
                }
            )
    typo_hints.sort(key=lambda x: (-x["count"], -x["score"], x["domain"], x["raw"]))

    top_by_domain: dict[str, list[dict[str, Any]]] = {}
    for domain in VALID_DOMAINS:
        rows: list[dict[str, Any]] = []
        for raw, count in grouped_raw.get(domain, Counter()).most_common(top):
            rows.append(
                {
                    "raw": raw,
                    "count": count,
                    "top_reason": grouped_reason[domain].most_common(1)[0][0] if grouped_reason[domain] else None,
                }
            )
        top_by_domain[domain] = rows

    return {
        "events": len(events),
        "unique_raw": sum(len(counter) for counter in grouped_raw.values()),
        "domain_counts": dict(domain_counts),
        "reason_counts": dict(reason_counts),
        "method_counts": dict(method_counts),
        "compound_counts": dict(compound_counts),
        "top_by_domain": top_by_domain,
        "typo_hints": typo_hints[:top],
    }


def render_markdown(summary: dict[str, Any], *, days: int, source: str) -> str:
    lines: list[str] = []
    lines.append("# Unknown Queue Weekly Report")
    lines.append("")
    lines.append(f"- Window: last {days} days")
    lines.append(f"- Source: `{source}`")
    lines.append(f"- Total events: {summary['events']}")
    lines.append(f"- Unique raw values: {summary['unique_raw']}")
    lines.append("")

    lines.append("## Domain Breakdown")
    lines.append("")
    lines.append("domain | events | compound_raw_events")
    lines.append("--- | --- | ---")
    for domain in VALID_DOMAINS:
        lines.append(
            f"{domain} | {summary['domain_counts'].get(domain, 0)} | {summary['compound_counts'].get(domain, 0)}"
        )
    lines.append("")

    lines.append("## Reasons")
    lines.append("")
    lines.append("reason | count")
    lines.append("--- | ---")
    for reason, count in sorted(summary["reason_counts"].items(), key=lambda x: (-x[1], x[0])):
        lines.append(f"{reason} | {count}")
    lines.append("")

    lines.append("## Top Unknown Values")
    lines.append("")
    for domain in VALID_DOMAINS:
        rows = summary["top_by_domain"].get(domain, [])
        if not rows:
            continue
        lines.append(f"### {domain}")
        lines.append("")
        lines.append("count | raw")
        lines.append("--- | ---")
        for row in rows:
            lines.append(f"{row['count']} | {row['raw']}")
        lines.append("")

    lines.append("## Typo Hints (Review Required)")
    lines.append("")
    lines.append("domain | raw | count | suggested_term | score")
    lines.append("--- | --- | --- | --- | ---")
    for row in summary["typo_hints"]:
        lines.append(
            f"{row['domain']} | {row['raw']} | {row['count']} | {row['suggested_term']} | {row['score']}"
        )
    if not summary["typo_hints"]:
        lines.append("(none)")
    lines.append("")

    lines.append("## Recommended Actions")
    lines.append("")
    lines.append("- Split compound values at extraction/parsing stage when `compound_raw_events` grows.")
    lines.append("- For `flavor_note`, keep strict mode and only add typo aliases after manual review.")
    lines.append("- Promote high-frequency unknown terms to `terms.py` when they represent new canonical concepts.")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    args = parse_args()

    if bool(args.input) == bool(args.database_url):
        raise SystemExit("Provide exactly one source: --input or --database-url")

    since_utc = datetime.now(timezone.utc) - timedelta(days=args.days)
    if args.input:
        source = args.input
        rows = _load_jsonl(Path(args.input))
    else:
        source = "postgres"
        rows = _load_postgres(args.database_url)

    events = _rows_to_events(rows, since_utc)
    summary = summarize(events, top=args.top, dictionary_version=args.dictionary_version)

    if args.format == "json":
        output = json.dumps(
            {
                "window_days": args.days,
                "source": source,
                "summary": summary,
            },
            ensure_ascii=False,
            indent=2,
        )
    else:
        output = render_markdown(summary, days=args.days, source=source)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output + "\n", encoding="utf-8")
        print(f"written: {out_path}")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
