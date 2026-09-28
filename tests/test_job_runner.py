from __future__ import annotations

import csv

from app.core.job_runner import _read_done_entry_ids


def test_read_done_entry_ids_accepts_utf8_bom(tmp_path):
    summary = tmp_path / "summary.csv"
    with summary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["entry_id", "applied", "error"])
        writer.writerow(["site-a", True, ""])
        writer.writerow(["site-b", True, ""])
        writer.writerow(["site-a", True, ""])

    assert _read_done_entry_ids(summary) == {"site-a", "site-b"}


def test_read_done_entry_ids_accepts_plain_utf8(tmp_path):
    summary = tmp_path / "summary.csv"
    summary.write_text("entry_id,applied,error\nsite-a,True,\n", encoding="utf-8")

    assert _read_done_entry_ids(summary) == {"site-a"}
