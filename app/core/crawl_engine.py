"""Per-entry crawler used by the bulk job runner when manifest.kind == 'crawl'."""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from app.core.screenshot import ScreenshotService
from app.utils.html_utils import inject_base_href, normalize_charset_utf8

logger = logging.getLogger(__name__)


SUMMARY_HEADER = [
    "entry_id", "target_url", "final_url", "status", "network_used",
    "wait_state", "html_path", "screenshot_path", "html_bytes",
    "attempts", "error",
]


@dataclass
class ProxySpec:
    """One network endpoint to try. label='direct' + spec=None means no proxy."""
    label: str
    spec: dict | None


def parse_proxy_url(url: str) -> dict | None:
    """Parse a proxy URL like `http://user:pass@host:port` or `socks5://h:p`
    into Playwright's per-context proxy dict. Returns None for blank/invalid."""
    if not url or not url.strip():
        return None
    raw = url.strip()
    parsed = urlparse(raw if "://" in raw else "http://" + raw)
    if not parsed.hostname:
        return None
    port = parsed.port
    server = f"{parsed.scheme}://{parsed.hostname}" + (f":{port}" if port else "")
    spec: dict = {"server": server}
    if parsed.username:
        spec["username"] = parsed.username
    if parsed.password:
        spec["password"] = parsed.password
    return spec


def build_proxy_list(raw_list: list | None) -> list[ProxySpec]:
    """Convert defaults['proxies'] (list of URL strings or {label,url} objects)
    into ordered ProxySpec list. An empty string means 'direct'."""
    if not raw_list:
        return [ProxySpec(label="direct", spec=None)]
    out: list[ProxySpec] = []
    for i, item in enumerate(raw_list):
        if isinstance(item, dict):
            url = (item.get("url") or item.get("server") or "").strip()
            label = (item.get("label") or "").strip() or f"network_{i+1}"
        else:
            url = str(item or "").strip()
            label = f"network_{i+1}" if i > 0 or url else "direct"
        spec = parse_proxy_url(url) if url else None
        if spec is None and url:
            logger.warning("crawl: ignoring invalid proxy '%s'", url)
            continue
        out.append(ProxySpec(label=label, spec=spec))
    return out or [ProxySpec(label="direct", spec=None)]


@dataclass
class CrawlEntry:
    """One row from the crawl manifest, after defaults have been merged."""
    id: str
    url: str
    full_page: bool = True
    wait_until: str = "networkidle"
    proxies: list[ProxySpec] = field(default_factory=lambda: [ProxySpec("direct", None)])
    min_html_bytes: int = 100
    unreachable_timeout_s: float = 10.0
    partial_timeout_s: float = 25.0


@dataclass
class CrawlResult:
    entry_id: str
    target_url: str
    success: bool
    error: str | None = None
    rows: list[dict] = field(default_factory=list)


_SLUG_RE = re.compile(r"[^a-zA-Z0-9._-]+")


def _safe_slug(s: str, max_len: int = 80) -> str:
    s = _SLUG_RE.sub("_", s.strip()).strip("_")
    if not s:
        s = "entry"
    return s[:max_len]


def sanitize_entry_id(eid: str, max_len: int = 120) -> str:
    """Tighten a user-supplied entry id so it can safely become a filename.

    Strips path separators, `..` traversal, and any character outside
    `[A-Za-z0-9._-]`. Used by every CSV→manifest builder so a row with
    `id: ../../etc/passwd` becomes `etc_passwd`, never escapes the output
    directory.
    """
    if not eid:
        return ""
    s = str(eid).replace("\x00", "")
    s = s.strip(" .")
    s = _SLUG_RE.sub("_", s).strip("_")
    if not s or s in (".", ".."):
        return ""
    return s[:max_len]


def derive_id_from_url(url: str) -> str:
    """Build a filesystem-safe id from a URL: '<host>__<path-slug>'."""
    try:
        p = urlparse(url if "://" in url else "https://" + url)
        host = p.hostname or "host"
        path = (p.path or "").strip("/")
        slug = host
        if path:
            slug += "__" + _safe_slug(path, 60)
        return _safe_slug(slug, 100)
    except Exception:
        return _safe_slug(url, 100)


async def process_crawl_entry(
    entry: CrawlEntry,
    output_root: Path,
    screenshot_service: ScreenshotService,
) -> CrawlResult:
    """Crawl one URL → write `legitimate_html_archive/<id>.html` and
    `screenshots/<id>.png` under `output_root`. Always uses per-kind layout.

    When `entry.proxies` has more than one element, the entry falls through to
    the next network whenever the current attempt fails or returns HTML smaller
    than `entry.min_html_bytes`. The first successful network produces the
    saved artifacts; `network_used` is recorded in the summary row.
    """
    html_dir = output_root / "legitimate_html_archive"
    shots_dir = output_root / "screenshots"
    html_dir.mkdir(parents=True, exist_ok=True)
    shots_dir.mkdir(parents=True, exist_ok=True)

    target = entry.url.strip()
    if not target:
        return CrawlResult(
            entry_id=entry.id, target_url=entry.url, success=False,
            error="empty url",
            rows=[{
                "entry_id": entry.id, "target_url": entry.url, "final_url": "",
                "status": "failed", "network_used": "", "wait_state": "",
                "html_path": "", "screenshot_path": "",
                "html_bytes": 0, "attempts": "", "error": "empty url",
            }],
        )
    if "://" not in target:
        target = "https://" + target

    attempts: list[str] = []

    for proxy_spec in entry.proxies:
        label = proxy_spec.label
        hard_cap = entry.unreachable_timeout_s + entry.partial_timeout_s + 5.0
        try:
            scraped = await asyncio.wait_for(
                screenshot_service.scrape_url(
                    target,
                    unreachable_timeout_ms=int(entry.unreachable_timeout_s * 1000),
                    partial_timeout_ms=int(entry.partial_timeout_s * 1000),
                    full_page=entry.full_page,
                    wait_until=entry.wait_until,
                    proxy=proxy_spec.spec,
                ),
                timeout=hard_cap,
            )
        except asyncio.CancelledError:
            raise
        except asyncio.TimeoutError:
            msg = f"hard_timeout {hard_cap:.0f}s"
            logger.warning("crawl[%s] via %s: %s", entry.id, label, msg)
            attempts.append(f"{label}:{msg}")
            continue
        except Exception as exc:
            msg = f"{type(exc).__name__}: {exc}"
            tag = "unreachable" if "Timeout" in type(exc).__name__ else "error"
            logger.warning("crawl[%s] via %s %s: %s", entry.id, label, tag, msg)
            attempts.append(f"{label}:{tag}:{msg[:120]}")
            continue

        html_text: str = scraped["html"]
        final_url: str = scraped.get("final_url", target)
        png_bytes: bytes = scraped["screenshot_png"]
        html_text = normalize_charset_utf8(html_text)
        html_text = inject_base_href(html_text, final_url)
        html_bytes_obj = html_text.encode("utf-8", errors="replace")

        if len(html_bytes_obj) < entry.min_html_bytes:
            attempts.append(f"{label}:incomplete ({len(html_bytes_obj)} bytes < {entry.min_html_bytes})")
            continue

        html_path = html_dir / f"{entry.id}.html"
        shot_path = shots_dir / f"{entry.id}.png"
        html_path.write_bytes(html_bytes_obj)
        shot_path.write_bytes(png_bytes)

        wait_state = scraped.get("wait_state", "")
        status = "ok" if wait_state and wait_state != "salvaged" else "ok_partial"

        return CrawlResult(
            entry_id=entry.id, target_url=entry.url, success=True, error=None,
            rows=[{
                "entry_id": entry.id,
                "target_url": entry.url,
                "final_url": final_url,
                "status": status,
                "network_used": label,
                "wait_state": wait_state,
                "html_path": f"legitimate_html_archive/{entry.id}.html",
                "screenshot_path": f"screenshots/{entry.id}.png",
                "html_bytes": len(html_bytes_obj),
                "attempts": " | ".join(attempts),
                "error": "",
            }],
        )

    msg = "all networks failed: " + " | ".join(attempts) if attempts else "no proxies tried"
    return CrawlResult(
        entry_id=entry.id, target_url=entry.url, success=False,
        error=msg,
        rows=[{
            "entry_id": entry.id, "target_url": entry.url, "final_url": "",
            "status": "failed", "network_used": "", "wait_state": "",
            "html_path": "", "screenshot_path": "",
            "html_bytes": 0,
            "attempts": " | ".join(attempts),
            "error": msg,
        }],
    )
