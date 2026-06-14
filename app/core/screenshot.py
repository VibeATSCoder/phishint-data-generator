from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)


_CHARSET_RE = re.compile(r'<meta[^>]+charset[^>]*>', re.IGNORECASE)
_HEAD_RE = re.compile(r'(<head(\s[^>]*)?>)', re.IGNORECASE)
_HTML_RE = re.compile(r'(<html(\s[^>]*)?>)', re.IGNORECASE)


def _inject_base_and_charset(html: str, base_url: str | None) -> str:
    """Inject UTF-8 charset + <base href> so relative assets resolve and
    non-ASCII content renders correctly."""
    html = _CHARSET_RE.sub('', html)

    base_tag = ''
    if base_url:
        url = base_url
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url.lstrip('/')
        base_tag = f'<base href="{url}" target="_blank">'
    inject = '<meta charset="utf-8">' + (f'\n  {base_tag}' if base_tag else '')

    if _HEAD_RE.search(html):
        return _HEAD_RE.sub(lambda m: m.group(0) + '\n  ' + inject, html, count=1)
    if _HTML_RE.search(html):
        return _HTML_RE.sub(
            lambda m: m.group(0) + f'\n<head>{inject}</head>', html, count=1
        )
    return inject + html


class ScreenshotService:
    """Renders HTML strings to PNG bytes using a long-lived Chromium instance.

    The browser is recycled every `recycle_after` pages to bound memory.
    Thread-safe within a single asyncio event loop; do not share across loops.
    """

    def __init__(self) -> None:
        s = get_settings()
        self._enabled = s.screenshot_enabled
        self._timeout_ms = s.screenshot_timeout_ms
        self._viewport = (s.screenshot_viewport_width, s.screenshot_viewport_height)
        self._recycle_after = s.screenshot_browser_recycle_after
        self._playwright: Any = None
        self._browser: Any = None
        self._pages_since_recycle = 0
        self._recycle_lock = asyncio.Lock()
        self._active = 0
        self._start_lock = asyncio.Lock()
        self._started = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def start(self) -> None:
        async with self._start_lock:
            if not self._enabled or self._started:
                return
            try:
                from playwright.async_api import async_playwright
            except ImportError:
                logger.warning("playwright not installed; screenshots disabled")
                self._enabled = False
                return
            self._playwright = await async_playwright().start()
            await self._launch_browser()
            self._started = True

    async def _launch_browser(self) -> None:
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        self._pages_since_recycle = 0

    async def _acquire_slot(self) -> None:
        """Reserve a slot to use the browser. Recycles when threshold is hit
        AND no other operations are in flight. Multiple slots can be held
        simultaneously — recycle only fires when active drops to 0.
        """
        async with self._recycle_lock:
            if (
                self._pages_since_recycle >= self._recycle_after
                and self._active == 0
            ):
                try:
                    await self._browser.close()
                except Exception:
                    pass
                await self._launch_browser()
            self._active += 1

    async def _release_slot(self) -> None:
        async with self._recycle_lock:
            self._active = max(0, self._active - 1)
            self._pages_since_recycle += 1
            if (
                self._active == 0
                and self._pages_since_recycle >= self._recycle_after
            ):
                try:
                    await self._browser.close()
                except Exception:
                    pass
                await self._launch_browser()

    async def stop(self) -> None:
        if not self._started:
            return
        try:
            if self._browser is not None:
                await self._browser.close()
        except Exception:
            pass
        try:
            if self._playwright is not None:
                await self._playwright.stop()
        except Exception:
            pass
        self._browser = None
        self._playwright = None
        self._started = False

    async def scrape_url(
        self,
        url: str,
        *,
        timeout_ms: int | None = None,
        unreachable_timeout_ms: int | None = None,
        partial_timeout_ms: int | None = None,
        full_page: bool = True,
        wait_until: str = "networkidle",
        proxy: dict | None = None,
    ) -> dict:
        """Visit `url` with the long-lived browser and return:
            {"html": str, "screenshot_png": bytes, "final_url": str,
             "wait_state": str}

        Two-phase timeout model:
          1. UNREACHABLE phase — `page.goto(wait_until="commit")` with
             `unreachable_timeout_ms`. Succeeds the moment the server's
             first response is received. If it times out here, the site
             is unreachable and we raise so the proxy fallback can try
             the next network.
          2. PARTIAL phase — wait for the requested `wait_until`
             (typically `networkidle`) with `partial_timeout_ms`. If this
             times out, we salvage: take page.content() + screenshot of
             whatever painted. Most real sites (analytics-heavy, long-poll)
             never fire networkidle but their DOM is fine after 2-3s.

        `timeout_ms` is a legacy single value used when the two specific
        values aren't supplied; it's split 30/70 between the phases.
        """
        if not self._enabled:
            raise RuntimeError("Screenshot service is disabled")
        if not self._started:
            await self.start()
            if not self._enabled:
                raise RuntimeError("Screenshot service is disabled (playwright unavailable)")

        legacy_total = timeout_ms or self._timeout_ms
        unreachable = int(unreachable_timeout_ms or max(3000, int(legacy_total * 0.3)))
        partial = int(partial_timeout_ms or max(5000, int(legacy_total * 0.7)))
        timeout = partial

        await self._acquire_slot()
        try:
            ctx_kwargs: dict = dict(
                viewport={"width": self._viewport[0], "height": self._viewport[1]},
                ignore_https_errors=True,
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
                ),
            )
            if proxy:
                ctx_kwargs["proxy"] = proxy
            ctx = await self._browser.new_context(**ctx_kwargs)
            try:
                page = await ctx.new_page()

                wait_state_used = "salvaged"
                navigation_ok = False
                try:
                    await page.goto(url, wait_until="commit", timeout=unreachable)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.info(
                        "scrape_url: unreachable (%s) within %dms: %s",
                        type(e).__name__, unreachable, url,
                    )
                    raise

                try:
                    await page.wait_for_load_state(wait_until, timeout=partial)
                    wait_state_used = wait_until
                    navigation_ok = True
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.info(
                        "scrape_url: %s not reached within %dms on %s — salvaging",
                        wait_until, partial, url,
                    )
                    try:
                        await page.wait_for_load_state(
                            "domcontentloaded", timeout=2000,
                        )
                        wait_state_used = "domcontentloaded_after_timeout"
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        pass

                try:
                    await page.evaluate("""
                        async () => {
                            const step = 600;
                            let last = -1;
                            let i = 0;
                            while (last !== document.documentElement.scrollHeight && i < 40) {
                                last = document.documentElement.scrollHeight;
                                window.scrollBy(0, step);
                                await new Promise(r => setTimeout(r, 80));
                                i++;
                            }
                            window.scrollTo(0, 0);
                        }
                    """)
                except Exception:
                    pass

                try:
                    html = await page.content()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    raise
                final_url = page.url or url

                shot_timeout_ms = max(5000, min(15000, timeout // 2))
                try:
                    png = await page.screenshot(
                        full_page=full_page, type="png", timeout=shot_timeout_ms,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.debug("scrape_url: full-page screenshot failed (%s); retry viewport-only", e)
                    try:
                        png = await page.screenshot(
                            full_page=False, type="png", timeout=shot_timeout_ms,
                        )
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        png = b""

                if not navigation_ok:
                    logger.info(
                        "scrape_url: salvaged %d HTML bytes from %s after goto timeouts",
                        len(html.encode("utf-8", errors="replace")), url,
                    )

                return {
                    "html": html,
                    "screenshot_png": png,
                    "final_url": final_url,
                    "wait_state": wait_state_used if navigation_ok else "salvaged",
                }
            finally:
                try:
                    await asyncio.shield(ctx.close())
                except Exception:
                    pass
        finally:
            try:
                await asyncio.shield(self._release_slot())
            except Exception:
                pass

    async def capture(
        self,
        html: str,
        base_url: str | None = None,
        full_page: bool = True,
    ) -> bytes:
        """Render HTML to a PNG. Returns bytes. Raises RuntimeError if disabled."""
        if not self._enabled:
            raise RuntimeError("Screenshot service is disabled")
        if not self._started:
            await self.start()
            if not self._enabled:
                raise RuntimeError("Screenshot service is disabled (playwright unavailable)")

        prepared = _inject_base_and_charset(html, base_url)

        await self._acquire_slot()
        try:
            ctx = await self._browser.new_context(
                viewport={"width": self._viewport[0], "height": self._viewport[1]},
                ignore_https_errors=True,
            )
            try:
                page = await ctx.new_page()
                async def _route(route):
                    rt = route.request.resource_type
                    if rt in ("media", "websocket", "manifest", "other"):
                        await route.abort()
                    else:
                        await route.continue_()
                try:
                    await page.route("**/*", _route)
                except Exception:
                    pass

                try:
                    await page.set_content(
                        prepared,
                        wait_until="networkidle",
                        timeout=self._timeout_ms,
                    )
                except Exception as e:
                    logger.debug("set_content networkidle failed (%s); falling back to load", e)
                    await page.set_content(prepared, wait_until="load", timeout=self._timeout_ms)

                png = await page.screenshot(full_page=full_page, type="png")
                return png
            finally:
                try:
                    await asyncio.shield(ctx.close())
                except Exception:
                    pass
        finally:
            try:
                await asyncio.shield(self._release_slot())
            except Exception:
                pass


_service: ScreenshotService | None = None


def get_screenshot_service() -> ScreenshotService:
    global _service
    if _service is None:
        _service = ScreenshotService()
    return _service
