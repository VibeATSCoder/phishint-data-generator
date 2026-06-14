from __future__ import annotations

from pydantic import BaseModel


class OptionSpecSchema(BaseModel):
    name: str
    description: str
    type: str
    default: object
    min_value: object | None = None
    max_value: object | None = None


class TechniqueInfoSchema(BaseModel):
    id: int
    name: str
    group: str
    categories: list[str]
    description: str
    requirements: list[str]
    options: list[OptionSpecSchema]


class TechniquesListResponse(BaseModel):
    total: int
    groups: dict[str, list[TechniqueInfoSchema]]
