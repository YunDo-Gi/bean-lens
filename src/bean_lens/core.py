"""Core extraction function."""

import os
from pathlib import Path

from PIL import Image

from bean_lens.providers.base import BaseProvider
from bean_lens.schema import BeanInfo

ImageInput = str | Path | Image.Image


def _build_gemini_provider(api_key: str | None) -> BaseProvider:
    from bean_lens.providers.gemini import GeminiProvider

    return GeminiProvider(api_key=api_key)


def _build_ocr_provider() -> BaseProvider:
    from bean_lens.providers.google_vision_ocr import GoogleVisionOCRProvider

    return GoogleVisionOCRProvider()


def _select_provider(provider: str | None, api_key: str | None) -> BaseProvider:
    provider_name = (provider or os.getenv("BEAN_LENS_PROVIDER", "gemini")).strip().lower()
    if provider_name in {"gemini", "vision"}:
        return _build_gemini_provider(api_key)
    if provider_name in {"ocr", "google_vision_ocr", "google-vision-ocr"}:
        return _build_ocr_provider()
    raise ValueError(f"Unsupported provider: {provider_name}")


def extract(
    image: ImageInput,
    *,
    api_key: str | None = None,
    provider: str | None = None,
) -> BeanInfo:
    """Extract coffee bean information from a package or card image.

    Args:
        image: Image input - file path (str), Path object, or PIL Image.
        api_key: Gemini API key. Falls back to GEMINI_API_KEY env var.
        provider: Provider name (`gemini` or `ocr`). Defaults to
            `BEAN_LENS_PROVIDER` env var, then `gemini`.

    Returns:
        BeanInfo with extracted information. Fields will be None if not found.
    """
    engine = _select_provider(provider, api_key)
    return engine.extract(image)


def extract_with_metadata(
    image: ImageInput,
    *,
    api_key: str | None = None,
    provider: str | None = None,
) -> tuple[BeanInfo, dict[str, str]]:
    """Extract bean info and return provider metadata."""

    engine = _select_provider(provider, api_key)
    result = engine.extract(image)
    metadata = engine.get_extraction_metadata() or {}
    return result, metadata
