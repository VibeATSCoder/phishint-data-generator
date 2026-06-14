"""Batch evaluation runner.

Reads a completed job's summary.csv, runs evaluate() on each generated
artifact, and writes evaluation_results.csv + evaluation_summary.json
into the job's output directory.

Usage
-----
# Python API
from app.core.evaluator import evaluate_job
report = evaluate_job("c84abf8a-e743-44fe-9792-1fc42eb30e28")

# CLI  (runs inside the container)
python -m app.core.evaluator <job_id>
"""
from __future__ import annotations

import csv
import json
import sys
import time
from pathlib import Path
from typing import Any


def evaluate_job(job_id: str, *, data_dir: str | None = None) -> dict:
    """Run evaluate() on every artifact in a completed job.

    Returns a summary dict:
    {
        "job_id": ...,
        "total": N,
        "passed": N,
        "failed": N,
        "skipped": N,          # technique had no evaluate() output or was not applied
        "avg_score": float,
        "by_technique": { "T01": {"passed":N,"failed":N,"avg_score":f}, ... },
        "entries": [ { entry_id, tid, passed, score, signals, issues, details }, ... ],
    }
    """
    from app.config import get_settings_sync
    from app.core.registry import TechniqueRegistry
    import app.techniques  # noqa: F401

    base = Path(data_dir or get_settings_sync().data_dir)
    job_out = base / "jobs" / job_id / "output"
    if not job_out.exists():
        raise FileNotFoundError(f"Job output directory not found: {job_out}")

    summary_csv = job_out / "summary.csv"
    if not summary_csv.exists():
        raise FileNotFoundError(f"summary.csv not found: {summary_csv}")

    html_dir = job_out / "phishing_html_archive"
    url_dir = job_out / "phishing_url_archive"
    extras_dir = job_out / "extras"

    tech_by_id: dict[int, Any] = {
        cls.TECHNIQUE_ID: cls() for cls in TechniqueRegistry.all()
    }

    rows = _read_csv(summary_csv)
    results: list[dict] = []
    by_tech: dict[str, dict] = {}

    for row in rows:
        entry_id = row.get("entry_id", "")
        tid_str = row.get("technique_id", "")
        applied = row.get("applied", "").lower() == "true"

        if not applied or not tid_str:
            continue

        try:
            tid = int(tid_str)
        except (ValueError, TypeError):
            continue

        tech = tech_by_id.get(tid)
        if tech is None:
            continue

        html = ""
        html_path = row.get("html_path", "")
        if html_path:
            full_html = job_out / html_path
            if full_html.exists():
                try:
                    html = full_html.read_text("utf-8", errors="replace")
                except Exception:
                    pass

        url = row.get("modified_url", "") or row.get("target_url", "")
        url_path = row.get("url_path", "")
        if not url and url_path:
            full_url = job_out / url_path
            if full_url.exists():
                try:
                    url = full_url.read_text("utf-8", errors="replace").strip()
                except Exception:
                    pass

        extra_files: dict[str, bytes] = {}
        entry_extras = extras_dir / entry_id
        if entry_extras.exists():
            for ef in entry_extras.rglob("*"):
                if ef.is_file():
                    rel = str(ef.relative_to(entry_extras))
                    try:
                        extra_files[rel] = ef.read_bytes()
                    except Exception:
                        pass

        target_url = row.get("target_url", "")
        if target_url:
            extra_files["__target_url__"] = target_url.encode()

        try:
            ev = tech.evaluate(html, url or "", [], extra_files)
        except Exception as exc:
            ev_dict = {
                "passed": False, "score": 0.0,
                "signals": [], "issues": [f"evaluate() raised {type(exc).__name__}: {exc}"],
                "details": {},
            }
        else:
            ev_dict = ev.to_dict()

        tid_key = f"T{tid:02d}"
        stat = by_tech.setdefault(tid_key, {"passed": 0, "failed": 0, "scores": []})
        if ev_dict["passed"]:
            stat["passed"] += 1
        else:
            stat["failed"] += 1
        stat["scores"].append(ev_dict["score"])

        results.append({
            "entry_id": entry_id,
            "tid": tid_key,
            "technique_name": row.get("technique_name", ""),
            **ev_dict,
        })

    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    failed = total - passed
    all_scores = [r["score"] for r in results]
    avg_score = round(sum(all_scores) / len(all_scores), 3) if all_scores else 0.0

    by_tech_summary = {}
    for tid_key, stat in sorted(by_tech.items()):
        scores = stat.pop("scores", [])
        stat["avg_score"] = round(sum(scores) / len(scores), 3) if scores else 0.0
        by_tech_summary[tid_key] = stat

    summary = {
        "job_id": job_id,
        "evaluated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": round(passed / total, 3) if total else 0.0,
        "avg_score": avg_score,
        "by_technique": by_tech_summary,
        "entries": results,
    }

    _write_results_csv(job_out / "evaluation_results.csv", results)
    summary_for_file = {k: v for k, v in summary.items() if k != "entries"}
    (job_out / "evaluation_summary.json").write_text(
        json.dumps(summary_for_file, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (job_out / "evaluation_full.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return summary


def _read_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _write_results_csv(path: Path, results: list[dict]) -> None:
    if not results:
        return
    fieldnames = [
        "entry_id", "tid", "technique_name",
        "passed", "score",
        "signals_count", "issues_count",
        "signals", "issues",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in results:
            w.writerow({
                "entry_id": r["entry_id"],
                "tid": r["tid"],
                "technique_name": r.get("technique_name", ""),
                "passed": r["passed"],
                "score": r["score"],
                "signals_count": len(r.get("signals", [])),
                "issues_count": len(r.get("issues", [])),
                "signals": " | ".join(r.get("signals", [])),
                "issues": " | ".join(r.get("issues", [])),
            })


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m app.core.evaluator <job_id>", file=sys.stderr)
        sys.exit(1)
    job_id = sys.argv[1]
    print(f"Evaluating job {job_id} ...")
    report = evaluate_job(job_id)
    print(f"Done. {report['total']} artifacts evaluated.")
    print(f"  Passed  : {report['passed']} ({report['pass_rate']*100:.1f}%)")
    print(f"  Failed  : {report['failed']}")
    print(f"  Avg score: {report['avg_score']:.3f}")
    print()
    print("By technique:")
    for tid, stat in sorted(report["by_technique"].items()):
        print(f"  {tid}: passed={stat['passed']} failed={stat['failed']} avg_score={stat['avg_score']:.3f}")
    print()
    print("Output files written to job output directory.")
