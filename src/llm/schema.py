from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class Category(str, Enum):
    fiction = "fiction"
    non_fiction = "non_fiction"
    poetry = "poetry"
    childrens = "childrens"
    other = "other"


class QualityFlag(str, Enum):
    missing_description = "missing_description"
    low_rating = "low_rating"
    price_outlier = "price_outlier"
    vague_title = "vague_title"


class BookInput(BaseModel):
    """What a caller sends to POST /enrich."""
    title: str
    description: Optional[str] = None
    price_gbp: float
    rating_text: str
    availability_text: str


class EnrichmentOutput(BaseModel):
    """The exact shape POST /enrich always returns. Never anything else."""
    category: Category
    summary: str = Field(max_length=200)
    quality_flags: list[QualityFlag] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
