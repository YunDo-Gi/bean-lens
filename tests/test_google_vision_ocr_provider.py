"""Tests for Google Vision OCR provider parsing."""

from types import SimpleNamespace

from PIL import Image

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


def test_extract_uses_text_llm_when_available():
    class MockOCRClient:
        def text_detection(self, image):
            return SimpleNamespace(
                text_annotations=[SimpleNamespace(description="Roastery: Should be replaced by llm")],
                error=SimpleNamespace(message=""),
            )

    class MockLLMClient:
        class Models:
            @staticmethod
            def generate_content(model, contents, config):
                return SimpleNamespace(
                    text=(
                        '{"roastery":"LLM Roastery","name":"Colombia Castillo",'
                        '"origin":{"country":"Colombia","region":null,"farm":null},'
                        '"variety":["Castillo"],"process":"Washed","roast_level":"Medium-Light",'
                        '"flavor_notes":["Caramel"],"altitude":"1800m"}'
                    )
                )

        models = Models()

    provider = GoogleVisionOCRProvider(client=MockOCRClient(), llm_client=MockLLMClient())
    info = provider.extract(image=Image.new("RGB", (20, 20), color="white"))
    metadata = provider.get_extraction_metadata()

    assert info.roastery == "LLM Roastery"
    assert info.origin is not None
    assert info.origin.country == "Colombia"
    assert info.variety == ["Castillo"]
    assert metadata["parser"] == "ocr_text_llm"


def test_extract_falls_back_when_text_llm_fails():
    class MockOCRClient:
        def text_detection(self, image):
            return SimpleNamespace(
                text_annotations=[SimpleNamespace(description="Roastery: Fallback Roastery\nOrigin: Ethiopia")],
                error=SimpleNamespace(message=""),
            )

    class BrokenLLMClient:
        class Models:
            @staticmethod
            def generate_content(model, contents, config):
                raise RuntimeError("llm unavailable")

        models = Models()

    provider = GoogleVisionOCRProvider(client=MockOCRClient(), llm_client=BrokenLLMClient())
    info = provider.extract(image=Image.new("RGB", (20, 20), color="white"))
    metadata = provider.get_extraction_metadata()

    assert info.roastery == "Fallback Roastery"
    assert info.origin is not None
    assert info.origin.country == "Ethiopia"
    assert metadata["parser"] == "heuristic_fallback"
