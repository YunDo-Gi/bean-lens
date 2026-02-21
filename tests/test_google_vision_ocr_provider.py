"""Tests for Google Vision OCR provider parsing."""

from bean_lens.providers.google_vision_ocr import GoogleVisionOCRProvider


def test_parse_text_extracts_labeled_fields():
    text = """
Roastery: Fritz Coffee
Name: Ethiopia Yirgacheffe
Origin: Ethiopia
Variety: Heirloom, Geisha
Process: Washed
Roast Level: Medium-Light
Flavor Notes: Citrus, Jasmine, Honey
Altitude: 1900-2100m
"""

    info = GoogleVisionOCRProvider._parse_text(text)

    assert info.roastery == "Fritz Coffee"
    assert info.name == "Ethiopia Yirgacheffe"
    assert info.origin is not None
    assert info.origin.country == "Ethiopia"
    assert info.variety == ["Heirloom", "Geisha"]
    assert info.process == "Washed"
    assert info.roast_level == "Medium-Light"
    assert info.flavor_notes == ["Citrus", "Jasmine", "Honey"]
    assert info.altitude == "1900-2100m"


def test_parse_text_guesses_country_and_roastery_fallback():
    text = """
Momos Coffee Roasters
Single Origin
케냐 키암부
"""

    info = GoogleVisionOCRProvider._parse_text(text)

    assert info.roastery == "Momos Coffee Roasters"
    assert info.origin is not None
    assert info.origin.country == "Kenya"
