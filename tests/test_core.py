"""Tests for core extraction function."""

import pytest

from bean_lens import BeanInfo, Origin, extract
from bean_lens.core import extract_with_metadata
from bean_lens.exceptions import AuthenticationError


def test_extract_requires_api_key(monkeypatch):
    """extract() should raise AuthenticationError without API key."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with pytest.raises(AuthenticationError):
        extract("test.jpg", provider="gemini")


def test_extract_with_mock_gemini_provider(mocker):
    """extract() should return BeanInfo from gemini provider."""
    mock_bean_info = BeanInfo(
        roastery="Test Roastery",
        name="Test Coffee",
        origin=Origin(country="Ethiopia", region="Sidamo"),
        variety=["Heirloom"],
        process="Natural",
        roast_level="Medium",
        flavor_notes=["Berry", "Wine"],
        altitude="1900m",
    )

    mock_provider = mocker.MagicMock()
    mock_provider.extract.return_value = mock_bean_info

    mocker.patch("bean_lens.core._build_gemini_provider", return_value=mock_provider)

    result = extract("test_image.jpg", api_key="test-key", provider="gemini")

    assert result.roastery == "Test Roastery"
    assert result.origin.country == "Ethiopia"
    assert result.flavor_notes == ["Berry", "Wine"]
    mock_provider.extract.assert_called_once_with("test_image.jpg")


def test_extract_returns_partial_info(mocker):
    """extract() should return partial info when some fields missing."""
    mock_bean_info = BeanInfo(
        roastery="Partial Roastery",
        origin=Origin(country="Colombia"),
    )

    mock_provider = mocker.MagicMock()
    mock_provider.extract.return_value = mock_bean_info

    mocker.patch("bean_lens.core._build_gemini_provider", return_value=mock_provider)

    result = extract("test_image.jpg", api_key="test-key", provider="gemini")

    assert result.roastery == "Partial Roastery"
    assert result.origin.country == "Colombia"
    assert result.name is None
    assert result.flavor_notes is None
    assert result.variety is None


def test_extract_uses_ocr_provider_when_selected(mocker):
    mock_provider = mocker.MagicMock()
    mock_provider.extract.return_value = BeanInfo(roastery="OCR")

    mocker.patch("bean_lens.core._build_ocr_provider", return_value=mock_provider)

    result = extract("test_image.jpg", provider="ocr")

    assert result.roastery == "OCR"
    mock_provider.extract.assert_called_once_with("test_image.jpg")


def test_extract_unsupported_provider_raises():
    with pytest.raises(ValueError):
        extract("test_image.jpg", provider="unknown")


def test_extract_with_metadata_includes_parser(mocker):
    mock_provider = mocker.MagicMock()
    mock_provider.extract.return_value = BeanInfo(roastery="OCR")
    mock_provider.get_extraction_metadata.return_value = {"provider": "ocr", "parser": "ocr_text_llm"}

    mocker.patch("bean_lens.core._build_ocr_provider", return_value=mock_provider)

    result, metadata = extract_with_metadata("test_image.jpg", provider="ocr")

    assert result.roastery == "OCR"
    assert metadata["provider"] == "ocr"
    assert metadata["parser"] == "ocr_text_llm"
