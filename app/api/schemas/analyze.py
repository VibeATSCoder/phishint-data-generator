from __future__ import annotations

from pydantic import BaseModel


class AnalyzeTechniqueResult(BaseModel):
    technique_id: int
    technique_name: str
    group: str
    categories: list[str] = []
    is_applicable: bool
    reason: str
    ai_unavailable: bool = False


class HTMLFeaturesSchema(BaseModel):
    has_input_fields: bool
    has_images: bool
    has_inline_svg: bool
    has_favicon: bool
    has_scripts: bool
    has_iframes: bool
    has_password_input: bool
    image_count: int
    form_count: int
    input_count: int
    raw_html_length: int


class AnalyzeResponse(BaseModel):
    url: str
    html_features: HTMLFeaturesSchema
    applicable: list[AnalyzeTechniqueResult]
    inapplicable: list[AnalyzeTechniqueResult]
    applicable_count: int
    inapplicable_count: int
