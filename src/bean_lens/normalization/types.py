"""Data models for normalization output."""

from typing import Literal

from pydantic import BaseModel, Field

Domain = Literal["process", "variety", "roast_level", "country", "flavor_note"]
Method = Literal["exact", "alias", "regex", "fuzzy", "llm_map", "unmapped"]


class NormalizedItem(BaseModel):
    """Normalized representation for a single raw value."""

    domain: Domain
    raw: str
    normalized_key: str | None = None
    normalized_label_en: str | None = None
    normalized_label_ko: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    method: Method = "unmapped"
    candidates: list[str] = Field(default_factory=list)
    reason: str | None = None


class NormalizedBeanInfo(BaseModel):
    """Normalization result for extracted bean information."""

    dictionary_version: str
    process: NormalizedItem | None = None
    roast_level: NormalizedItem | None = None
    country: NormalizedItem | None = None
    varieties: list[NormalizedItem] = Field(default_factory=list)
    flavor_notes: list[NormalizedItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
