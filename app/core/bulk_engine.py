from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from app.config import get_settings
from app.core.analyzer import HTMLAnalyzer
from app.core.engine import GenerationEngine, RunResult, TechniqueConfig
from app.core.registry import TechniqueRegistry
from app.core.report import ReportBuilder
from app.core.screenshot import ScreenshotService
from app.core.screenshot_pipeline import render_run_screenshots
from app.techniques.base import Requirement
from app.utils.html_utils import normalize_charset_utf8

logger = logging.getLogger(__name__)


@dataclass
class BulkEntry:
    """One entry from manifest.json, after defaults have been merged."""
    id: str
    url: str
    html_path: Path
    screenshot_path: Path | None
    technique_configs: list[dict] | None
    category_filter: list[str] | None
    hybrid_mode: bool
    include_report: bool
    include_screenshots: bool
    output_layout: str = "per_entry"
    legitimate_root: Path | None = None
    llm_credentials: dict | None = None
    auto_url_pairing: bool = False


@dataclass
class EntryResult:
    """Outcome of processing one BulkEntry. Per-technique rows are written
    by the runner to summary.csv; this dataclass is just the in-memory return."""
    entry_id: str
    target_url: str
    success: bool
    error: str | None = None
    technique_rows: list[dict] = field(default_factory=list)
    output_dir: Path | None = None


def _resolve_technique_configs(
    entry: BulkEntry, html: str,
) -> tuple[list[TechniqueConfig], str | None]:
    """Returns (configs, error). If category_filter is set and no explicit
    technique_configs, auto-select all applicable techniques in those categories."""
    if entry.technique_configs is not None:
        try:
            return [TechniqueConfig(**c) for c in entry.technique_configs], None
        except Exception as exc:
            return [], f"invalid technique_configs: {exc}"

    if entry.category_filter:
        analyzer = HTMLAnalyzer()
        feats = analyzer.analyze(html, entry.url)
        elig = analyzer.evaluate_eligibility(
            feats, TechniqueRegistry.all(), category_filter=entry.category_filter,
        )
        ids = [e.technique_id for e in elig if e.is_applicable]
        if not ids:
            return [], (
                f"no applicable techniques for category_filter={entry.category_filter}"
            )
        return [TechniqueConfig(technique_id=i) for i in ids], None

    return [], "neither technique_configs nor category_filter provided"


def _substitute_if_needed(
    configs: list[TechniqueConfig],
    url: str,
    html: str,
) -> tuple[list[TechniqueConfig], str]:
    """For distribution-baked entries (exactly one technique config), check whether
    that technique is actually applicable to this page. If not, find a compatible
    substitute so the entry still produces useful output instead of failing silently.

    Returns (configs, note). note='' means no substitution was made.

    Substitution rules:
    - Only applies to single-technique configs (distribution / baked mode).
    - Prefers a technique from the same GROUP, falls back to any applicable one.
    - Never introduces a REQUIRES_AI technique unless the original also required AI.
    - If no substitute is found at all, returns the original (engine will record
      the reason in the technique row).
    """
    if len(configs) != 1:
        return configs, ""

    tid = configs[0].technique_id
    cls = TechniqueRegistry.get(tid)
    if cls is None:
        return configs, ""

    analyzer = HTMLAnalyzer()
    features = analyzer.analyze(html, url)
    eligibility = analyzer.evaluate_eligibility(features, [cls])[0]
    if eligibility.is_applicable:
        return configs, ""

    original_is_ai = Requirement.REQUIRES_AI in cls.REQUIREMENTS

    all_cls = TechniqueRegistry.all()
    candidates: list[int] = []
    same_group: list[int] = []
    for elig in analyzer.evaluate_eligibility(features, all_cls):
        if not elig.is_applicable or elig.technique_id == tid:
            continue
        sub_cls = TechniqueRegistry.get(elig.technique_id)
        if sub_cls is None:
            continue
        if Requirement.REQUIRES_AI in sub_cls.REQUIREMENTS and not original_is_ai:
            continue
        if set(sub_cls.REQUIREMENTS) == {Requirement.HAS_URL}:
            continue
        candidates.append(elig.technique_id)
        if sub_cls.GROUP == cls.GROUP:
            same_group.append(elig.technique_id)

    if not candidates:
        return configs, ""

    chosen = same_group[0] if same_group else candidates[0]
    note = (
        f"T{tid:02d} not applicable ({eligibility.reason}); "
        f"auto-substituted T{chosen:02d}"
    )
    return [TechniqueConfig(technique_id=chosen)], note


_URL_TECHNIQUE_IDS: list[int] = [1, 2, 3, 4, 5, 6]


def _is_url_only_technique(tid: int) -> bool:
    """True for techniques whose only requirement is HAS_URL (T1–T6)."""
    cls = TechniqueRegistry.get(tid)
    if cls is None:
        return False
    return set(cls.REQUIREMENTS) == {Requirement.HAS_URL}


def _pick_url_technique(seed: str) -> int:
    """Deterministically pick one URL technique (T1–T6) keyed by entry ID."""
    h = int(hashlib.md5(seed.encode(), usedforsecurity=False).hexdigest(), 16)
    return _URL_TECHNIQUE_IDS[h % len(_URL_TECHNIQUE_IDS)]


def _tech_tag(ids: list[int]) -> str:
    """Build the filename tech tag like 'T01_T07_T16'."""
    return "_".join(f"T{i:02d}" for i in ids)


def _categories_for(technique_id: int) -> str:
    cls = TechniqueRegistry.get(technique_id)
    return "|".join(c.value for c in cls.CATEGORIES) if cls else ""


async def process_entry(
    entry: BulkEntry,
    output_root: Path,
    screenshot_service: ScreenshotService,
    timeout_s: float | None = None,
) -> EntryResult:
    """Process one BulkEntry. Output layout depends on entry.output_layout:
    - "per_entry": output_root/<entry.id>/{modified.html, report.md, screenshots/, ...}
    - "per_kind":  output_root/{phishing_html_archive,phishing_url_archive,reports,screenshots,extras}/...
    """
    is_per_kind = entry.output_layout == "per_kind"
    out_dir = output_root if is_per_kind else (output_root / entry.id)
    if not is_per_kind:
        out_dir.mkdir(parents=True, exist_ok=True)
    else:
        output_root.mkdir(parents=True, exist_ok=True)

    try:
        raw = entry.html_path.read_bytes()
        html = raw.decode("utf-8", errors="replace")
    except Exception as exc:
        return EntryResult(
            entry_id=entry.id, target_url=entry.url, success=False,
            error=f"failed to read html: {exc}", output_dir=out_dir,
        )

    if not html.strip():
        return EntryResult(
            entry_id=entry.id, target_url=entry.url, success=False,
            error="html file is empty", output_dir=out_dir,
        )

    if "#DOMAIN#" in html:
        from urllib.parse import urlparse as _urlparse
        _cf_domain = _urlparse(entry.url).netloc or entry.url
        html = html.replace("#DOMAIN#", _cf_domain)

    screenshot_bytes: bytes | None = None
    if entry.screenshot_path and entry.screenshot_path.exists():
        try:
            screenshot_bytes = entry.screenshot_path.read_bytes()
        except Exception as exc:
            logger.warning("[%s] couldn't read reference screenshot: %s", entry.id, exc)

    configs, err = _resolve_technique_configs(entry, html)
    if err:
        return EntryResult(
            entry_id=entry.id, target_url=entry.url, success=False,
            error=err, output_dir=out_dir,
        )

    configs, sub_note = _substitute_if_needed(configs, entry.url, html)
    if sub_note:
        logger.info("[%s] %s", entry.id, sub_note)

    if (
        entry.auto_url_pairing
        and len(configs) == 1
        and not _is_url_only_technique(configs[0].technique_id)
    ):
        url_tid = _pick_url_technique(entry.id)
        configs = configs + [TechniqueConfig(technique_id=url_tid)]
        logger.debug("[%s] auto_url_pairing: added T%02d", entry.id, url_tid)

    from app.techniques.base import set_log_context
    timeout_s = timeout_s if timeout_s is not None else get_settings().bulk_entry_timeout_s
    engine = GenerationEngine()
    try:
        with set_log_context(entry_id=entry.id):
            result: RunResult = await asyncio.wait_for(
                asyncio.to_thread(
                    engine.run,
                    html, entry.url, configs, entry.hybrid_mode, screenshot_bytes,
                    entry.llm_credentials,
                ),
                timeout=timeout_s,
            )
    except asyncio.TimeoutError:
        logger.warning("[%s] engine.run timed out after %.0fs", entry.id, timeout_s)
        return EntryResult(
            entry_id=entry.id, target_url=entry.url, success=False,
            error=f"timed out after {timeout_s:.0f}s", output_dir=out_dir,
        )
    except Exception as exc:
        return EntryResult(
            entry_id=entry.id, target_url=entry.url, success=False,
            error=f"engine.run failed: {exc}", output_dir=out_dir,
        )

    if is_per_kind:
        rows = await _write_per_kind(entry, result, output_root, screenshot_service)
    else:
        rows = await _write_per_entry(entry, result, out_dir, screenshot_service)

    return EntryResult(
        entry_id=entry.id, target_url=entry.url, success=True,
        technique_rows=rows, output_dir=out_dir,
    )


async def _write_per_entry(
    entry: BulkEntry,
    result: RunResult,
    out_dir: Path,
    screenshot_service: ScreenshotService,
) -> list[dict]:
    """Write all artifacts under out_dir/<entry.id>/...; return summary rows."""
    final_html_utf8 = normalize_charset_utf8(result.final_html)
    (out_dir / "modified.html").write_bytes(final_html_utf8.encode("utf-8"))

    url_lines = [
        f"T{tr.technique_id} ({tr.technique_name}): {tr.modified_url}"
        for tr in result.technique_results if tr.success and tr.modified_url
    ]
    if url_lines:
        (out_dir / "url_variations.txt").write_text(
            "URL mutations:\n" + "\n".join(url_lines), encoding="utf-8",
        )

    if entry.include_report:
        result.report_markdown = ReportBuilder.build(result)
        (out_dir / "report.md").write_text(result.report_markdown, encoding="utf-8")

    for fname, data in result.extra_files.items():
        path = out_dir / fname
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    screenshot_filename_by_seq: dict[int, str] = {}
    if entry.include_screenshots and screenshot_service.enabled:
        try:
            items = await render_run_screenshots(result, screenshot_service)
            shots_dir = out_dir / "screenshots"
            shots_dir.mkdir(exist_ok=True)
            seq = 0
            for it in items:
                if it.png_bytes is not None and it.filename:
                    name = it.filename.split("/")[-1]
                    (shots_dir / name).write_bytes(it.png_bytes)
                if it.manifest_entry.get("kind") == "technique":
                    seq += 1
                    screenshot_filename_by_seq[seq] = it.manifest_entry.get("file", "")
            (shots_dir / "manifest.json").write_text(
                json.dumps([it.manifest_entry for it in items], indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning("[%s] screenshot pipeline failed: %s", entry.id, exc)

    rows = []
    seq = 0
    for tr in result.technique_results:
        if tr.success:
            seq += 1
        screenshot_path = ""
        if tr.success and entry.include_screenshots and seq in screenshot_filename_by_seq:
            screenshot_path = (
                f"{entry.id}/screenshots/{screenshot_filename_by_seq[seq]}"
            )
        rows.append({
            "entry_id": entry.id,
            "target_url": entry.url,
            "technique_id": tr.technique_id,
            "technique_name": tr.technique_name,
            "categories": _categories_for(tr.technique_id),
            "applied": tr.success,
            "error": tr.error or "",
            "modified_url": tr.modified_url or "",
            "html_path": f"{entry.id}/modified.html" if tr.success else "",
            "url_path": "",
            "screenshot_path": screenshot_path,
        })
    return rows


async def _write_per_kind(
    entry: BulkEntry,
    result: RunResult,
    output_root: Path,
    screenshot_service: ScreenshotService,
) -> list[dict]:
    """Write artifacts grouped by kind:
       phishing_html_archive/<basename>__T<id>...html
       phishing_url_archive/<basename>__T<id>...txt
       reports/<basename>.md
       screenshots/<basename>/...
       extras/<basename>/...
    """
    basename = entry.id
    html_dir   = output_root / "phishing_html_archive"
    url_dir    = output_root / "phishing_url_archive"
    reports_dir = output_root / "reports"
    shots_dir   = output_root / "screenshots" / basename
    extras_dir  = output_root / "extras" / basename
    html_dir.mkdir(parents=True, exist_ok=True)
    url_dir.mkdir(parents=True, exist_ok=True)

    html_tech_ids = [
        tr.technique_id for tr in result.technique_results
        if tr.success and tr.html_after is not None
    ]
    url_tech_ids = [
        tr.technique_id for tr in result.technique_results
        if tr.success and tr.modified_url is not None
    ]

    tech_html_path: dict[int, str] = {}
    tech_url_path: dict[int, str] = {}

    if entry.hybrid_mode:
        if html_tech_ids:
            tag = _tech_tag(html_tech_ids)
            fname = f"{basename}__{tag}.html"
            (html_dir / fname).write_bytes(
                normalize_charset_utf8(result.final_html).encode("utf-8")
            )
            for tid in html_tech_ids:
                tech_html_path[tid] = f"phishing_html_archive/{fname}"
        if url_tech_ids:
            tag = _tech_tag(url_tech_ids)
            fname = f"{basename}__{tag}.txt"
            (url_dir / fname).write_text(result.final_url, encoding="utf-8")
            for tid in url_tech_ids:
                tech_url_path[tid] = f"phishing_url_archive/{fname}"
    else:
        for tr in result.technique_results:
            if not tr.success:
                continue
            if tr.html_after is not None:
                fname = f"{basename}__T{tr.technique_id:02d}.html"
                (html_dir / fname).write_bytes(
                    normalize_charset_utf8(tr.html_after).encode("utf-8")
                )
                tech_html_path[tr.technique_id] = f"phishing_html_archive/{fname}"
            if tr.modified_url is not None:
                fname = f"{basename}__T{tr.technique_id:02d}.txt"
                (url_dir / fname).write_text(tr.modified_url, encoding="utf-8")
                tech_url_path[tr.technique_id] = f"phishing_url_archive/{fname}"

    if entry.include_report:
        reports_dir.mkdir(parents=True, exist_ok=True)
        result.report_markdown = ReportBuilder.build(result)
        (reports_dir / f"{basename}.md").write_text(
            result.report_markdown, encoding="utf-8",
        )

    if result.extra_files:
        extras_dir.mkdir(parents=True, exist_ok=True)
        for fname, data in result.extra_files.items():
            path = extras_dir / fname
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

    screenshot_filename_by_seq: dict[int, str] = {}
    if entry.include_screenshots and screenshot_service.enabled:
        try:
            items = await render_run_screenshots(result, screenshot_service)
            shots_dir.mkdir(parents=True, exist_ok=True)
            seq = 0
            for it in items:
                if it.png_bytes is not None and it.filename:
                    name = it.filename.split("/")[-1]
                    (shots_dir / name).write_bytes(it.png_bytes)
                if it.manifest_entry.get("kind") == "technique":
                    seq += 1
                    screenshot_filename_by_seq[seq] = it.manifest_entry.get("file", "")
            (shots_dir / "manifest.json").write_text(
                json.dumps([it.manifest_entry for it in items], indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning("[%s] screenshot pipeline failed: %s", entry.id, exc)

    rows = []
    seq = 0
    for tr in result.technique_results:
        if tr.success:
            seq += 1
        screenshot_path = ""
        if tr.success and entry.include_screenshots and seq in screenshot_filename_by_seq:
            screenshot_path = (
                f"screenshots/{basename}/{screenshot_filename_by_seq[seq]}"
            )
        rows.append({
            "entry_id": entry.id,
            "target_url": entry.url,
            "technique_id": tr.technique_id,
            "technique_name": tr.technique_name,
            "categories": _categories_for(tr.technique_id),
            "applied": tr.success,
            "error": tr.error or "",
            "modified_url": tr.modified_url or "",
            "html_path": tech_html_path.get(tr.technique_id, ""),
            "url_path": tech_url_path.get(tr.technique_id, ""),
            "screenshot_path": screenshot_path,
        })
    return rows
