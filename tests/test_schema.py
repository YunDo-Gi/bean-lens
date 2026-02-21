"""Tests for schema models."""

from bean_lens import BeanInfo, Origin


def test_origin_all_none():
    """Origin with no data should work."""
    origin = Origin()
    assert origin.country is None
    assert origin.region is None
    assert origin.farm is None


def test_origin_with_data():
    """Origin with data should store correctly."""
    origin = Origin(country="Ethiopia", region="Yirgacheffe", farm="Konga")
    assert origin.country == "Ethiopia"
    assert origin.region == "Yirgacheffe"
    assert origin.farm == "Konga"


def test_bean_info_all_none():
    """BeanInfo with no data should work."""
    info = BeanInfo()
    assert info.roastery is None
    assert info.name is None
    assert info.origin is None
    assert info.flavor_notes is None


def test_bean_info_with_data():
    """BeanInfo with data should store correctly."""
    info = BeanInfo(
        roastery="Fritz Coffee",
        name="Ethiopia Yirgacheffe",
        origin=Origin(country="Ethiopia", region="Yirgacheffe"),
        variety=["Heirloom"],
        process="Washed",
        roast_level="Light",
        flavor_notes=["Citrus", "Jasmine", "Honey"],
        altitude="1800-2000m",
    )
    assert info.roastery == "Fritz Coffee"
    assert info.origin.country == "Ethiopia"
    assert info.variety == ["Heirloom"]
    assert len(info.flavor_notes) == 3


def test_bean_info_partial_data():
    """BeanInfo with partial data should work."""
    info = BeanInfo(
        roastery="Some Roastery",
        flavor_notes=["Chocolate"],
    )
    assert info.roastery == "Some Roastery"
    assert info.name is None
    assert info.origin is None
    assert info.flavor_notes == ["Chocolate"]


def test_bean_info_json_serialization():
    """BeanInfo should serialize to JSON correctly."""
    info = BeanInfo(
        roastery="Test",
        origin=Origin(country="Kenya"),
    )
    json_str = info.model_dump_json()
    assert "Test" in json_str
    assert "Kenya" in json_str


def test_bean_info_json_deserialization():
    """BeanInfo should deserialize from JSON correctly."""
    json_str = '{"roastery": "Test", "origin": {"country": "Brazil"}}'
    info = BeanInfo.model_validate_json(json_str)
    assert info.roastery == "Test"
    assert info.origin.country == "Brazil"
