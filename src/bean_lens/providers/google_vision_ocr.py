"""Google Vision OCR provider implementation."""

from __future__ import annotations

import json
import os
import re
from io import BytesIO
from pathlib import Path

from PIL import Image

from bean_lens.exceptions import AuthenticationError, BeanLensError, ImageError, RateLimitError
from bean_lens.providers.base import BaseProvider, ImageInput
from bean_lens.schema import BeanInfo, Origin

_COUNTRY_ALIASES = {
    "ethiopia": "Ethiopia",
    "에티오피아": "Ethiopia",
    "colombia": "Colombia",
    "콜롬비아": "Colombia",
    "brazil": "Brazil",
    "브라질": "Brazil",
    "costa rica": "Costa Rica",
    "코스타리카": "Costa Rica",
    "guatemala": "Guatemala",
    "과테말라": "Guatemala",
    "kenya": "Kenya",
    "케냐": "Kenya",
    "honduras": "Honduras",
    "온두라스": "Honduras",
    "indonesia": "Indonesia",
    "인도네시아": "Indonesia",
    "rwanda": "Rwanda",
    "르완다": "Rwanda",
    "panama": "Panama",
    "파나마": "Panama",
}


class GoogleVisionOCRProvider(BaseProvider):
    """Google Vision OCR provider."""

    def __init__(self, client=None):
        if client is not None:
            self.client = client
            self._vision = None
            return

        try:
            from google.cloud import vision  # type: ignore
        except Exception as exc:
            raise BeanLensError(
                "google-cloud-vision is required for OCR mode. "
                "Install dependencies and set GOOGLE_APPLICATION_CREDENTIALS."
            ) from exc

        self._vision = vision
        try:
            credentials_json = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")
            if credentials_json:
                from google.oauth2 import service_account  # type: ignore

                info = json.loads(credentials_json)
                credentials = service_account.Credentials.from_service_account_info(info)
                self.client = vision.ImageAnnotatorClient(credentials=credentials)
            else:
                self.client = vision.ImageAnnotatorClient()
        except Exception as exc:
            raise AuthenticationError(
                "Failed to initialize Google Vision client. "
                "Check GOOGLE_APPLICATION_CREDENTIALS(_JSON) and GCP IAM permissions."
            ) from exc

    def _load_image(self, image: ImageInput) -> Image.Image:
        if isinstance(image, Image.Image):
            return image

        path = Path(image) if isinstance(image, str) else image
        if not path.exists():
            raise ImageError(f"Image file not found: {path}")

        try:
            return Image.open(path)
        except Exception as e:
            raise ImageError(f"Failed to open image: {e}") from e

    def _extract_text(self, content: bytes) -> str:
        try:
            if self._vision is not None:
                image = self._vision.Image(content=content)
            else:
                image = {"content": content}
            response = self.client.text_detection(image=image)
        except Exception as exc:
            message = str(exc).lower()
            if "quota" in message or "rate" in message:
                raise RateLimitError(f"OCR quota exceeded: {exc}") from exc
            if "credential" in message or "permission" in message or "auth" in message:
                raise AuthenticationError(f"OCR authentication failed: {exc}") from exc
            raise BeanLensError(f"OCR request failed: {exc}") from exc

        error_obj = getattr(response, "error", None)
        error_message = getattr(error_obj, "message", "") if error_obj else ""
        if error_message:
            lowered = error_message.lower()
            if "quota" in lowered or "rate" in lowered:
                raise RateLimitError(f"OCR quota exceeded: {error_message}")
            if "permission" in lowered or "auth" in lowered:
                raise AuthenticationError(f"OCR authentication failed: {error_message}")
            raise BeanLensError(f"OCR request failed: {error_message}")

        annotations = getattr(response, "text_annotations", None) or []
        if not annotations:
            return ""
        return (getattr(annotations[0], "description", "") or "").strip()

    def extract(self, image: ImageInput) -> BeanInfo:
        pil_image = self._load_image(image)

        try:
            with BytesIO() as buffer:
                fmt = (pil_image.format or "PNG").upper()
                if fmt not in {"JPEG", "PNG", "WEBP"}:
                    fmt = "PNG"
                pil_image.save(buffer, format=fmt)
                content = buffer.getvalue()
            raw_text = self._extract_text(content)
            return self._parse_text(raw_text)
        except (AuthenticationError, RateLimitError, ImageError, BeanLensError):
            raise
        except Exception as exc:
            raise ImageError(f"Failed to extract info with OCR: {exc}") from exc

    @staticmethod
    def _parse_text(raw_text: str) -> BeanInfo:
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]

        roastery = _extract_labeled_value(lines, ["roastery", "roaster", "brand", "로스터리", "로스터"])
        name = _extract_labeled_value(lines, ["name", "bean", "coffee", "원두명", "이름"])
        country_raw = _extract_labeled_value(lines, ["origin", "country", "원산지", "오리진"])
        variety_raw = _extract_labeled_value(lines, ["variety", "varietal", "품종"])
        process = _extract_labeled_value(lines, ["process", "processing", "가공", "프로세스"])
        roast_level = _extract_labeled_value(lines, ["roast", "roast level", "배전도", "로스팅"])
        flavor_raw = _extract_labeled_value(
            lines,
            ["flavor notes", "flavour notes", "flavor", "flavour", "taste", "note", "향미", "노트"],
        )
        altitude = _extract_labeled_value(lines, ["altitude", "elevation", "고도"])

        country = _normalize_country(country_raw or _guess_country(lines))

        if roastery is None and lines:
            roastery = lines[0][:80]

        return BeanInfo(
            roastery=roastery,
            name=name,
            origin=Origin(country=country) if country else None,
            variety=_split_values(variety_raw),
            process=process,
            roast_level=roast_level,
            flavor_notes=_split_values(flavor_raw),
            altitude=altitude,
        )


def _extract_labeled_value(lines: list[str], labels: list[str]) -> str | None:
    patterns = [re.compile(rf"^\s*{re.escape(label)}\s*[:：]\s*(.+)$", re.IGNORECASE) for label in labels]
    for line in lines:
        for pattern in patterns:
            match = pattern.search(line)
            if match:
                value = match.group(1).strip()
                if value:
                    return value
    return None


def _split_values(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    values = [item.strip() for item in re.split(r"[,/|·•]", raw) if item.strip()]
    return values or None


def _normalize_country(raw: str | None) -> str | None:
    if not raw:
        return None
    lowered = raw.lower()
    for alias, canonical in _COUNTRY_ALIASES.items():
        if alias in lowered:
            return canonical
    return raw.strip() or None


def _guess_country(lines: list[str]) -> str | None:
    joined = "\n".join(lines).lower()
    for alias, canonical in _COUNTRY_ALIASES.items():
        if alias in joined:
            return canonical
    return None
