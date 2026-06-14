"""Crawler routes — single-URL `/scrape` and CSV-driven `/crawl-bulk`."""
from __future__ import annotations

import asyncio
import base64
import csv as csvlib
import io
import ipaddress
import json
import logging
import shutil
import socket
import uuid
import zipfile

logger = logging.getLogger(__name__)
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.api.schemas.jobs import JobCreateResponse
from app.config import get_settings
from app.core.crawl_engine import derive_id_from_url, sanitize_entry_id
from app.core.job_runner import get_job_runner
from app.core.job_store import get_job_store, job_dir
from app.core.screenshot import get_screenshot_service
from app.utils.html_utils import inject_base_href, normalize_charset_utf8
from app.utils.upload_utils import read_with_cap

router = APIRouter()


def _is_valid_http_url(url: str) -> bool:
    try:
        p = urlparse(url)
        return p.scheme in ("http", "https") and bool(p.hostname)
    except Exception:
        return False


async def _assert_no_ssrf(url: str) -> None:
    """Resolve the URL's hostname and refuse private / loopback / reserved IPs.

    Bulk-crawl mode bypasses this check because operators may legitimately want
    to scrape internal sites; only the public-facing `/scrape` endpoint applies
    it.
    """
    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        raise HTTPException(400, "url has no hostname")
    try:
        ip_str = await asyncio.get_event_loop().run_in_executor(
            None, socket.gethostbyname, host,
        )
        ip = ipaddress.ip_address(ip_str)
    except (socket.gaierror, ValueError) as exc:
        raise HTTPException(400, f"url hostname does not resolve: {exc}")
    if ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local or ip.is_multicast:
        raise HTTPException(
            400,
            f"url resolves to a non-public address ({ip}); refusing SSRF target",
        )


@router.post("/scrape")
async def scrape_single(
    url: str = Form(..., description="URL to scrape (https://… or bare host)"),
    full_page: bool = Form(True, description="Full-page screenshot (vs viewport-only)"),
    timeout_ms: int = Form(25000, description="Per-page Playwright timeout"),
) -> dict:
    """Scrape a single URL and return HTML + screenshot in a base64-encoded ZIP.
    Synchronous — for bulk runs use POST /crawl-bulk.
    Refuses URLs that resolve to private / loopback / reserved addresses
    (SSRF guard).
    """
    target = url.strip()
    if not target:
        raise HTTPException(400, "url is required")
    if "://" not in target:
        target = "https://" + target
    if not _is_valid_http_url(target):
        raise HTTPException(400, "url must use http:// or https:// scheme")
    await _assert_no_ssrf(target)

    svc = get_screenshot_service()
    if not svc.enabled:
        raise HTTPException(503, "Screenshot service disabled (Playwright unavailable)")

    try:
        scraped = await svc.scrape_url(target, timeout_ms=timeout_ms, full_page=full_page)
    except HTTPException:
        raise
    except Exception as exc:
        msg = str(exc).splitlines()[0][:200] if str(exc) else type(exc).__name__
        raise HTTPException(502, f"Scrape failed: {msg}")

    eid = derive_id_from_url(target)
    html = scraped["html"]
    png = scraped["screenshot_png"]
    final_url = scraped.get("final_url", target)
    html = inject_base_href(normalize_charset_utf8(html), final_url)

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"legitimate_html_archive/{eid}.html", html.encode("utf-8", errors="replace"))
        zf.writestr(f"screenshots/{eid}.png", png)
        zf.writestr("summary.json", json.dumps({
            "id": eid, "url": url, "final_url": final_url,
            "html_bytes": len(html.encode("utf-8", errors="replace")),
            "screenshot_bytes": len(png),
        }, indent=2).encode("utf-8"))
    zip_bytes = zip_buf.getvalue()

    return {
        "id": eid,
        "url": url,
        "final_url": final_url,
        "html_bytes": len(html.encode("utf-8", errors="replace")),
        "screenshot_bytes": len(png),
        "zip_base64": base64.b64encode(zip_bytes).decode(),
        "file_names": [
            f"legitimate_html_archive/{eid}.html",
            f"screenshots/{eid}.png",
            "summary.json",
        ],
    }


def _url_from_filename(fname: str) -> str:
    """Derive URL from the dataset filename pattern `YYYYMMDD__domain.tld__hash.html`.
    Returns empty string if pattern doesn't match."""
    parts = fname.split("__")
    if len(parts) >= 3 and parts[1].strip():
        return "https://" + parts[1].strip()
    return ""


def _csv_to_crawl_manifest(csv_bytes: bytes, defaults: dict) -> dict:
    """CSV → crawl manifest. Accepts either of two formats:

    A) ``url`` column (and optional ``id``) — straightforward case.
    B) ``html_filename`` column (and optional ``id`` / ``url``) — matches the
       dataset format `id,html_filename` where each filename follows the
       pattern ``YYYYMMDD__domain.tld__hash.html``. URL is derived from the
       domain segment, and the scraped HTML is saved using *that exact
       filename* (so the crawler output drops straight into a
       ``legitimate_html_archive`` folder that matches the CSV).

    A per-row ``url`` (when present) always wins over the derived URL.
    """
    text = csv_bytes.decode("utf-8-sig", errors="replace")
    reader = csvlib.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(422, "csv_file is empty or missing a header row")
    fields = {f.strip().lower(): f for f in reader.fieldnames if f}

    has_url = "url" in fields
    has_fname = "html_filename" in fields
    if not has_url and not has_fname:
        raise HTTPException(
            422,
            "csv_file must have either a 'url' column or an 'html_filename' column",
        )

    settings = get_settings()
    entries: list[dict] = []
    seen_ids: set[str] = set()
    derive_errors: list[str] = []

    for i, row in enumerate(reader, start=2):
        if not row:
            continue

        fname = (row.get(fields["html_filename"]) or "").strip() if has_fname else ""
        url = (row.get(fields["url"]) or "").strip() if has_url else ""

        if not url and fname:
            url = _url_from_filename(fname)
            if not url:
                derive_errors.append(
                    f"row {i}: could not derive URL from filename '{fname}' "
                    "(expected pattern YYYYMMDD__domain__hash.html)"
                )
                continue

        if not url:
            continue

        if fname:
            eid = fname[:-5] if fname.lower().endswith(".html") else fname
        else:
            eid = (row.get(fields["id"]) or "").strip() if "id" in fields else ""
        if not eid:
            eid = derive_id_from_url(url)
        eid = sanitize_entry_id(eid)
        if not eid:
            eid = derive_id_from_url(url) or f"row_{i}"

        base = eid
        n = 2
        while eid in seen_ids:
            eid = f"{base}_{n}"; n += 1
        seen_ids.add(eid)

        entries.append({"id": eid, "url": url})

        if len(entries) > settings.bulk_max_entries:
            raise HTTPException(
                413,
                f"too many entries ({len(entries)} > limit {settings.bulk_max_entries})",
            )

    if not entries:
        msg = "csv_file produced no entries"
        if derive_errors:
            msg += " — " + "; ".join(derive_errors[:3])
        raise HTTPException(422, msg)

    defaults_out = dict(defaults)
    if derive_errors:
        defaults_out["_csv_derive_errors"] = derive_errors[:50]

    return {
        "kind": "crawl",
        "defaults": defaults_out,
        "entries": entries,
    }


@router.post("/crawl-bulk", response_model=JobCreateResponse)
async def crawl_bulk(
    csv_file: UploadFile = File(
        ...,
        description=(
            "CSV in either of two formats:\n"
            "  • `url` column (+ optional `id`)\n"
            "  • `html_filename` column (+ optional `id`/`url`) — URL is "
            "derived from the `YYYYMMDD__domain__hash.html` pattern and the "
            "scraped HTML is saved using that exact filename."
        ),
    ),
    defaults_json: str = Form(
        "",
        description="Optional JSON object with crawl defaults: timeout_ms, full_page, wait_until, concurrency.",
    ),
) -> JobCreateResponse:
    """Submit a bulk crawl job. Each entry's URL is scraped (HTML + screenshot)
    into the per-job output folder. Reuses /jobs endpoints for status & download.

    Output layout (downloadable as `results.zip`):
        legitimate_html_archive/<id>.html    ← `<id>` equals the CSV's `html_filename` (minus .html) when that column is used
        screenshots/<id>.png
        summary.csv                          ← columns: entry_id, target_url, final_url, status, html_path, screenshot_path, html_bytes, error
        failed.json
        manifest_echo.json
    """
    svc = get_screenshot_service()
    if not svc.enabled:
        raise HTTPException(
            503,
            "Screenshot service is disabled (Playwright not available); "
            "cannot accept crawl jobs. Install playwright + browsers on the server.",
        )

    raw = await read_with_cap(
        csv_file, get_settings().max_csv_size_bytes, field_name="csv_file",
    )
    if not raw:
        raise HTTPException(400, "csv_file is empty")

    defaults: dict = {}
    if defaults_json.strip():
        try:
            defaults = json.loads(defaults_json)
            if not isinstance(defaults, dict):
                raise ValueError("defaults_json must decode to a JSON object")
        except Exception as exc:
            raise HTTPException(422, f"invalid defaults_json: {exc}")
    settings_ = get_settings()
    requested_conc = int(defaults.get("concurrency", settings_.crawl_default_concurrency))
    capped_conc = max(1, min(requested_conc, settings_.crawl_max_concurrency))
    if capped_conc != requested_conc:
        logger.warning(
            "crawl-bulk: clamping concurrency %d → %d (CRAWL_MAX_CONCURRENCY)",
            requested_conc, capped_conc,
        )
    defaults["concurrency"] = capped_conc
    defaults.setdefault("unreachable_timeout_s", settings_.crawl_unreachable_timeout_s)
    defaults.setdefault("partial_timeout_s", settings_.crawl_partial_timeout_s)
    defaults.setdefault("full_page", True)
    defaults.setdefault("wait_until", "networkidle")
    defaults.setdefault("min_html_bytes", 100)

    manifest = _csv_to_crawl_manifest(raw, defaults)

    job_id = str(uuid.uuid4())
    jdir = job_dir(job_id)
    input_dir = jdir / "input"
    input_dir.mkdir(exist_ok=True)
    (input_dir / "input.csv").write_bytes(raw)

    options = {"concurrency": defaults.get("concurrency", 4)}
    store = get_job_store()
    store.create(job_id, manifest, options, entries_total=len(manifest["entries"]))
    get_job_runner().notify_new_job()

    return JobCreateResponse(
        job_id=job_id, status="pending", entries_total=len(manifest["entries"]),
    )
