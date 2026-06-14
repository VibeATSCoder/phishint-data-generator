from __future__ import annotations

from typing import Any
from pydantic import BaseModel


class JobErrorEntry(BaseModel):
    entry_id: str
    error: str


class JobStatusResponse(BaseModel):
    id: str
    status: str
    kind: str = "generate"
    entries_total: int
    entries_done: int
    entries_failed: int
    current_entry: str | None = None
    in_flight: list[str] = []
    error: str | None = None
    avg_seconds_per_entry: float | None = None
    eta_seconds: float | None = None
    recent_errors: list[JobErrorEntry] = []
    created_at: float
    started_at: float | None = None
    completed_at: float | None = None


class JobsListResponse(BaseModel):
    total: int
    jobs: list[JobStatusResponse]


class JobCreateResponse(BaseModel):
    job_id: str
    status: str
    entries_total: int
