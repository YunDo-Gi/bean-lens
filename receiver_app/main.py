"""Minimal webhook receiver for unknown-queue events (PostgreSQL).

Run locally:
  uvicorn receiver_app.main:app --reload --port 8100
"""

from __future__ import annotations

import os
from datetime import datetime

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field
import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.getenv("DATABASE_URL")
WEBHOOK_TOKEN = os.getenv("UNKNOWN_QUEUE_RECEIVER_TOKEN")

app = FastAPI(title="Unknown Queue Receiver", version="1.1.0")


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


def _require_database_url() -> str:
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is required for receiver_app")
    return DATABASE_URL


def _conn() -> psycopg.Connection:
    return psycopg.connect(_require_database_url(), row_factory=dict_row)


def _init_db() -> None:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                create table if not exists unknown_queue_events (
                  id bigserial primary key,
                  ts timestamptz not null,
                  domain text not null,
                  raw text not null,
                  confidence double precision not null,
                  reason text not null,
                  method text not null,
                  normalized_key text null,
                  dictionary_version text not null,
                  received_at timestamptz not null default now()
                )
                """
            )
            cur.execute(
                "create index if not exists idx_unknown_queue_events_domain on unknown_queue_events(domain)"
            )
            cur.execute(
                "create index if not exists idx_unknown_queue_events_reason on unknown_queue_events(reason)"
            )
            cur.execute(
                "create index if not exists idx_unknown_queue_events_received_at on unknown_queue_events(received_at)"
            )
        conn.commit()


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
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into unknown_queue_events (
                  ts, domain, raw, confidence, reason, method, normalized_key, dictionary_version
                ) values (%s, %s, %s, %s, %s, %s, %s, %s)
                returning id
                """,
                (
                    event.ts,
                    event.domain,
                    event.raw,
                    event.confidence,
                    event.reason,
                    event.method,
                    event.normalized_key,
                    event.dictionary_version,
                ),
            )
            row = cur.fetchone()
        conn.commit()

    event_id = int(row["id"]) if row and row.get("id") is not None else 0
    return {"id": event_id}


@app.get("/unknown-queue/recent", response_model=list[UnknownQueueEventOut])
def recent_events(
    limit: int = Query(default=50, ge=1, le=500),
    _: None = Depends(_verify_token),
) -> list[UnknownQueueEventOut]:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select id, ts, domain, raw, confidence, reason, method, normalized_key, dictionary_version, received_at
                from unknown_queue_events
                order by id desc
                limit %s
                """,
                (limit,),
            )
            rows = cur.fetchall()

    return [
        UnknownQueueEventOut(
            id=int(row["id"]),
            ts=_as_datetime(row["ts"]),
            domain=row["domain"],
            raw=row["raw"],
            confidence=float(row["confidence"]),
            reason=row["reason"],
            method=row["method"],
            normalized_key=row["normalized_key"],
            dictionary_version=row["dictionary_version"],
            received_at=_as_datetime(row["received_at"]),
        )
        for row in rows
    ]


def _as_datetime(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    raise ValueError("Invalid datetime value")
