"""Data models for bean-lens."""

from pydantic import BaseModel


class Origin(BaseModel):
    """Origin information of coffee beans."""

    country: str | None = None
    region: str | None = None
    farm: str | None = None


class BeanInfo(BaseModel):
    """Structured information extracted from coffee bean package."""

    roastery: str | None = None
    name: str | None = None
    origin: Origin | None = None
    variety: list[str] | None = None
    process: str | None = None
    roast_level: str | None = None
    flavor_notes: list[str] | None = None
    roast_date: str | None = None
    altitude: str | None = None
