from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from app.core.engine import RunResult
from app.core.registry import TechniqueRegistry
from app.core.screenshot import ScreenshotService

logger = logging.getLogger(__name__)


@dataclass
class ScreenshotItem:
    filename: str
    png_bytes: bytes | None
    manifest_entry: dict


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug(name: str, max_len: int = 30) -> str:
    s = _SLUG_RE.sub("_", name.lower()).strip("_")
    return s[:max_len] or "technique"


async def render_run_screenshots(
    result: RunResult,
    service: ScreenshotService,
) -> list[ScreenshotItem]:
    """Render screenshots for original, each successful technique with HTML output, and final.

    URL-only techniques get a manifest entry that points to the previous frame
    (no new PNG is rendered).
    Returns an ordered list ready for ZIP writing.
    """
    items: list[ScreenshotItem] = []
    if not service.enabled:
        return items

    try:
        png = await service.capture(result.original_html, base_url=result.original_url)
        items.append(ScreenshotItem(
            filename="screenshots/00_original.png",
            png_bytes=png,
            manifest_entry={
                "file": "00_original.png",
                "kind": "original",
                "url": result.original_url,
            },
        ))
    except Exception as e:
        logger.warning("original screenshot failed: %s", e)
        items.append(ScreenshotItem(
            filename="screenshots/00_original.png",
            png_bytes=None,
            manifest_entry={
                "file": "00_original.png",
                "kind": "original",
                "url": result.original_url,
                "error": f"render failed: {e}",
            },
        ))

    last_rendered_file = items[0].filename.split("/")[-1]
    last_url = result.original_url

    seq = 1
    for tr in result.technique_results:
        if not tr.success:
            continue
        cls = TechniqueRegistry.get(tr.technique_id)
        cats = [c.value for c in cls.CATEGORIES] if cls else []
        applied_url = tr.modified_url or last_url

        if tr.html_after is None:
            items.append(ScreenshotItem(
                filename="",
                png_bytes=None,
                manifest_entry={
                    "file": last_rendered_file,
                    "kind": "technique",
                    "technique_id": tr.technique_id,
                    "technique_name": tr.technique_name,
                    "categories": cats,
                    "applied_url": applied_url,
                    "shares_render_with_previous": True,
                },
            ))
        else:
            fname = f"{seq:02d}_T{tr.technique_id:02d}_{_slug(tr.technique_name)}.png"
            try:
                png = await service.capture(tr.html_after, base_url=applied_url)
            except Exception as e:
                logger.warning("screenshot T%s failed: %s", tr.technique_id, e)
                png = None
            entry = {
                "file": fname,
                "kind": "technique",
                "technique_id": tr.technique_id,
                "technique_name": tr.technique_name,
                "categories": cats,
                "applied_url": applied_url,
            }
            if png is None:
                entry["error"] = "render failed"
            items.append(ScreenshotItem(
                filename=f"screenshots/{fname}",
                png_bytes=png,
                manifest_entry=entry,
            ))
            if png is not None:
                last_rendered_file = fname
        if tr.modified_url:
            last_url = tr.modified_url
        seq += 1

    try:
        png = await service.capture(result.final_html, base_url=result.final_url)
        items.append(ScreenshotItem(
            filename="screenshots/99_final.png",
            png_bytes=png,
            manifest_entry={
                "file": "99_final.png",
                "kind": "final",
                "url": result.final_url,
            },
        ))
    except Exception as e:
        logger.warning("final screenshot failed: %s", e)
        items.append(ScreenshotItem(
            filename="screenshots/99_final.png",
            png_bytes=None,
            manifest_entry={
                "file": "99_final.png",
                "kind": "final",
                "url": result.final_url,
                "error": f"render failed: {e}",
            },
        ))

    return items
