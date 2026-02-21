"""Tests for normalization engine."""

import json

from bean_lens import BeanInfo, Origin, normalize_bean_info
from bean_lens.normalization import NormalizationConfig, NormalizationEngine
import bean_lens.normalization.engine as engine_module


def test_normalize_process_exact():
    bean = BeanInfo(process="Washed")

    result = normalize_bean_info(bean)

    assert result.process is not None
    assert result.process.normalized_key == "washed"
    assert result.process.method == "exact"


def test_normalize_process_alias_korean():
    bean = BeanInfo(process="워시드")

    result = normalize_bean_info(bean)

    assert result.process is not None
    assert result.process.normalized_key == "washed"
    assert result.process.method in {"alias", "exact"}


def test_normalize_roast_level_alias_city():
    bean = BeanInfo(roast_level="City")

    result = normalize_bean_info(bean)

    assert result.roast_level is not None
    assert result.roast_level.normalized_key == "medium"
    assert result.roast_level.method == "alias"


def test_normalize_roast_level_medium_light():
    bean = BeanInfo(roast_level="medium-light")

    result = normalize_bean_info(bean)

    assert result.roast_level is not None
    assert result.roast_level.normalized_key == "medium_light"
    assert result.roast_level.method in {"alias", "exact"}


def test_normalize_roast_level_medium_dark():
    bean = BeanInfo(roast_level="full city")

    result = normalize_bean_info(bean)

    assert result.roast_level is not None
    assert result.roast_level.normalized_key == "medium_dark"
    assert result.roast_level.method == "alias"


def test_normalize_country_korean_name():
    bean = BeanInfo(origin=Origin(country="에티오피아"))

    result = normalize_bean_info(bean)

    assert result.country is not None
    assert result.country.normalized_key == "ET"


def test_normalize_variety_dedupes_by_normalized_key():
    bean = BeanInfo(variety=["Geisha", "Gesha"])

    result = normalize_bean_info(bean)

    assert len(result.varieties) == 1
    assert result.varieties[0].normalized_key == "geisha"


def test_normalize_flavor_note_fuzzy():
    bean = BeanInfo(flavor_notes=["Jasmin"])

    result = normalize_bean_info(bean)

    assert len(result.flavor_notes) == 1
    assert result.flavor_notes[0].normalized_key == "jasmine"


def test_unmapped_writes_unknown_queue(tmp_path):
    queue_path = tmp_path / "unknown.jsonl"
    engine = NormalizationEngine(
        config=NormalizationConfig(unknown_queue_path=str(queue_path))
    )

    item = engine.normalize_one("process", "Mystery Process")

    assert item.method == "unmapped"
    lines = queue_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1

    payload = json.loads(lines[0])
    assert payload["domain"] == "process"
    assert payload["raw"] == "Mystery Process"


def test_unmapped_generates_warning():
    bean = BeanInfo(process="Mystery Process")

    result = normalize_bean_info(bean)

    assert "process_unmapped" in result.warnings


def test_low_confidence_match_writes_unknown_queue(tmp_path):
    queue_path = tmp_path / "unknown.jsonl"
    engine = NormalizationEngine(
        config=NormalizationConfig(
            unknown_queue_path=str(queue_path),
            fuzzy_threshold=0.7,
            unknown_min_confidence=0.9,
        )
    )

    item = engine.normalize_one("flavor_note", "chocolet")

    assert item.method == "fuzzy"
    lines = queue_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1

    payload = json.loads(lines[0])
    assert payload["reason"] == "low_confidence"
    assert payload["domain"] == "flavor_note"
    assert payload["raw"] == "chocolet"


def test_unmapped_sends_webhook(monkeypatch):
    captured: list[tuple[str, dict, float]] = []

    def fake_send(url: str, payload: dict, *, timeout_sec: float) -> None:
        captured.append((url, payload, timeout_sec))

    monkeypatch.setattr(engine_module, "_send_unknown_webhook", fake_send)

    engine = NormalizationEngine(
        config=NormalizationConfig(
            unknown_queue_webhook_url="https://example.com/hook",
            unknown_queue_webhook_timeout_sec=1.2,
        )
    )
    engine.normalize_one("process", "Mystery Process")

    assert len(captured) == 1
    url, payload, timeout_sec = captured[0]
    assert url == "https://example.com/hook"
    assert timeout_sec == 1.2
    assert payload["domain"] == "process"
    assert payload["reason"] == "no_dictionary_match"
