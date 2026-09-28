from __future__ import annotations

import asyncio
import base64
import io
import json
import zipfile
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.config import get_settings
from app.core.engine import GenerationEngine, RunResult, TechniqueConfig
from app.core.report import ReportBuilder
from app.core.registry import TechniqueRegistry
from app.core.screenshot import get_screenshot_service
from app.core.screenshot_pipeline import render_run_screenshots
from app.techniques.base import Requirement
from app.utils.html_utils import normalize_charset_utf8
from app.utils.upload_utils import read_with_cap

router = APIRouter()


@router.post("/generate")
async def generate(
    url: str = Form(..., description="Target URL"),
    html_file: UploadFile = File(..., description="Source HTML file"),
    technique_configs: str = Form(
        ...,
        description=(
            'JSON array of technique configs: '
            '[{"technique_id": 1, "options": {...}}, ...]'
        ),
    ),
    hybrid_mode: bool = Form(
        True,
        description=(
            "Chain techniques sequentially (each gets previous output). "
            "False = apply each independently to original HTML/URL."
        ),
    ),
    include_report: bool = Form(True, description="Include Markdown change report in ZIP"),
    include_screenshots: bool = Form(
        True,
        description=(
            "Render per-technique screenshots into the ZIP (always-on by default). "
            "Set false to skip rendering for faster experiments."
        ),
    ),
    html_only: bool = Form(
        False,
        description="Exclude URL-only techniques and URL-variation artifacts.",
    ),
    llm_provider: str = Form("", description="LLM provider for AI techniques: 'anthropic' or 'openai' (or any OpenAI-compatible API)."),
    llm_base_url: str = Form("", description="LLM base URL (e.g. https://api.openai.com/v1, https://openrouter.ai/api/v1, http://ollama:11434/v1). Empty uses provider default."),
    llm_api_key: str = Form("", description="LLM API key. Per-run; overrides ANTHROPIC_API_KEY env."),
    llm_model: str = Form("", description="LLM model id. Empty uses provider default."),
    screenshot: UploadFile | None = File(None, description="Optional reference screenshot for T23"),
) -> dict:
    """
    Generate phishing variants using the selected techniques.

    Returns JSON with per-technique results and a base64-encoded ZIP.
    The ZIP contains only output from successful techniques.
    """
    settings = get_settings()
    raw = await read_with_cap(
        html_file, settings.max_html_size_bytes, field_name="html_file",
    )
    if not raw:
        raise HTTPException(status_code=400, detail="html_file is empty")
    html = raw.decode("utf-8", errors="replace")

    screenshot_bytes: bytes | None = None
    if screenshot is not None:
        screenshot_bytes = await read_with_cap(
            screenshot, settings.max_screenshot_size_bytes, field_name="screenshot",
        )

    try:
        configs_raw = json.loads(technique_configs)
        if not isinstance(configs_raw, list):
            raise ValueError("technique_configs must be a JSON array")
        configs = [TechniqueConfig(**c) for c in configs_raw]
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid technique_configs: {exc}",
        )

    if not configs:
        raise HTTPException(
            status_code=400,
            detail="technique_configs must contain at least one technique",
        )

    unknown = [
        c.technique_id
        for c in configs
        if TechniqueRegistry.get(c.technique_id) is None
    ]
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown technique IDs: {unknown}",
        )

    if html_only:
        configs = [
            config for config in configs
            if set(TechniqueRegistry.get(config.technique_id).REQUIREMENTS)
            != {Requirement.HAS_URL}
        ]
        if not configs:
            raise HTTPException(
                status_code=400,
                detail=(
                    "HTML-only mode excluded every selected technique; "
                    "select at least one HTML technique (T07-T25)"
                ),
            )

    llm_credentials = {
        "provider": llm_provider, "base_url": llm_base_url,
        "api_key": llm_api_key, "model": llm_model,
    }

    engine = GenerationEngine()
    result: RunResult = await asyncio.to_thread(
        engine.run,
        html,
        url,
        configs,
        hybrid_mode,
        screenshot_bytes,
        llm_credentials,
    )

    if html_only:
        result.final_url = result.original_url
        for technique_result in result.technique_results:
            technique_result.modified_url = None
            technique_result.url_before = None

    if include_report:
        result.report_markdown = ReportBuilder.build(result)

    screenshot_items = []
    screenshot_manifest: list[dict] = []
    if include_screenshots:
        svc = get_screenshot_service()
        if svc.enabled:
            try:
                screenshot_items = await render_run_screenshots(result, svc)
                screenshot_manifest = [it.manifest_entry for it in screenshot_items]
            except Exception as exc:
                screenshot_manifest = [{"error": f"screenshot pipeline failed: {exc}"}]

    applied_count = sum(1 for tr in result.technique_results if tr.success)
    final_html_utf8 = normalize_charset_utf8(result.final_html)

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("modified.html", final_html_utf8.encode("utf-8"))

        url_lines = []
        for tr in result.technique_results:
            if tr.success and tr.modified_url:
                url_lines.append(
                    f"T{tr.technique_id} ({tr.technique_name}): {tr.modified_url}"
                )
        if url_lines:
            zf.writestr(
                "url_variations.txt",
                ("URL mutations:\n" + "\n".join(url_lines)).encode("utf-8"),
            )

        if result.report_markdown:
            zf.writestr("report.md", result.report_markdown.encode("utf-8"))

        for filename, data in result.extra_files.items():
            zf.writestr(filename, data)

        for it in screenshot_items:
            if it.png_bytes is not None and it.filename:
                zf.writestr(it.filename, it.png_bytes)
        if screenshot_manifest:
            zf.writestr(
                "screenshots/manifest.json",
                json.dumps(screenshot_manifest, indent=2, ensure_ascii=False).encode("utf-8"),
            )

    zip_buf.seek(0)
    zip_bytes = zip_buf.read()
    zip_b64 = base64.b64encode(zip_bytes).decode()

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf_r:
        file_names = zf_r.namelist()

    import urllib.parse as _up
    return {
        "run_id": result.run_id,
        "original_html": html,
        "original_url": url,
        "final_url": result.final_url,
        "final_url_encoded": _up.quote(result.final_url, safe=":/?=&%"),
        "applied_count": applied_count,
        "total_count": len(result.technique_results),
        "technique_results": [tr.to_dict() for tr in result.technique_results],
        "file_names": file_names,
        "zip_base64": zip_b64,
    }
