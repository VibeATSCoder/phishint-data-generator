from __future__ import annotations

from fastapi import APIRouter

from app.api.schemas.technique import TechniqueInfoSchema, TechniquesListResponse
from app.core.registry import TechniqueRegistry

router = APIRouter()


@router.get("/techniques", response_model=TechniquesListResponse)
async def list_techniques() -> TechniquesListResponse:
    """
    Return all registered techniques grouped by category,
    with full metadata and option specifications.
    """
    all_techniques = TechniqueRegistry.all()
    groups: dict[str, list[TechniqueInfoSchema]] = {}

    for cls in all_techniques:
        group_name = cls.GROUP.value
        info = TechniqueInfoSchema(**cls.to_info_dict())
        groups.setdefault(group_name, []).append(info)

    return TechniquesListResponse(
        total=len(all_techniques),
        groups=groups,
    )
