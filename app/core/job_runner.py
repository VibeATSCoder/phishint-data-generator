from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import time
import zipfile
from pathlib import Path

from app.config import get_settings
from app.core.bulk_engine import BulkEntry, EntryResult, process_entry
from app.core.crawl_engine import (
    CrawlEntry, CrawlResult, process_crawl_entry,
    SUMMARY_HEADER as CRAWL_SUMMARY_HEADER,
)
from app.core.job_store import get_job_store, job_dir
from app.core.screenshot import get_screenshot_service

logger = logging.getLogger(__name__)


SUMMARY_CSV_HEADER = [
    "entry_id", "target_url", "technique_id", "technique_name", "categories",
    "applied", "error", "modified_url", "html_path", "url_path", "screenshot_path",
]

URLS_CSV_HEADER = [
    "entry_id", "original_url", "phishing_url",
    "url_technique_id", "url_technique_name",
    "html_technique_id", "html_technique_name",
    "html_path", "url_path",
]


class _Cancelled(Exception):
    pass


class _Paused(Exception):
    """Raised inside the runner when a pause is requested. Distinct from
    _Cancelled so the outer loop marks the job paused (resumable) instead
    of cancelled (terminal)."""
    pass


def _write_urls_csv(output_dir: Path, summary_path: Path) -> None:
    """Build urls.csv from summary.csv: one consolidated row per entry that
    pairs the HTML technique result with its auto-generated URL variation.
    Written to output_dir/urls.csv so it lands inside the download ZIP.
    """
    if not summary_path.exists():
        return
    try:
        # summary.csv is created with utf-8-sig. Reading it as plain UTF-8
        # leaves the BOM attached to the first field name ("\ufeffentry_id"),
        # which made every resumed job look unfinished and reprocessed all
        # entries. utf-8-sig accepts both BOM and non-BOM files.
        with summary_path.open("r", encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
    except Exception as exc:
        logger.warning("urls.csv: failed to read summary.csv: %s", exc)
        return

    from collections import defaultdict
    by_entry: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        eid = (row.get("entry_id") or "").strip()
        if eid:
            by_entry[eid].append(row)

    urls_path = output_dir / "urls.csv"
    try:
        with urls_path.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(URLS_CSV_HEADER)
            for eid, entry_rows in by_entry.items():
                original_url = (entry_rows[0].get("target_url") or "").strip()
                html_row = next(
                    (r for r in entry_rows
                     if (r.get("html_path") or "").strip()
                     and (r.get("applied") or "").strip().lower() in ("true", "1")),
                    {},
                )
                url_row = next(
                    (r for r in entry_rows
                     if (r.get("modified_url") or "").strip()
                     and (r.get("applied") or "").strip().lower() in ("true", "1")),
                    {},
                )
                w.writerow([
                    eid,
                    original_url,
                    url_row.get("modified_url", ""),
                    url_row.get("technique_id", ""),
                    url_row.get("technique_name", ""),
                    html_row.get("technique_id", ""),
                    html_row.get("technique_name", ""),
                    html_row.get("html_path", ""),
                    url_row.get("url_path", ""),
                ])
    except Exception as exc:
        logger.warning("urls.csv: write failed: %s", exc)


def _read_done_entry_ids(summary_path: Path) -> set[str]:
    """Return the set of entry_ids already written to summary.csv. Used by
    `_run_job` so a resumed job only re-processes entries that didn't
    complete on the previous run."""
    if not summary_path.exists():
        return set()
    done: set[str] = set()
    try:
        # summary.csv is created with utf-8-sig. Reading it as plain UTF-8
        # leaves the BOM attached to the first field name, so resumed jobs do
        # not recognize any completed entry.
        with summary_path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                eid = (row.get("entry_id") or "").strip()
                if eid:
                    done.add(eid)
    except Exception:
        return set()
    return done


class JobRunner:
    """Single-worker async runner. Pulls 'pending' jobs FIFO and processes
    each one's entries with bounded concurrency."""

    def __init__(self) -> None:
        self._store = get_job_store()
        self._task: asyncio.Task | None = None
        self._wakeup = asyncio.Event()
        self._stopping = False
        self._in_flight: dict[str, set[str]] = {}

    def get_in_flight(self, job_id: str) -> list[str]:
        """Return a snapshot of entry_ids currently being processed."""
        s = self._in_flight.get(job_id)
        return sorted(s) if s else []

    async def startup(self) -> None:
        n = self._store.reset_running_to_paused("auto-paused at restart")
        if n:
            logger.warning(
                "auto-paused %d jobs that were running at the last restart "
                "(click Resume to continue)", n,
            )
        self._task = asyncio.create_task(self._loop(), name="job-runner")

    async def shutdown(self) -> None:
        self._stopping = True
        self._wakeup.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5)
            except asyncio.TimeoutError:
                self._task.cancel()
            except Exception:
                pass

    def notify_new_job(self) -> None:
        self._wakeup.set()

    async def _loop(self) -> None:
        while not self._stopping:
            job = self._store.next_pending()
            if job is None:
                self._wakeup.clear()
                try:
                    await asyncio.wait_for(self._wakeup.wait(), timeout=2.0)
                except asyncio.TimeoutError:
                    pass
                continue
            try:
                await self._run_job(job)
            except _Cancelled:
                self._in_flight.pop(job["id"], None)
                self._store.mark_cancelled(job["id"])
                logger.info("job %s cancelled", job["id"])
            except _Paused:
                self._in_flight.pop(job["id"], None)
                self._store.mark_paused(job["id"])
                logger.info("job %s paused (resumable)", job["id"])
            except Exception as exc:
                self._in_flight.pop(job["id"], None)
                logger.exception("job %s failed", job["id"])
                self._store.mark_failed(job["id"], f"{type(exc).__name__}: {exc}")

    async def _run_job(self, job: dict) -> None:
        job_id = job["id"]
        manifest = job["manifest"]
        options = job["options"]
        self._store.mark_running(job_id)

        jdir = job_dir(job_id)
        input_dir = jdir / "input"
        output_dir = jdir / "output"
        output_dir.mkdir(exist_ok=True)

        defaults = manifest.get("defaults", {}) or {}
        entries_raw = manifest.get("entries", []) or []
        kind = (manifest.get("kind") or defaults.get("kind") or "generate").lower()
        settings_ = get_settings()
        default_conc = (
            settings_.crawl_default_concurrency if kind == "crawl"
            else settings_.bulk_default_concurrency
        )
        requested_conc = int(options.get("concurrency",
            defaults.get("concurrency", default_conc)))
        if kind == "crawl":
            requested_conc = min(requested_conc, settings_.crawl_max_concurrency)
        else:
            requested_conc = min(requested_conc, settings_.bulk_max_concurrency)
        concurrency = max(1, requested_conc)

        entry_timeout_s: float | None = None
        if "bulk_entry_timeout_s" in options:
            try:
                entry_timeout_s = float(options["bulk_entry_timeout_s"])
            except (TypeError, ValueError):
                pass

        if kind == "crawl":
            header = CRAWL_SUMMARY_HEADER
        else:
            header = SUMMARY_CSV_HEADER

        sem = asyncio.Semaphore(concurrency)
        screenshot_service = get_screenshot_service()
        self._in_flight[job_id] = set()

        summary_path = output_dir / "summary.csv"
        already_done_ids = _read_done_entry_ids(summary_path)
        if not summary_path.exists():
            with summary_path.open("w", newline="", encoding="utf-8-sig") as f:
                csv.writer(f).writerow(header)
        if already_done_ids:
            logger.info(
                "job %s resuming — skipping %d entries already in summary.csv",
                job_id, len(already_done_ids),
            )

        summary_lock = asyncio.Lock()
        durations: list[float] = []
        durations_lock = asyncio.Lock()
        # summary.csv is written before the SQLite progress update, so it is
        # the durable source of truth after a crash or restart. The database
        # value can lag, and older releases could also over-count on resume.
        done = len(already_done_ids)
        failed = min(int(job.get("entries_failed") or 0), done)
        if (
            done != int(job.get("entries_done") or 0)
            or failed != int(job.get("entries_failed") or 0)
        ):
            self._store.update_progress(
                job_id, entries_done=done, entries_failed=failed,
            )
        failed_entries: list[dict] = []

        async def _process_one(idx: int, entry_raw: dict) -> None:
            nonlocal done, failed
            if self._store.is_cancel_requested(job_id):
                raise _Cancelled()
            if self._store.is_pause_requested(job_id):
                raise _Paused()

            entry_id_candidate = str(entry_raw.get("id") or "").strip()
            if entry_id_candidate and entry_id_candidate in already_done_ids:
                return

            entry_label = str(entry_raw.get("id") or entry_raw.get("url") or f"row_{idx}")
            try:
                if kind == "crawl":
                    entry = _resolve_crawl_entry(entry_raw, defaults)
                else:
                    entry = _resolve_entry(entry_raw, defaults, input_dir)
            except Exception as exc:
                err_msg = f"resolve failed: {type(exc).__name__}: {exc}"
                logger.warning("job[%s] entry %s: %s", job_id, entry_label, err_msg)
                fail_row = {c: "" for c in header}
                fail_row["entry_id"] = entry_label
                if "target_url" in fail_row:
                    fail_row["target_url"] = str(entry_raw.get("url") or "")
                if "status" in fail_row:
                    fail_row["status"] = "failed"
                if "applied" in fail_row:
                    fail_row["applied"] = False
                fail_row["error"] = err_msg
                async with summary_lock:
                    with summary_path.open("a", newline="", encoding="utf-8-sig") as f:
                        csv.writer(f).writerow([fail_row.get(c, "") for c in header])
                    failed_entries.append({"entry_id": entry_label, "error": err_msg})
                    done += 1
                    failed += 1
                    done_snapshot = done
                    failed_snapshot = failed
                    # Keep progress writes ordered with the CSV rows. When the
                    # write happened after releasing this lock, an older async
                    # task could overwrite a newer count.
                    self._store.update_progress(
                        job_id,
                        entries_done=done_snapshot,
                        entries_failed=failed_snapshot,
                        append_error=(entry_label, err_msg),
                    )
                return

            in_flight_set = self._in_flight.setdefault(job_id, set())
            async with sem:
                if self._store.is_cancel_requested(job_id):
                    raise _Cancelled()
                self._store.update_progress(job_id, current_entry=entry.id)
                t0 = time.time()
                in_flight_set.add(entry.id)
                try:
                    if kind == "crawl":
                        res = await process_crawl_entry(entry, output_dir, screenshot_service)
                        rows = res.rows
                        success = res.success
                        err = res.error
                    else:
                        bres: EntryResult = await process_entry(
                            entry, output_dir, screenshot_service,
                            timeout_s=entry_timeout_s,
                        )
                        rows = bres.technique_rows
                        success = bres.success
                        err = bres.error
                finally:
                    in_flight_set.discard(entry.id)
            dt = time.time() - t0
            async with durations_lock:
                durations.append(dt)
                avg = sum(durations) / len(durations)

            async with summary_lock:
                with summary_path.open("a", newline="", encoding="utf-8-sig") as f:
                    w = csv.writer(f)
                    for row in rows:
                        w.writerow([row.get(c, "") for c in header])
                if not success:
                    failed_entries.append({"entry_id": entry.id, "error": err})
                done += 1
                if not success:
                    failed += 1
                done_snapshot = done
                failed_snapshot = failed
                self._store.update_progress(
                    job_id,
                    entries_done=done_snapshot,
                    entries_failed=failed_snapshot,
                    avg_seconds_per_entry=avg,
                    append_error=(entry.id, err) if not success else None,
                )

        tasks = [
            asyncio.create_task(_process_one(i, e)) for i, e in enumerate(entries_raw)
        ]

        watcher_event = asyncio.Event()
        pause_signaled = {"value": False}
        async def _watcher() -> None:
            while not watcher_event.is_set():
                try:
                    if self._store.is_cancel_requested(job_id):
                        logger.info("job %s: cancel requested, aborting tasks", job_id)
                        for t in tasks:
                            if not t.done():
                                t.cancel()
                        return
                    if self._store.is_pause_requested(job_id):
                        logger.info("job %s: pause requested, aborting in-flight", job_id)
                        pause_signaled["value"] = True
                        for t in tasks:
                            if not t.done():
                                t.cancel()
                        return
                except Exception:
                    pass
                try:
                    await asyncio.wait_for(watcher_event.wait(), timeout=0.5)
                except asyncio.TimeoutError:
                    pass
        watcher = asyncio.create_task(_watcher(), name=f"job-watcher-{job_id[:8]}")

        try:
            for t in asyncio.as_completed(tasks):
                try:
                    await t
                except _Cancelled:
                    for other in tasks:
                        if not other.done():
                            other.cancel()
                    raise
                except _Paused:
                    for other in tasks:
                        if not other.done():
                            other.cancel()
                    raise
                except asyncio.CancelledError:
                    for other in tasks:
                        if not other.done():
                            other.cancel()
                    raise _Paused() if pause_signaled["value"] else _Cancelled()
                except Exception as exc:
                    logger.warning("entry task raised unexpectedly: %s", exc)
        except (_Cancelled, _Paused):
            for t in tasks:
                if not t.done():
                    t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise
        finally:
            watcher_event.set()
            if not watcher.done():
                watcher.cancel()
            try:
                await watcher
            except (asyncio.CancelledError, Exception):
                pass

        (output_dir / "summary.json").write_text(
            json.dumps({
                "job_id": job_id,
                "entries_total": len(entries_raw),
                "entries_succeeded": done - failed,
                "entries_failed": failed,
                "avg_seconds_per_entry": (sum(durations) / len(durations))
                                         if durations else None,
            }, indent=2),
            encoding="utf-8",
        )
        (output_dir / "failed.json").write_text(
            json.dumps(failed_entries, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        (output_dir / "manifest_echo.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        if not bool(defaults.get("html_only", False)):
            _write_urls_csv(output_dir, summary_path)

        self._in_flight.pop(job_id, None)
        await asyncio.to_thread(build_results_zip, job_id)
        self._store.mark_completed(job_id)


def _resolve_entry(raw: dict, defaults: dict, input_dir: Path) -> BulkEntry:
    """Merge defaults into a per-entry record. Supports two source modes:
    - ZIP mode: html paths are relative to input_dir (job's extracted upload).
    - CSV mode: defaults.legitimate_dir (absolute path) is the validation root;
                html_file may be either just a filename or already absolute.
    """
    eid = str(raw["id"])
    url = str(raw.get("url", defaults.get("url", "")))
    html_rel = raw.get("html_file") or defaults.get("html_file")
    if not html_rel:
        raise ValueError(f"entry {eid}: html_file missing")

    legit_root_str = defaults.get("legitimate_dir")
    legitimate_root: Path | None = None
    if legit_root_str:
        legitimate_root = Path(legit_root_str).resolve()
        validation_root = legitimate_root
    else:
        validation_root = input_dir.resolve()

    html_candidate = Path(html_rel)
    if html_candidate.is_absolute():
        html_path = html_candidate.resolve()
    else:
        html_path = (validation_root / html_candidate).resolve()
    if not str(html_path).startswith(str(validation_root)):
        raise ValueError(f"entry {eid}: html_file outside validation root")

    screenshot_path = None
    sshot_rel = raw.get("screenshot_file")
    if sshot_rel:
        sp_candidate = Path(sshot_rel)
        sp = sp_candidate.resolve() if sp_candidate.is_absolute() else (validation_root / sp_candidate).resolve()
        if str(sp).startswith(str(validation_root)):
            screenshot_path = sp

    technique_configs = raw.get("technique_configs", defaults.get("technique_configs"))
    category_filter = raw.get("category_filter", defaults.get("category_filter"))
    hybrid_mode = bool(raw.get("hybrid_mode", defaults.get("hybrid_mode", True)))
    include_report = bool(raw.get("include_report", defaults.get("include_report", True)))
    include_screenshots = bool(
        raw.get("include_screenshots", defaults.get("include_screenshots", True))
    )
    html_only = bool(raw.get("html_only", defaults.get("html_only", False)))
    output_layout = str(raw.get("output_layout", defaults.get("output_layout", "per_entry")))
    if output_layout not in ("per_entry", "per_kind"):
        output_layout = "per_entry"

    llm_creds = raw.get("llm_credentials", defaults.get("llm_credentials"))
    if llm_creds is not None and not isinstance(llm_creds, dict):
        llm_creds = None

    auto_url_pairing = bool(
        raw.get("auto_url_pairing", defaults.get("auto_url_pairing", False))
    )

    if technique_configs:
        category_filter = None

    return BulkEntry(
        id=eid, url=url, html_path=html_path, screenshot_path=screenshot_path,
        technique_configs=technique_configs, category_filter=category_filter,
        hybrid_mode=hybrid_mode, include_report=include_report,
        include_screenshots=include_screenshots, html_only=html_only,
        output_layout=output_layout, legitimate_root=legitimate_root,
        llm_credentials=llm_creds, auto_url_pairing=auto_url_pairing,
    )


def _resolve_crawl_entry(raw: dict, defaults: dict) -> CrawlEntry:
    """Build a CrawlEntry from a manifest row + defaults."""
    from app.core.crawl_engine import build_proxy_list
    eid = str(raw.get("id") or "").strip()
    url = str(raw.get("url") or "").strip()
    if not url:
        raise ValueError(f"entry {eid or '?'}: url is required for crawl jobs")
    if not eid:
        from app.core.crawl_engine import derive_id_from_url
        eid = derive_id_from_url(url)
    full_page = bool(raw.get("full_page", defaults.get("full_page", True)))
    wait_until = str(raw.get("wait_until", defaults.get("wait_until", "networkidle")))
    raw_proxies = raw.get("proxies", defaults.get("proxies"))
    proxies = build_proxy_list(raw_proxies)
    min_html_bytes = int(raw.get("min_html_bytes", defaults.get("min_html_bytes", 100)))
    s = get_settings()
    unreachable_s = float(raw.get(
        "unreachable_timeout_s",
        defaults.get("unreachable_timeout_s", s.crawl_unreachable_timeout_s),
    ))
    partial_s = float(raw.get(
        "partial_timeout_s",
        defaults.get("partial_timeout_s", s.crawl_partial_timeout_s),
    ))
    return CrawlEntry(
        id=eid, url=url,
        full_page=full_page, wait_until=wait_until,
        proxies=proxies, min_html_bytes=min_html_bytes,
        unreachable_timeout_s=unreachable_s,
        partial_timeout_s=partial_s,
    )


def build_results_zip(job_id: str) -> Path:
    """Build (or rebuild) results.zip from output/. Returns path."""
    jdir = job_dir(job_id)
    out_dir = jdir / "output"
    zip_path = jdir / "results.zip"
    if zip_path.exists():
        return zip_path
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for f in out_dir.rglob("*"):
            if f.is_file():
                zf.write(f, arcname=str(f.relative_to(out_dir)))
    return zip_path


_runner: JobRunner | None = None


def get_job_runner() -> JobRunner:
    global _runner
    if _runner is None:
        _runner = JobRunner()
    return _runner
