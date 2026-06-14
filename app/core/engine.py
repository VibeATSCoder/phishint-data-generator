from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from app.core.analyzer import HTMLAnalyzer, HTMLFeatures
from app.core.registry import TechniqueRegistry
from app.techniques.base import ApplyResult, ChangeEntry
from app.utils.html_utils import normalize_charset_utf8


@dataclass
class TechniqueRunResult:
    technique_id: int
    technique_name: str
    success: bool
    error: str | None
    modified_url: str | None
    extra_file_names: list[str]
    changes: list[ChangeEntry]
    html_after: str | None = None
    url_before: str | None = None

    def to_dict(self) -> dict:
        d: dict = {
            "technique_id": self.technique_id,
            "technique_name": self.technique_name,
            "success": self.success,
            "error": self.error,
            "modified_url": self.modified_url,
            "extra_file_names": self.extra_file_names,
            "changes": [c.to_dict() for c in self.changes],
            "url_before": self.url_before,
        }
        if self.html_after is not None:
            d["html_after"] = self.html_after
        return d


@dataclass
class RunResult:
    run_id: str
    original_html: str
    original_url: str
    final_html: str
    final_url: str
    extra_files: dict[str, bytes] = field(default_factory=dict)
    technique_results: list[TechniqueRunResult] = field(default_factory=list)
    report_markdown: str | None = None


@dataclass
class TechniqueConfig:
    technique_id: int
    options: dict[str, Any] = field(default_factory=dict)


class GenerationEngine:
    """
    Orchestrates technique application in single or hybrid (chained) mode.

    Hybrid mode: techniques are applied sequentially; each technique's
    output (html, url) becomes the input for the next.

    Non-hybrid mode: each technique is applied independently to the
    ORIGINAL html/url; results are collected separately.
    """

    def __init__(self) -> None:
        self.analyzer = HTMLAnalyzer()

    def run(
        self,
        html: str,
        url: str,
        technique_configs: list[TechniqueConfig],
        hybrid_mode: bool = True,
        screenshot_bytes: bytes | None = None,
        llm_credentials: dict[str, Any] | None = None,
    ) -> RunResult:
        from app.techniques.base import set_log_context
        run_id = str(uuid.uuid4())

        with set_log_context(run_id=run_id):
            return self._run_locked(
                html, url, technique_configs, hybrid_mode,
                screenshot_bytes, llm_credentials, run_id,
            )

    def _run_locked(
        self,
        html: str,
        url: str,
        technique_configs: list[TechniqueConfig],
        hybrid_mode: bool,
        screenshot_bytes: bytes | None,
        llm_credentials: dict[str, Any] | None,
        run_id: str,
    ) -> RunResult:
        current_html = html
        current_url = url
        accumulated_extra: dict[str, bytes] = {}
        technique_results: list[TechniqueRunResult] = []

        for config in technique_configs:
            cls = TechniqueRegistry.get(config.technique_id)
            if cls is None:
                technique_results.append(TechniqueRunResult(
                    technique_id=config.technique_id,
                    technique_name=f"Unknown technique {config.technique_id}",
                    success=False,
                    error=f"Technique ID {config.technique_id} not found in registry",
                    modified_url=None,
                    extra_file_names=[],
                    changes=[],
                ))
                continue

            features = self.analyzer.analyze(
                current_html if hybrid_mode else html,
                current_url if hybrid_mode else url,
            )
            eligibility = self.analyzer.evaluate_eligibility(features, [cls])[0]

            if not eligibility.is_applicable:
                technique_results.append(TechniqueRunResult(
                    technique_id=cls.TECHNIQUE_ID,
                    technique_name=cls.TECHNIQUE_NAME,
                    success=False,
                    error=eligibility.reason,
                    modified_url=None,
                    extra_file_names=[],
                    changes=[],
                ))
                continue

            merged = cls.get_default_options()
            merged.update(config.options)
            if llm_credentials:
                for k, v in llm_credentials.items():
                    if v is None or v == "":
                        continue
                    merged.setdefault(f"_llm_{k}", v)

            input_html = current_html if hybrid_mode else html
            input_url = current_url if hybrid_mode else url

            try:
                instance = cls()
                result: ApplyResult = instance.apply(
                    html=input_html,
                    url=input_url,
                    options=merged,
                    screenshot_bytes=screenshot_bytes,
                )

                normalized_html = (
                    normalize_charset_utf8(result.modified_html)
                    if result.modified_html is not None
                    else None
                )

                if hybrid_mode:
                    if normalized_html is not None:
                        current_html = normalized_html
                    if result.modified_url is not None:
                        current_url = result.modified_url

                accumulated_extra.update(result.extra_files)

                technique_results.append(TechniqueRunResult(
                    technique_id=cls.TECHNIQUE_ID,
                    technique_name=cls.TECHNIQUE_NAME,
                    success=True,
                    error=None,
                    modified_url=result.modified_url,
                    extra_file_names=list(result.extra_files.keys()),
                    changes=result.change_log,
                    html_after=normalized_html,
                    url_before=input_url if result.modified_url is not None else None,
                ))

            except Exception as exc:
                technique_results.append(TechniqueRunResult(
                    technique_id=cls.TECHNIQUE_ID,
                    technique_name=cls.TECHNIQUE_NAME,
                    success=False,
                    error=str(exc),
                    modified_url=None,
                    extra_file_names=[],
                    changes=[],
                ))

        return RunResult(
            run_id=run_id,
            original_html=html,
            original_url=url,
            final_html=current_html,
            final_url=current_url,
            extra_files=accumulated_extra,
            technique_results=technique_results,
        )
