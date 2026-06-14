from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from app.config import get_settings_sync


JOB_STATUSES = ("pending", "running", "paused", "completed", "failed", "cancelled")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id              TEXT PRIMARY KEY,
    status          TEXT NOT NULL,
    manifest_json   TEXT NOT NULL,
    options_json    TEXT NOT NULL,
    entries_total   INTEGER NOT NULL DEFAULT 0,
    entries_done    INTEGER NOT NULL DEFAULT 0,
    entries_failed  INTEGER NOT NULL DEFAULT 0,
    current_entry   TEXT,
    error           TEXT,
    cancel_requested INTEGER NOT NULL DEFAULT 0,
    pause_requested  INTEGER NOT NULL DEFAULT 0,
    avg_seconds_per_entry REAL,
    recent_errors_json TEXT NOT NULL DEFAULT '[]',
    created_at      REAL NOT NULL,
    started_at      REAL,
    completed_at    REAL
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at DESC);
-- Additive migration for installs that pre-date the pause flag. Sqlite
-- refuses ALTER TABLE on a column it already has, so we ignore that.
"""

_MIGRATIONS = [
    "ALTER TABLE jobs ADD COLUMN pause_requested INTEGER NOT NULL DEFAULT 0",
]


def _data_dir() -> Path:
    p = Path(get_settings_sync().data_dir)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _db_path() -> Path:
    return _data_dir() / "jobs.db"


def job_dir(job_id: str) -> Path:
    p = _data_dir() / "jobs" / job_id
    p.mkdir(parents=True, exist_ok=True)
    return p


class JobStore:
    """Thin synchronous SQLite wrapper. Use from a single asyncio loop;
    each method opens its own short-lived connection (sqlite3 connections
    are not thread-safe). All writes are wrapped in a transaction."""

    def __init__(self) -> None:
        self._path = str(_db_path())
        self._init_schema()

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self._path, isolation_level=None, timeout=10)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=NORMAL")
        return c

    def _init_schema(self) -> None:
        with self._conn() as c:
            c.executescript(_SCHEMA)
            for stmt in _MIGRATIONS:
                try:
                    c.execute(stmt)
                except sqlite3.OperationalError:
                    pass

    def create(
        self,
        job_id: str,
        manifest: dict,
        options: dict,
        entries_total: int,
    ) -> None:
        now = time.time()
        with self._conn() as c:
            c.execute(
                """INSERT INTO jobs
                (id, status, manifest_json, options_json, entries_total,
                 entries_done, entries_failed, cancel_requested,
                 recent_errors_json, created_at)
                VALUES (?, 'pending', ?, ?, ?, 0, 0, 0, '[]', ?)""",
                (job_id, json.dumps(manifest), json.dumps(options),
                 entries_total, now),
            )

    def get(self, job_id: str) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return _row_to_dict(row) if row else None

    def list(self, limit: int = 100) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def next_pending(self) -> dict | None:
        with self._conn() as c:
            row = c.execute(
                "SELECT * FROM jobs WHERE status='pending' "
                "ORDER BY created_at ASC LIMIT 1"
            ).fetchone()
        return _row_to_dict(row) if row else None

    def mark_running(self, job_id: str) -> None:
        with self._conn() as c:
            c.execute(
                "UPDATE jobs SET status='running', started_at=? WHERE id=?",
                (time.time(), job_id),
            )

    def mark_completed(self, job_id: str) -> None:
        with self._conn() as c:
            c.execute(
                "UPDATE jobs SET status='completed', completed_at=?, current_entry=NULL "
                "WHERE id=?",
                (time.time(), job_id),
            )

    def mark_failed(self, job_id: str, error: str) -> None:
        with self._conn() as c:
            c.execute(
                "UPDATE jobs SET status='failed', completed_at=?, error=? WHERE id=?",
                (time.time(), error, job_id),
            )

    def mark_cancelled(self, job_id: str) -> None:
        with self._conn() as c:
            c.execute(
                "UPDATE jobs SET status='cancelled', completed_at=? WHERE id=?",
                (time.time(), job_id),
            )

    def request_cancel(self, job_id: str) -> bool:
        """Returns True if job was running/pending and cancel was set."""
        with self._conn() as c:
            cur = c.execute(
                "UPDATE jobs SET cancel_requested=1 "
                "WHERE id=? AND status IN ('pending','running','paused')",
                (job_id,),
            )
            return cur.rowcount > 0

    def is_cancel_requested(self, job_id: str) -> bool:
        with self._conn() as c:
            row = c.execute(
                "SELECT cancel_requested FROM jobs WHERE id=?", (job_id,)
            ).fetchone()
        return bool(row and row["cancel_requested"])

    def request_pause(self, job_id: str) -> bool:
        """Set the pause flag on a running/pending job. Returns True if the
        flag was actually set (state was eligible)."""
        with self._conn() as c:
            cur = c.execute(
                "UPDATE jobs SET pause_requested=1 "
                "WHERE id=? AND status IN ('pending','running')",
                (job_id,),
            )
            return cur.rowcount > 0

    def is_pause_requested(self, job_id: str) -> bool:
        with self._conn() as c:
            row = c.execute(
                "SELECT pause_requested FROM jobs WHERE id=?", (job_id,)
            ).fetchone()
        return bool(row and row["pause_requested"])

    def mark_paused(self, job_id: str) -> None:
        """Move a job to the paused state. Resets the pause flag so the next
        resume → run cycle starts clean."""
        with self._conn() as c:
            c.execute(
                "UPDATE jobs SET status='paused', pause_requested=0, "
                "current_entry=NULL WHERE id=?",
                (job_id,),
            )

    def resume_paused(self, job_id: str) -> bool:
        """Move a paused job back to pending so the runner picks it up.
        Returns True if state was eligible. Clears both flags."""
        with self._conn() as c:
            cur = c.execute(
                "UPDATE jobs SET status='pending', pause_requested=0, "
                "cancel_requested=0, completed_at=NULL, error=NULL "
                "WHERE id=? AND status='paused'",
                (job_id,),
            )
            return cur.rowcount > 0

    def update_progress(
        self,
        job_id: str,
        *,
        entries_done: int | None = None,
        entries_failed: int | None = None,
        current_entry: str | None = None,
        avg_seconds_per_entry: float | None = None,
        append_error: tuple[str, str] | None = None,
    ) -> None:
        """All field updates run atomically in a single transaction. When
        `append_error` is set, the recent_errors_json read-modify-write happens
        inside the same `BEGIN IMMEDIATE` so concurrent appenders cannot lose
        each other's entries.
        """
        sets: list[str] = []
        args: list[Any] = []
        if entries_done is not None:
            sets.append("entries_done=?"); args.append(entries_done)
        if entries_failed is not None:
            sets.append("entries_failed=?"); args.append(entries_failed)
        if current_entry is not None:
            sets.append("current_entry=?"); args.append(current_entry)
        if avg_seconds_per_entry is not None:
            sets.append("avg_seconds_per_entry=?"); args.append(avg_seconds_per_entry)

        if append_error is None and not sets:
            return

        with self._conn() as c:
            try:
                c.execute("BEGIN IMMEDIATE")
                if append_error is not None:
                    row = c.execute(
                        "SELECT recent_errors_json FROM jobs WHERE id=?", (job_id,)
                    ).fetchone()
                    arr = json.loads(row["recent_errors_json"]) if row else []
                    arr.append({"entry_id": append_error[0], "error": append_error[1]})
                    arr = arr[-20:]
                    sets.append("recent_errors_json=?")
                    args.append(json.dumps(arr))
                if sets:
                    sql_args = args + [job_id]
                    c.execute(
                        f"UPDATE jobs SET {', '.join(sets)} WHERE id=?", sql_args,
                    )
                c.execute("COMMIT")
            except Exception:
                try:
                    c.execute("ROLLBACK")
                except Exception:
                    pass
                raise

    def reset_running_to_paused(self, reason: str) -> int:
        """Called on startup: any 'running' job was interrupted by a restart.
        We move it to `paused` (not `failed`) so the operator can resume it
        with one click; summary.csv is intact and resume skips already-done
        entries. `reason` is stamped into `error` for visibility but the
        status is `paused`, not `failed`."""
        with self._conn() as c:
            cur = c.execute(
                "UPDATE jobs SET status='paused', current_entry=NULL, error=? "
                "WHERE status='running'",
                (reason,),
            )
            return cur.rowcount

    def delete(self, job_id: str) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM jobs WHERE id=?", (job_id,))


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["manifest"] = json.loads(d.pop("manifest_json"))
    d["options"] = json.loads(d.pop("options_json"))
    d["recent_errors"] = json.loads(d.pop("recent_errors_json"))
    return d


_store: JobStore | None = None


def get_job_store() -> JobStore:
    global _store
    if _store is None:
        _store = JobStore()
    return _store
