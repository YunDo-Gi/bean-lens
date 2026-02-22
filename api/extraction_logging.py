"""Best-effort extraction logging and optional image storage."""

from __future__ import annotations

import hashlib
import json
import os
import random
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib import error, request


def _parse_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _safe_float(value: str | None, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ExtractionLoggingConfig:
    enabled: bool = False
    database_url: str | None = None
    table: str = "extract_logs"
    save_image_on_warning: bool = False
    save_image_sample_rate: float = 0.0
    save_image_on_error: bool = False
    storage_backend: str = "none"  # none|supabase
    supabase_url: str | None = None
    supabase_service_role_key: str | None = None
    supabase_bucket: str | None = None

    @classmethod
    def from_env(cls) -> "ExtractionLoggingConfig":
        return cls(
            enabled=_parse_bool(os.getenv("SAVE_REQUEST_LOG"), False),
            database_url=os.getenv("EXTRACTION_LOG_DATABASE_URL") or os.getenv("DATABASE_URL"),
            table=os.getenv("EXTRACTION_LOG_TABLE", "extract_logs"),
            save_image_on_warning=_parse_bool(os.getenv("SAVE_IMAGE_ON_WARNING"), True),
            save_image_sample_rate=max(0.0, min(1.0, _safe_float(os.getenv("SAVE_IMAGE_SAMPLE_RATE"), 0.0))),
            save_image_on_error=_parse_bool(os.getenv("SAVE_IMAGE_ON_ERROR"), False),
            storage_backend=(os.getenv("STORAGE_BACKEND", "none").strip().lower() or "none"),
            supabase_url=os.getenv("SUPABASE_URL"),
            supabase_service_role_key=os.getenv("SUPABASE_SERVICE_ROLE_KEY"),
            supabase_bucket=os.getenv("SUPABASE_BUCKET"),
        )


class ExtractionLogger:
    def __init__(self, config: ExtractionLoggingConfig):
        self.config = config
        self._db_ready = False

    def should_log(self) -> bool:
        return self.config.enabled and bool(self.config.database_url)

    def new_request_id(self) -> str:
        return str(uuid.uuid4())

    def image_sha256(self, payload: bytes) -> str:
        return hashlib.sha256(payload).hexdigest()

    def should_save_image(self, *, warnings: list[str], has_error: bool) -> bool:
        if has_error and self.config.save_image_on_error:
            return True
        if warnings and self.config.save_image_on_warning:
            return True
        if self.config.save_image_sample_rate > 0 and random.random() < self.config.save_image_sample_rate:
            return True
        return False

    def log_success(
        self,
        *,
        request_id: str,
        payload: bytes,
        content_type: str,
        extracted: dict,
        normalized: dict,
        extraction_metadata: dict,
        warnings: list[str],
    ) -> None:
        if not self.should_log():
            return

        image_sha = self.image_sha256(payload)
        save_image = self.should_save_image(warnings=warnings, has_error=False)
        image_url = self._maybe_store_image(
            request_id=request_id,
            payload=payload,
            content_type=content_type,
            image_sha=image_sha,
            enabled=save_image,
        )
        payload_row = {
            "request_id": request_id,
            "created_at": _utc_now_iso(),
            "provider": extraction_metadata.get("provider"),
            "parser": extraction_metadata.get("parser"),
            "image_sha256": image_sha,
            "mime_type": content_type,
            "image_size_bytes": len(payload),
            "save_image": bool(image_url),
            "image_url": image_url,
            "warnings_json": warnings,
            "extracted_json": extracted,
            "normalized_json": normalized,
            "metadata_json": extraction_metadata,
            "ocr_text": extraction_metadata.get("ocr_text"),
            "error_detail": None,
        }
        self._insert_row(payload_row)

    def log_error(
        self,
        *,
        request_id: str,
        payload: bytes | None,
        content_type: str | None,
        extraction_metadata: dict | None,
        error_detail: str,
    ) -> None:
        if not self.should_log():
            return

        image_sha = self.image_sha256(payload) if payload else None
        save_image = self.should_save_image(warnings=[], has_error=True)
        image_url = None
        if payload and content_type:
            image_url = self._maybe_store_image(
                request_id=request_id,
                payload=payload,
                content_type=content_type,
                image_sha=image_sha or "",
                enabled=save_image,
            )
        payload_row = {
            "request_id": request_id,
            "created_at": _utc_now_iso(),
            "provider": (extraction_metadata or {}).get("provider"),
            "parser": (extraction_metadata or {}).get("parser"),
            "image_sha256": image_sha,
            "mime_type": content_type,
            "image_size_bytes": len(payload) if payload else None,
            "save_image": bool(image_url),
            "image_url": image_url,
            "warnings_json": [],
            "extracted_json": None,
            "normalized_json": None,
            "metadata_json": extraction_metadata or {},
            "ocr_text": (extraction_metadata or {}).get("ocr_text"),
            "error_detail": error_detail[:2000],
        }
        self._insert_row(payload_row)

    def _maybe_store_image(
        self,
        *,
        request_id: str,
        payload: bytes,
        content_type: str,
        image_sha: str,
        enabled: bool,
    ) -> str | None:
        if not enabled:
            return None
        if self.config.storage_backend != "supabase":
            return None
        if not (self.config.supabase_url and self.config.supabase_service_role_key and self.config.supabase_bucket):
            return None

        ext = _extension_from_content_type(content_type)
        object_path = f"extract/{datetime.now(timezone.utc).strftime('%Y/%m/%d')}/{request_id}_{image_sha[:12]}.{ext}"
        base = self.config.supabase_url.rstrip("/")
        url = f"{base}/storage/v1/object/{self.config.supabase_bucket}/{object_path}"

        headers = {
            "Authorization": f"Bearer {self.config.supabase_service_role_key}",
            "apikey": self.config.supabase_service_role_key,
            "Content-Type": content_type,
            "x-upsert": "true",
        }
        req = request.Request(url, data=payload, headers=headers, method="POST")
        try:
            with request.urlopen(req, timeout=5):
                pass
        except (error.URLError, TimeoutError, ValueError):
            return None
        return f"supabase://{self.config.supabase_bucket}/{object_path}"

    def _insert_row(self, row: dict) -> None:
        try:
            import psycopg
        except Exception:
            return

        if not self.config.database_url:
            return

        table = self.config.table
        create_sql = f"""
            create table if not exists {table} (
              id bigserial primary key,
              request_id text not null unique,
              created_at timestamptz not null default now(),
              provider text null,
              parser text null,
              image_sha256 text null,
              mime_type text null,
              image_size_bytes integer null,
              save_image boolean not null default false,
              image_url text null,
              warnings_json jsonb not null default '[]'::jsonb,
              extracted_json jsonb null,
              normalized_json jsonb null,
              metadata_json jsonb not null default '{{}}'::jsonb,
              ocr_text text null,
              error_detail text null
            )
        """
        insert_sql = f"""
            insert into {table} (
              request_id, created_at, provider, parser, image_sha256, mime_type, image_size_bytes,
              save_image, image_url, warnings_json, extracted_json, normalized_json, metadata_json,
              ocr_text, error_detail
            ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            on conflict (request_id) do nothing
        """
        try:
            with psycopg.connect(self.config.database_url) as conn:
                with conn.cursor() as cur:
                    if not self._db_ready:
                        cur.execute(create_sql)
                        self._db_ready = True
                    cur.execute(
                        insert_sql,
                        (
                            row.get("request_id"),
                            row.get("created_at"),
                            row.get("provider"),
                            row.get("parser"),
                            row.get("image_sha256"),
                            row.get("mime_type"),
                            row.get("image_size_bytes"),
                            row.get("save_image"),
                            row.get("image_url"),
                            json.dumps(row.get("warnings_json") or [], ensure_ascii=False),
                            json.dumps(row.get("extracted_json"), ensure_ascii=False)
                            if row.get("extracted_json") is not None
                            else None,
                            json.dumps(row.get("normalized_json"), ensure_ascii=False)
                            if row.get("normalized_json") is not None
                            else None,
                            json.dumps(row.get("metadata_json") or {}, ensure_ascii=False),
                            row.get("ocr_text"),
                            row.get("error_detail"),
                        ),
                    )
                conn.commit()
        except Exception:
            # Logging should never break extraction API.
            return


def _extension_from_content_type(content_type: str) -> str:
    normalized = content_type.split(";")[0].strip().lower()
    mapping = {
        "image/jpeg": "jpg",
        "image/jpg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
    }
    return mapping.get(normalized, "bin")
