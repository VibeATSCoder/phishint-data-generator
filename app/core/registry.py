from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.techniques.base import BaseTechnique


class TechniqueRegistry:
    """
    Global registry mapping technique ID → technique class.
    Populated automatically when BaseTechnique subclasses are imported.
    """

    _techniques: dict[int, type[BaseTechnique]] = {}

    @classmethod
    def register(cls, technique_cls: type[BaseTechnique]) -> None:
        tid = technique_cls.TECHNIQUE_ID
        if tid in cls._techniques:
            existing = cls._techniques[tid].__name__
            raise ValueError(
                f"Duplicate TECHNIQUE_ID {tid}: "
                f"'{technique_cls.__name__}' conflicts with '{existing}'"
            )
        cls._techniques[tid] = technique_cls

    @classmethod
    def get(cls, technique_id: int) -> type[BaseTechnique] | None:
        return cls._techniques.get(technique_id)

    @classmethod
    def all(cls) -> list[type[BaseTechnique]]:
        return sorted(cls._techniques.values(), key=lambda t: t.TECHNIQUE_ID)

    @classmethod
    def get_many(cls, ids: list[int]) -> list[type[BaseTechnique]]:
        missing = [i for i in ids if i not in cls._techniques]
        if missing:
            raise ValueError(f"Unknown technique IDs: {missing}")
        return [cls._techniques[i] for i in ids]

    @classmethod
    def count(cls) -> int:
        return len(cls._techniques)
