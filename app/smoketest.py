"""End-to-end smoke test of the crawl + 25-technique pipeline.

Why this exists
---------------
After the recent crawl improvements (two-phase timeouts, salvage on
partial loads, base-href injection, parallel workers), the reviewer asked
for a *repeatable* way to prove the platform crawls real sites and
applies every technique. This module is that proof:

  python -m app.smoketest [csv_path]

For each URL in the CSV it:
  1. Runs `process_crawl_entry` against the URL.
  2. If the crawl succeeded (`ok` or `ok_partial`), feeds the saved HTML
     through the full 25-technique pipeline in non-hybrid mode.
  3. Prints a per-URL row: crawl status, language detected, techniques
     applied (NN/25), and the first technique error (if any).

Exit code is 0 when:
  • ≥ 60% of URLs crawled successfully, AND
  • ≥ 90% of (URL, technique) pairs applied (or skipped cleanly).

Anything else is non-zero so this script can gate CI / deployment.

It reuses the existing crawl + generation engines verbatim. No new
runtime behaviour is introduced — this is purely a verification harness.
"""
from __future__ import annotations

import argparse
import asyncio
import csv as csvlib
import logging
import sys
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger("phishgen.smoketest")


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def _load_csv(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csvlib.DictReader(f)
        for r in reader:
            url = (r.get("url") or "").strip()
            eid = (r.get("id") or "").strip()
            if not url:
                continue
            if not eid:
                eid = url.replace("https://", "").replace("http://", "")[:48]
            rows.append({"id": eid, "url": url})
    return rows


async def _crawl_one(entry: dict, output_root: Path, service: Any) -> dict:
    """Wrap process_crawl_entry so we always return a result dict."""
    from app.core.crawl_engine import (
        CrawlEntry, ProxySpec, process_crawl_entry,
    )
    crawl_entry = CrawlEntry(
        id=entry["id"], url=entry["url"],
        proxies=[ProxySpec("direct", None)],
        unreachable_timeout_s=10.0, partial_timeout_s=20.0,
        min_html_bytes=100,
    )
    try:
        res = await process_crawl_entry(crawl_entry, output_root, service)
        row = res.rows[0] if res.rows else {}
        return {
            "ok": res.success,
            "status": row.get("status", "failed"),
            "html_path": row.get("html_path", ""),
            "error": res.error or "",
            "wait_state": row.get("wait_state", ""),
        }
    except Exception as exc:
        return {
            "ok": False, "status": "failed",
            "html_path": "", "error": f"{type(exc).__name__}: {exc}",
            "wait_state": "",
        }


def _run_techniques(html_text: str, url: str) -> dict:
    """Apply all 25 techniques (non-hybrid) and count successes."""
    import app.techniques  # noqa: F401
    from app.core.engine import GenerationEngine, TechniqueConfig
    from app.core.registry import TechniqueRegistry
    from app.utils.i18n import detect_language
    engine = GenerationEngine()
    configs = [
        TechniqueConfig(technique_id=cls.TECHNIQUE_ID)
        for cls in TechniqueRegistry.all()
    ]
    try:
        run_result = engine.run(
            html=html_text, url=url, technique_configs=configs,
            hybrid_mode=False, screenshot_bytes=None, llm_credentials=None,
        )
    except Exception as exc:
        return {
            "applied": 0, "total": len(configs),
            "first_error": f"{type(exc).__name__}: {exc}",
            "lang": detect_language(html_text),
        }
    applied = sum(1 for r in run_result.technique_results if r.success)
    first_error = next(
        (r.error for r in run_result.technique_results
         if not r.success and r.error and "not applicable" not in r.error.lower()),
        "",
    )
    return {
        "applied": applied, "total": len(configs),
        "first_error": (first_error or "")[:80],
        "lang": detect_language(html_text),
    }


async def _smoke_async(csv_path: Path) -> int:
    from app.core.screenshot import get_screenshot_service
    rows = _load_csv(csv_path)
    if not rows:
        logger.error("no URLs found in %s", csv_path)
        return 2
    print(f"\nRunning smoke test on {len(rows)} URLs from {csv_path}\n")

    service = get_screenshot_service()
    await service.start()

    with tempfile.TemporaryDirectory(prefix="phishgen_smoke_") as tmp_str:
        tmp = Path(tmp_str)
        results: list[dict] = []

        sem = asyncio.Semaphore(4)
        async def _one(entry: dict) -> dict:
            async with sem:
                crawl = await _crawl_one(entry, tmp, service)
            tech_summary = {"applied": 0, "total": 25, "first_error": "", "lang": "?"}
            html_path = crawl.get("html_path")
            if crawl["ok"] and html_path:
                full_path = tmp / html_path
                try:
                    html_text = full_path.read_text("utf-8", errors="replace")
                    tech_summary = _run_techniques(html_text, entry["url"])
                except Exception as exc:
                    tech_summary["first_error"] = f"{type(exc).__name__}: {exc}"
            return {"entry": entry, "crawl": crawl, "tech": tech_summary}

        for done in asyncio.as_completed([_one(r) for r in rows]):
            results.append(await done)

        await service.stop()

    print(f"{'URL':<55}{'CRAWL':<12}{'LANG':<5}{'WAIT':<28}{'APPLIED':<10}{'NOTE'}")
    print("-" * 130)
    ok = 0
    pair_ok = 0
    pair_total = 0
    for r in results:
        url = r["entry"]["url"]
        c = r["crawl"]
        t = r["tech"]
        crawl_status = c["status"] if c["status"] else ("ok" if c["ok"] else "failed")
        if "unreachable" in (c.get("error") or "").lower() or "unreach" in crawl_status:
            crawl_status = "unreach"
        if c["ok"]:
            ok += 1
        pair_ok += t["applied"]
        pair_total += t["total"]
        note = t["first_error"] or c["error"][:60]
        print(f"{url[:54]:<55}{crawl_status:<12}{t['lang']:<5}"
              f"{c['wait_state'][:26]:<28}"
              f"{t['applied']}/{t['total']:<8}{note[:50]}")
    print("-" * 130)

    crawl_rate = ok / len(rows)
    pair_rate = (pair_ok / pair_total) if pair_total else 0.0
    print(f"\nCrawl success rate:  {crawl_rate:.0%} ({ok}/{len(rows)})")
    print(f"Technique apply rate: {pair_rate:.0%} ({pair_ok}/{pair_total})")

    if crawl_rate >= 0.60 and pair_rate >= 0.90:
        print("\n✅ SMOKETEST PASSED — crawl ≥60% + technique apply ≥90%")
        return 0
    print("\n❌ SMOKETEST FAILED — see breakdown above")
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Smoke-test the crawl + 25-technique pipeline.")
    parser.add_argument("csv_path", nargs="?", default="tests/data/smoketest_urls.csv",
                        help="CSV of URLs to crawl (default: bundled sample)")
    parser.add_argument("-v", "--verbose", action="store_true", help="DEBUG logs")
    args = parser.parse_args(argv)
    _setup_logging(args.verbose)
    csv_path = Path(args.csv_path)
    if not csv_path.exists():
        print(f"CSV not found: {csv_path}", file=sys.stderr)
        return 2
    try:
        return asyncio.run(_smoke_async(csv_path))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
