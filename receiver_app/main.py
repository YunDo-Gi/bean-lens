"""Minimal webhook receiver for unknown-queue events.

Run locally:
  uvicorn receiver_app.main:app --reload --port 8100
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field

DB_PATH = os.getenv("UNKNOWN_QUEUE_RECEIVER_DB_PATH", "/tmp/unknown_queue_events.db")
WEBHOOK_TOKEN = os.getenv("UNKNOWN_QUEUE_RECEIVER_TOKEN")

app = FastAPI(title="Unknown Queue Receiver", version="1.0.0")


class UnknownQueueEvent(BaseModel):
    ts: datetime
    domain: str = Field(min_length=1)
    raw: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1)
    method: str = Field(min_length=1)
    normalized_key: str | None = None
    dictionary_version: str = Field(min_length=1)


class UnknownQueueEventOut(UnknownQueueEvent):
    id: int
    received_at: datetime


def _conn() -> sqlite3.Connection:
    db_path = Path(DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    with _conn() as conn:
        conn.execute(
            """
            create table if not exists unknown_queue_events (
              id integer primary key autoincrement,
              ts text not null,
              domain text not null,
              raw text not null,
              confidence real not null,
              reason text not null,
              method text not null,
              normalized_key text null,
              dictionary_version text not null,
              received_at text not null default (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            )
            """
        )
        conn.execute(
            "create index if not exists idx_unknown_queue_events_domain on unknown_queue_events(domain)"
        )
        conn.execute(
            "create index if not exists idx_unknown_queue_events_reason on unknown_queue_events(reason)"
        )
        conn.execute(
            "create index if not exists idx_unknown_queue_events_received_at on unknown_queue_events(received_at)"
        )


@app.on_event("startup")
def startup() -> None:
    _init_db()


def _verify_token(x_webhook_token: str | None = Header(default=None)) -> None:
    if WEBHOOK_TOKEN and x_webhook_token != WEBHOOK_TOKEN:
        raise HTTPException(status_code=401, detail="invalid webhook token")


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.post("/unknown-queue")
def ingest_event(
    event: UnknownQueueEvent,
    _: None = Depends(_verify_token),
) -> dict[str, int]:
    with _conn() as conn:
        cur = conn.execute(
            """
            insert into unknown_queue_events (
              ts, domain, raw, confidence, reason, method, normalized_key, dictionary_version
            ) values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.ts.isoformat(),
                event.domain,
                event.raw,
                event.confidence,
                event.reason,
                event.method,
                event.normalized_key,
                event.dictionary_version,
            ),
        )
        event_id = int(cur.lastrowid)
    return {"id": event_id}


@app.get("/unknown-queue/recent", response_model=list[UnknownQueueEventOut])
def recent_events(
    limit: int = Query(default=50, ge=1, le=500),
    _: None = Depends(_verify_token),
) -> list[UnknownQueueEventOut]:
    with _conn() as conn:
        rows = conn.execute(
            """
            select id, ts, domain, raw, confidence, reason, method, normalized_key, dictionary_version, received_at
            from unknown_queue_events
            order by id desc
            limit ?
            """,
            (limit,),
        ).fetchall()

    return [
        UnknownQueueEventOut(
            id=row["id"],
            ts=datetime.fromisoformat(row["ts"]),
            domain=row["domain"],
            raw=row["raw"],
            confidence=row["confidence"],
            reason=row["reason"],
            method=row["method"],
            normalized_key=row["normalized_key"],
            dictionary_version=row["dictionary_version"],
            received_at=datetime.fromisoformat(row["received_at"].replace("Z", "+00:00")),
        )
        for row in rows
    ]
