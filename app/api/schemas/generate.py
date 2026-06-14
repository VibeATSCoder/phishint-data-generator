from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class TechniqueConfigSchema(BaseModel):
    technique_id: int
    options: dict[str, Any] = {}


class ChangeEntrySchema(BaseModel):
    technique_id: int
    technique_name: str
    change_type: str
    description: str
    before: str | None = None
    after: str | None = None


class TechniqueResultSchema(BaseModel):
    technique_id: int
    technique_name: str
    success: bool
    error: str | None = None
    modified_url: str | None = None
    extra_file_names: list[str] = []
    changes: list[ChangeEntrySchema] = []


class GenerateResponse(BaseModel):
    run_id: str
    original_url: str
    final_url: str
    technique_results: list[TechniqueResultSchema]
    successful_count: int
    failed_count: int
    total_changes: int
    output_files: list[str]
