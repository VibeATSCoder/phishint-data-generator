from __future__ import annotations

import asyncio
import csv as csvlib
import io
import json
import random
import shutil
import time
import uuid
import zipfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.api.schemas.jobs import (
    JobCreateResponse, JobErrorEntry, JobStatusResponse, JobsListResponse,
)
from app.config import get_settings
from app.core.job_runner import build_results_zip, get_job_runner
from app.core.job_store import get_job_store, job_dir
from app.core.registry import TechniqueRegistry
from app.techniques.base import Requirement
from app.utils.upload_utils import read_with_cap

router = APIRouter()


def _to_status_response(job: dict) -> JobStatusResponse:
    avg = job.get("avg_seconds_per_entry")
    remaining = max(0, job["entries_total"] - job["entries_done"])
    eta = (avg * remaining) if (avg and avg > 0 and job["status"] == "running") else None
    recent = [JobErrorEntry(**e) for e in job.get("recent_errors", [])]
    manifest = job.get("manifest") or {}
    kind = (manifest.get("kind") or "generate").lower()
    in_flight = get_job_runner().get_in_flight(job["id"])
    return JobStatusResponse(
        id=job["id"], status=job["status"], kind=kind,
        entries_total=job["entries_total"], entries_done=job["entries_done"],
        entries_failed=job["entries_failed"],
        current_entry=job.get("current_entry"),
        in_flight=in_flight,
        error=job.get("error"),
        avg_seconds_per_entry=avg, eta_seconds=eta,
        recent_errors=recent, created_at=job["created_at"],
        started_at=job.get("started_at"), completed_at=job.get("completed_at"),
    )


def _validate_manifest(manifest: dict) -> tuple[list[dict], dict]:
    """Returns (entries, defaults). Raises HTTPException on validation errors."""
    if not isinstance(manifest, dict):
        raise HTTPException(422, "manifest.json must be an object")
    defaults = manifest.get("defaults") or {}
    if not isinstance(defaults, dict):
        raise HTTPException(422, "manifest.defaults must be an object")
    entries = manifest.get("entries")
    if not isinstance(entries, list) or not entries:
        raise HTTPException(422, "manifest.entries must be a non-empty array")

    settings = get_settings()
    if len(entries) > settings.bulk_max_entries:
        raise HTTPException(
            413,
            f"too many entries ({len(entries)} > limit {settings.bulk_max_entries})",
        )

    seen_ids = set()
    for i, e in enumerate(entries):
        if not isinstance(e, dict):
            raise HTTPException(422, f"entries[{i}] must be an object")
        eid = e.get("id")
        if not eid or not isinstance(eid, str):
            raise HTTPException(422, f"entries[{i}].id missing or not a string")
        if eid in seen_ids:
            raise HTTPException(422, f"duplicate entry id: {eid}")
        seen_ids.add(eid)
        if not e.get("html_file") and not defaults.get("html_file"):
            raise HTTPException(422, f"entries[{i}].html_file missing (no default)")

    def_configs = defaults.get("technique_configs") or []
    for c in def_configs:
        if isinstance(c, dict) and TechniqueRegistry.get(int(c.get("technique_id", -1))) is None:
            raise HTTPException(422, f"unknown technique_id in defaults: {c}")

    return entries, defaults


def _resolve_legitimate_dir(rel_or_abs: str) -> Path:
    """Resolve `legitimate_dir` to an absolute path inside settings.data_dir.
    Raises HTTPException(422) on path-traversal or missing dir.
    """
    data_root = Path(get_settings().data_dir).resolve()
    candidate = Path(rel_or_abs)
    target = candidate.resolve() if candidate.is_absolute() else (data_root / candidate).resolve()
    if not str(target).startswith(str(data_root)):
        raise HTTPException(422, f"legitimate_dir must resolve inside {data_root}")
    if not target.exists() or not target.is_dir():
        raise HTTPException(422, f"legitimate_dir does not exist: {rel_or_abs}")
    return target


def _csv_to_manifest(
    csv_bytes: bytes,
    legitimate_dir: Path,
    defaults: dict,
) -> dict:
    """Parse a CSV with `id,html_filename` columns into a manifest dict.
    URL is derived from the filename pattern `YYYYMMDD__domain__hash.html`.
    Optional columns (`url`, `technique_configs`, `category_filter`) are honored
    as per-entry overrides if present.
    """
    text = csv_bytes.decode("utf-8-sig", errors="replace")
    reader = csvlib.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(422, "csv_file is empty or missing a header row")

    fields = {f.strip().lower(): f for f in reader.fieldnames if f}
    if "html_filename" not in fields:
        raise HTTPException(422, "csv_file must have an 'html_filename' column")

    settings = get_settings()
    entries: list[dict] = []
    seen_ids: set[str] = set()

    for i, row in enumerate(reader, start=2):
        if not row:
            continue
        fname = (row.get(fields["html_filename"]) or "").strip()
        if not fname:
            continue

        eid_raw = (row.get(fields["id"]) or "").strip() if "id" in fields else ""
        if not eid_raw:
            eid_raw = fname[:-5] if fname.lower().endswith(".html") else fname
        from app.core.crawl_engine import sanitize_entry_id
        eid = sanitize_entry_id(eid_raw)
        if not eid:
            raise HTTPException(
                422, f"csv row {i}: id '{eid_raw}' has no usable characters",
            )
        base = eid; n = 2
        while eid in seen_ids:
            eid = f"{base}_{n}"; n += 1
        seen_ids.add(eid)

        url = (row.get(fields["url"]) or "").strip() if "url" in fields else ""
        if not url:
            parts = fname.split("__")
            if len(parts) >= 3 and parts[1].strip():
                url = "https://" + parts[1].strip()
            else:
                url = ""

        entry: dict = {
            "id": eid,
            "url": url,
            "html_file": fname,
        }
        if "technique_configs" in fields:
            v = (row.get(fields["technique_configs"]) or "").strip()
            if v:
                try:
                    entry["technique_configs"] = json.loads(v)
                except Exception:
                    raise HTTPException(
                        422, f"csv row {i}: technique_configs is not valid JSON",
                    )
        if "category_filter" in fields:
            v = (row.get(fields["category_filter"]) or "").strip()
            if v:
                entry["category_filter"] = [s.strip() for s in v.split("|") if s.strip()]
        entries.append(entry)

        if len(entries) > settings.bulk_max_entries:
            raise HTTPException(
                413,
                f"too many entries ({len(entries)} > limit {settings.bulk_max_entries})",
            )

    if not entries:
        raise HTTPException(422, "csv_file produced no entries")

    defaults_out = dict(defaults)
    defaults_out["legitimate_dir"] = str(legitimate_dir)
    defaults_out.setdefault("output_layout", "per_kind")

    return {"defaults": defaults_out, "entries": entries}


def _zip_to_manifest(
    zip_bytes: bytes,
    legitimate_dir: Path,
    defaults: dict,
) -> dict:
    """Auto-generate a manifest by scanning .html files in a dataset ZIP.
    Applies the same YYYYMMDD__domain__hash.html → URL derivation as _csv_to_manifest.
    """
    from app.core.crawl_engine import sanitize_entry_id

    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            html_names = sorted({
                Path(info.filename).name
                for info in zf.infolist()
                if not info.is_dir() and info.filename.lower().endswith(".html")
            })
    except zipfile.BadZipFile:
        raise HTTPException(400, "dataset_zip is not a valid ZIP file")

    if not html_names:
        raise HTTPException(422, "dataset_zip contains no .html files")

    settings = get_settings()
    entries: list[dict] = []
    seen_ids: set[str] = set()

    for fname in html_names:
        eid_raw = fname[:-5] if fname.lower().endswith(".html") else fname
        eid = sanitize_entry_id(eid_raw)
        if not eid:
            continue
        base = eid
        n = 2
        while eid in seen_ids:
            eid = f"{base}_{n}"
            n += 1
        seen_ids.add(eid)

        parts = fname.split("__")
        url = ("https://" + parts[1].strip()) if len(parts) >= 3 and parts[1].strip() else ""

        entries.append({"id": eid, "url": url, "html_file": fname})

        if len(entries) > settings.bulk_max_entries:
            raise HTTPException(
                413,
                f"too many entries ({len(entries)} > limit {settings.bulk_max_entries})",
            )

    if not entries:
        raise HTTPException(422, "dataset_zip produced no usable HTML entries")

    defaults_out = dict(defaults)
    defaults_out["legitimate_dir"] = str(legitimate_dir)
    defaults_out.setdefault("output_layout", "per_kind")
    return {"defaults": defaults_out, "entries": entries}


def _extract_dataset_zip(raw: bytes, dest: Path) -> Path:
    """Extract a dataset ZIP into `dest`. Auto-detect single-subfolder case
    (a ZIP wrapping `legitimate_html_archive/` will resolve to that subfolder).
    Refuses to extract decompression bombs (declared uncompressed total above
    `settings.bulk_max_zip_uncompressed_bytes`).
    Returns the directory that should be used as `legitimate_dir`."""
    dest.mkdir(parents=True, exist_ok=True)
    bio = io.BytesIO(raw)
    cap = get_settings().bulk_max_zip_uncompressed_bytes
    try:
        with zipfile.ZipFile(bio) as zf:
            total_uncompressed = 0
            for info in zf.infolist():
                name = info.filename
                if name.startswith("/") or ".." in Path(name).parts:
                    raise HTTPException(422, f"unsafe path in dataset_zip: {name}")
                total_uncompressed += int(info.file_size or 0)
                if total_uncompressed > cap:
                    raise HTTPException(
                        413,
                        f"dataset_zip uncompressed size exceeds cap "
                        f"({total_uncompressed} > {cap} bytes); raise "
                        "bulk_max_zip_uncompressed_bytes if intentional",
                    )
            zf.extractall(dest)
    except zipfile.BadZipFile:
        raise HTTPException(400, "dataset_zip is not a valid ZIP file")

    children = [c for c in dest.iterdir() if not c.name.startswith(".")]
    if len(children) == 1 and children[0].is_dir():
        return children[0].resolve()
    return dest.resolve()


def _bake_distribution(
    entries: list[dict],
    distribution: dict,
    seed: int = 42,
) -> dict[int, int]:
    """Stamp `entries[i].technique_configs` with exactly one technique per entry,
    distributed to match the percentages. Mutates `entries` in place.
    Returns the assigned-count map {technique_id: count}.

    `distribution` keys may be ints, str ints, or "T01"-style. Values are
    fractions 0..1 OR percentages 0..100; both are normalized.
    """
    if not isinstance(distribution, dict) or not distribution:
        raise HTTPException(422, "distribution must be a non-empty object")

    parsed: dict[int, float] = {}
    for k, v in distribution.items():
        try:
            ks = str(k).strip().upper().lstrip("T")
            tid = int(ks)
        except Exception:
            raise HTTPException(422, f"distribution key '{k}' is not a technique id")
        if TechniqueRegistry.get(tid) is None:
            raise HTTPException(422, f"distribution: unknown technique id {tid}")
        try:
            f = float(v)
        except Exception:
            raise HTTPException(422, f"distribution[{k}] is not numeric")
        if f < 0:
            raise HTTPException(422, f"distribution[{k}] must be >= 0")
        if f == 0:
            continue
        parsed[tid] = parsed.get(tid, 0.0) + f

    if not parsed:
        raise HTTPException(422, "distribution sums to zero")

    total = sum(parsed.values())
    if abs(total - 100.0) <= 0.5:
        scale = 1.0 / 100.0
    elif abs(total - 1.0) <= 0.005:
        scale = 1.0
    else:
        raise HTTPException(
            422,
            f"distribution must sum to 100 (percent) or 1.0 (fraction); got {total}",
        )
    fractions = {tid: f * scale for tid, f in parsed.items()}

    n = len(entries)
    floats = {tid: fractions[tid] * n for tid in fractions}
    counts = {tid: int(v) for tid, v in floats.items()}
    remainders = sorted(
        ((floats[tid] - counts[tid], tid) for tid in floats),
        key=lambda x: (-x[0], x[1]),
    )
    deficit = n - sum(counts.values())
    for _, tid in remainders[:max(0, deficit)]:
        counts[tid] += 1

    labels: list[int] = []
    for tid, c in counts.items():
        labels.extend([tid] * c)
    random.Random(seed).shuffle(labels)
    if len(labels) != n:
        raise HTTPException(500, "distribution baking produced wrong length")

    for entry, tid in zip(entries, labels):
        entry["technique_configs"] = [{"technique_id": tid}]
        entry["hybrid_mode"] = False
        entry.pop("category_filter", None)

    return counts


def _tech_requires_ai(tid: int) -> bool:
    cls = TechniqueRegistry.get(tid)
    return cls is not None and Requirement.REQUIRES_AI in cls.REQUIREMENTS


def _estimate_tokens(
    chars: int,
    *,
    chars_per_token: float = 4.0,
    system_prompt_tokens: int = 320,
    max_html_chars: int = 40000,
    max_output_tokens: int = 8192,
) -> tuple[int, int]:
    """Returns (input_tokens, output_tokens) for one T23 call given the
    source HTML size in characters. Refined HTML is roughly the same size
    as the (capped) input, bounded by max_output_tokens."""
    capped = min(chars, max_html_chars)
    inp = system_prompt_tokens + int(round(capped / max(0.5, chars_per_token)))
    out = min(max_output_tokens, int(round(capped / max(0.5, chars_per_token))))
    return inp, max(64, out)


def _sample_html_sizes_from_dir(
    legitimate_dir: Path, filenames: list[str], n: int = 50,
) -> list[int]:
    """Return file sizes (bytes) for up to n sampled filenames."""
    if not filenames:
        return []
    rng = random.Random(1234)
    sample = rng.sample(filenames, min(n, len(filenames)))
    sizes: list[int] = []
    for fname in sample:
        try:
            p = (legitimate_dir / fname).resolve()
            if str(p).startswith(str(legitimate_dir.resolve())) and p.is_file():
                sizes.append(p.stat().st_size)
        except Exception:
            continue
    return sizes


def _sample_html_sizes_from_zip(
    zip_bytes: bytes, filenames: list[str], n: int = 50,
) -> list[int]:
    """Read uncompressed sizes from the ZIP central directory (no extraction)."""
    if not filenames:
        return []
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            info_by_name: dict[str, zipfile.ZipInfo] = {}
            for info in zf.infolist():
                if info.is_dir():
                    continue
                info_by_name[Path(info.filename).name] = info
            rng = random.Random(1234)
            sample = rng.sample(filenames, min(n, len(filenames)))
            sizes = [info_by_name[f].file_size for f in sample if f in info_by_name]
            return sizes
    except Exception:
        return []


@router.post("/estimate-bulk")
async def estimate_bulk(
    csv_file: UploadFile | None = File(None, description="CSV with id,html_filename — optional when dataset_zip is provided (entries auto-detected from HTML filenames)."),
    dataset_zip: UploadFile | None = File(None, description="Optional dataset ZIP — sizes read from central dir, not extracted. Required when csv_file is omitted."),
    legitimate_dir: str = Form("legitimate_html_archive"),
    defaults_json: str = Form(""),
    distribution_json: str = Form(""),
    input_price_per_million: float = Form(0.0, description="Input token price ($ per 1M tokens) for the AI provider."),
    output_price_per_million: float = Form(0.0, description="Output token price ($ per 1M tokens)."),
    chars_per_token: float = Form(4.0, description="Heuristic: characters per token for token counts. 4 ≈ English text."),
    sample_size: int = Form(50, description="How many entries to sample for HTML size measurement."),
    assumed_avg_html_bytes: int = Form(50000, description="Used when source files are not accessible (no dir + no zip)."),
) -> dict:
    """Estimate token usage and LLM cost for a bulk run **without** starting a job.

    Reuses the same CSV + distribution + dataset_zip flow as /generate-bulk,
    but reads HTML sizes via central-directory sampling (zip) or stat (dir),
    then projects tokens/cost based on T23's (max_html_chars / max_output_tokens)
    options merged from defaults_json.
    """
    settings = get_settings()
    if csv_file is None and dataset_zip is None:
        raise HTTPException(400, "provide csv_file or dataset_zip (for auto-detection from HTML filenames)")

    raw_csv: bytes | None = None
    if csv_file is not None:
        raw_csv = await read_with_cap(
            csv_file, settings.max_csv_size_bytes, field_name="csv_file",
        )
        if not raw_csv:
            raise HTTPException(400, "csv_file is empty")

    defaults: dict = {}
    if defaults_json.strip():
        try:
            defaults = json.loads(defaults_json)
            if not isinstance(defaults, dict):
                raise ValueError("defaults_json must decode to a JSON object")
        except Exception as exc:
            raise HTTPException(422, f"invalid defaults_json: {exc}")

    raw_zip: bytes | None = None
    legit_root: Path | None = None
    if dataset_zip is not None:
        raw_zip = await read_with_cap(
            dataset_zip, settings.max_input_zip_size_bytes, field_name="dataset_zip",
        )
        if not raw_zip:
            raise HTTPException(400, "dataset_zip is empty")
    else:
        try:
            legit_root = _resolve_legitimate_dir(legitimate_dir)
        except HTTPException:
            legit_root = None

    if raw_csv is not None:
        manifest = _csv_to_manifest(raw_csv, legit_root or Path("/data"), defaults)
    else:
        assert raw_zip is not None
        manifest = _zip_to_manifest(raw_zip, legit_root or Path("/data"), defaults)
    entries = manifest["entries"]

    distribution = None
    if distribution_json.strip():
        try:
            distribution = json.loads(distribution_json)
        except Exception as exc:
            raise HTTPException(422, f"invalid distribution_json: {exc}")
        _bake_distribution(entries, distribution)

    tech_ids: list[int] = []
    if distribution is not None:
        for e in entries:
            cfgs = e.get("technique_configs") or []
            if cfgs:
                tech_ids.append(int(cfgs[0]["technique_id"]))
    else:
        def_cfgs = defaults.get("technique_configs") or []
        cfg_ids = [int(c["technique_id"]) for c in def_cfgs if "technique_id" in c]
        for _ in entries:
            tech_ids.extend(cfg_ids)

    ai_count = sum(1 for tid in tech_ids if _tech_requires_ai(tid))
    non_ai_count = len(tech_ids) - ai_count

    filenames = [e.get("html_file", "") for e in entries if e.get("html_file")]
    if raw_zip is not None:
        sizes = _sample_html_sizes_from_zip(raw_zip, filenames, n=sample_size)
        size_source = "dataset_zip (uncompressed_size from central directory)"
    elif legit_root is not None:
        sizes = _sample_html_sizes_from_dir(legit_root, filenames, n=sample_size)
        size_source = f"directory ({legit_root})"
    else:
        sizes = []
        size_source = "no source — using assumed_avg_html_bytes"

    if sizes:
        sample_avg_bytes = sum(sizes) // len(sizes)
        sample_max_bytes = max(sizes)
        sample_min_bytes = min(sizes)
    else:
        sample_avg_bytes = int(assumed_avg_html_bytes)
        sample_max_bytes = sample_avg_bytes
        sample_min_bytes = sample_avg_bytes

    tech_opts: dict = {}
    for cfg in (defaults.get("technique_configs") or []):
        if int(cfg.get("technique_id", -1)) == 23:
            tech_opts = cfg.get("options", {}) or {}
            break
    max_html_chars = int(tech_opts.get("max_html_chars", 40000))
    max_output_tokens = int(tech_opts.get("max_output_tokens", 8192))

    inp_per, out_per = _estimate_tokens(
        sample_avg_bytes,
        chars_per_token=chars_per_token,
        max_html_chars=max_html_chars,
        max_output_tokens=max_output_tokens,
    )
    total_inp = inp_per * ai_count
    total_out = out_per * ai_count
    inp_cost = total_inp / 1_000_000.0 * input_price_per_million
    out_cost = total_out / 1_000_000.0 * output_price_per_million
    total_cost = inp_cost + out_cost

    return {
        "entries_total": len(entries),
        "ai_calls_total": ai_count,
        "non_ai_runs": non_ai_count,
        "sample": {
            "size": len(sizes),
            "source": size_source,
            "avg_html_bytes": sample_avg_bytes,
            "min_html_bytes": sample_min_bytes,
            "max_html_bytes": sample_max_bytes,
        },
        "tokens": {
            "input_per_call": inp_per,
            "output_per_call": out_per,
            "input_total": total_inp,
            "output_total": total_out,
        },
        "cost_usd": {
            "input": round(inp_cost, 4),
            "output": round(out_cost, 4),
            "total": round(total_cost, 4),
        },
        "assumptions": {
            "chars_per_token": chars_per_token,
            "system_prompt_tokens": 320,
            "max_html_chars": max_html_chars,
            "max_output_tokens": max_output_tokens,
            "input_price_per_million_tokens": input_price_per_million,
            "output_price_per_million_tokens": output_price_per_million,
        },
    }


@router.post("/generate-bulk", response_model=JobCreateResponse)
async def generate_bulk(
    input_zip: UploadFile | None = File(None, description="ZIP containing manifest.json + targets/"),
    csv_file: UploadFile | None = File(None, description="CSV with id,html_filename (alternative to ZIP)"),
    dataset_zip: UploadFile | None = File(None, description="Optional ZIP of source HTML files (CSV mode). Extracts to per-job dir; overrides legitimate_dir."),
    legitimate_dir: str = Form(
        "legitimate_html_archive",
        description="Directory holding source HTML files (for CSV mode). Relative to data_dir or absolute, but must resolve inside data_dir. Ignored if dataset_zip is provided.",
    ),
    defaults_json: str = Form(
        "",
        description="Optional JSON object with manifest defaults (technique_configs, hybrid_mode, include_screenshots, concurrency, output_layout, ...) — used in CSV mode.",
    ),
    distribution_json: str = Form(
        "",
        description="Optional JSON map {technique_id_or_T_id: percent}. When set, each entry is assigned exactly one technique by deterministic shuffled allocation; technique_configs in defaults_json is ignored. Sum must be 100 (percent) or 1.0 (fraction).",
    ),
    include_screenshots: bool | None = Form(
        None,
        description="Optional UI override for screenshot generation. When omitted, manifest/default settings apply.",
    ),
    html_only: bool | None = Form(
        None,
        description="Optional UI override that excludes URL techniques and URL-variation artifacts.",
    ),
) -> JobCreateResponse:
    """
    Submit a bulk dataset generation job.

    Three input modes (provide exactly one):

    - **ZIP manifest mode** — `input_zip` containing `manifest.json` + `targets/` folder.
      Output defaults to `per_entry` layout under `output/<entry_id>/...`.

    - **CSV mode** — `csv_file` (columns `id,html_filename`) + `dataset_zip` or `legitimate_dir`.
      Source HTML files are read from the dataset ZIP or an existing directory.
      Output defaults to `per_kind` layout under
      `output/{phishing_html_archive,phishing_url_archive,reports,screenshots,extras}/...`.

    - **Auto-detect mode** — `dataset_zip` only (no `csv_file`).
      Entries are derived from the `.html` filenames inside the ZIP;
      URLs are extracted from the `YYYYMMDD__domain__hash.html` pattern.

    Returns `{job_id, status:"pending", entries_total}`. Poll `GET /jobs/{id}`.
    """
    if input_zip is not None and csv_file is not None:
        raise HTTPException(400, "provide only one of input_zip or csv_file")
    if input_zip is not None and dataset_zip is not None:
        raise HTTPException(400, "dataset_zip is for CSV/auto-detect mode; cannot combine with input_zip")
    if input_zip is None and csv_file is None and dataset_zip is None:
        raise HTTPException(
            400,
            "provide one of: input_zip, csv_file, or dataset_zip (auto-detects entries from HTML filenames)",
        )

    job_id = str(uuid.uuid4())
    jdir = job_dir(job_id)
    input_dir = jdir / "input"
    input_dir.mkdir(exist_ok=True)

    settings = get_settings()
    if input_zip is None:
        ds_raw: bytes | None = None
        if dataset_zip is not None:
            try:
                ds_raw = await read_with_cap(
                    dataset_zip, settings.max_input_zip_size_bytes,
                    field_name="dataset_zip",
                )
            except HTTPException:
                shutil.rmtree(jdir, ignore_errors=True)
                raise
            if not ds_raw:
                shutil.rmtree(jdir, ignore_errors=True)
                raise HTTPException(400, "dataset_zip is empty")
            try:
                legit_root = _extract_dataset_zip(ds_raw, jdir / "legit")
            except HTTPException:
                shutil.rmtree(jdir, ignore_errors=True)
                raise
        else:
            legit_root = _resolve_legitimate_dir(legitimate_dir)

        defaults: dict = {}
        if defaults_json.strip():
            try:
                defaults = json.loads(defaults_json)
                if not isinstance(defaults, dict):
                    raise ValueError("defaults_json must decode to a JSON object")
            except Exception as exc:
                shutil.rmtree(jdir, ignore_errors=True)
                raise HTTPException(422, f"invalid defaults_json: {exc}")

        if include_screenshots is not None:
            defaults["include_screenshots"] = include_screenshots
        if html_only is not None:
            defaults["html_only"] = html_only

        if csv_file is not None:
            try:
                raw = await read_with_cap(
                    csv_file, settings.max_csv_size_bytes, field_name="csv_file",
                )
            except HTTPException:
                shutil.rmtree(jdir, ignore_errors=True)
                raise
            if not raw:
                shutil.rmtree(jdir, ignore_errors=True)
                raise HTTPException(400, "csv_file is empty")
            (input_dir / "input.csv").write_bytes(raw)
            manifest = _csv_to_manifest(raw, legit_root, defaults)
        else:
            assert ds_raw is not None
            manifest = _zip_to_manifest(ds_raw, legit_root, defaults)

        if distribution_json.strip():
            try:
                distribution = json.loads(distribution_json)
            except Exception as exc:
                shutil.rmtree(jdir, ignore_errors=True)
                raise HTTPException(422, f"invalid distribution_json: {exc}")
            counts = _bake_distribution(manifest["entries"], distribution)
            manifest["defaults"]["distribution"] = distribution
            manifest["defaults"]["distribution_counts"] = {
                str(tid): c for tid, c in counts.items()
            }
            if manifest["defaults"].get("html_only", False):
                manifest["defaults"]["auto_url_pairing"] = False
            else:
                manifest["defaults"].setdefault("auto_url_pairing", True)

        entries, defaults_resolved = _validate_manifest(manifest)

    else:
        input_zip_path = jdir / "input.zip"
        try:
            raw = await read_with_cap(
                input_zip, settings.max_input_zip_size_bytes, field_name="input_zip",
            )
        except HTTPException:
            shutil.rmtree(jdir, ignore_errors=True)
            raise
        if not raw:
            shutil.rmtree(jdir, ignore_errors=True)
            raise HTTPException(400, "input_zip is empty")
        input_zip_path.write_bytes(raw)

        try:
            with zipfile.ZipFile(input_zip_path) as zf:
                for name in zf.namelist():
                    if name.startswith("/") or ".." in Path(name).parts:
                        raise HTTPException(422, f"unsafe path in zip: {name}")
                zf.extractall(input_dir)
        except zipfile.BadZipFile:
            shutil.rmtree(jdir, ignore_errors=True)
            raise HTTPException(400, "input_zip is not a valid ZIP file")

        manifest_path = input_dir / "manifest.json"
        if not manifest_path.exists():
            shutil.rmtree(jdir, ignore_errors=True)
            raise HTTPException(422, "manifest.json missing from ZIP root")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            shutil.rmtree(jdir, ignore_errors=True)
            raise HTTPException(422, f"manifest.json is not valid JSON: {exc}")

        if include_screenshots is not None:
            manifest.setdefault("defaults", {})["include_screenshots"] = include_screenshots
        if html_only is not None:
            manifest.setdefault("defaults", {})["html_only"] = html_only
            if html_only:
                manifest["defaults"]["auto_url_pairing"] = False

        entries, defaults_resolved = _validate_manifest(manifest)

    settings_ = get_settings()
    requested_conc = int(defaults_resolved.get("concurrency", settings_.bulk_default_concurrency))
    options = {
        "concurrency": min(requested_conc, settings_.bulk_max_concurrency),
    }
    if "bulk_entry_timeout_s" in defaults_resolved:
        try:
            options["bulk_entry_timeout_s"] = float(defaults_resolved["bulk_entry_timeout_s"])
        except (TypeError, ValueError):
            pass

    store = get_job_store()
    store.create(job_id, manifest, options, entries_total=len(entries))
    get_job_runner().notify_new_job()

    return JobCreateResponse(
        job_id=job_id, status="pending", entries_total=len(entries),
    )


@router.get("/jobs", response_model=JobsListResponse)
async def list_jobs() -> JobsListResponse:
    jobs = get_job_store().list(limit=200)
    return JobsListResponse(
        total=len(jobs),
        jobs=[_to_status_response(j) for j in jobs],
    )


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job(job_id: str) -> JobStatusResponse:
    job = get_job_store().get(job_id)
    if not job:
        raise HTTPException(404, f"job {job_id} not found")
    return _to_status_response(job)


@router.get("/jobs/{job_id}/download")
async def download_results(job_id: str) -> FileResponse:
    job = get_job_store().get(job_id)
    if not job:
        raise HTTPException(404, f"job {job_id} not found")
    if job["status"] != "completed":
        raise HTTPException(409, f"job is {job['status']}, not completed yet")
    zip_path = await asyncio.to_thread(build_results_zip, job_id)
    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=f"phishgen_bulk_{job_id[:8]}.zip",
    )


@router.get("/jobs/{job_id}/entries")
async def list_job_entries(
    job_id: str,
    limit: int = 200,
    status: str = "",
) -> dict:
    """Return recent per-entry rows from the job's summary.csv as JSON.

    Used by the UI to render a live activity feed inside the job detail
    panel — operators can see which entries crawled successfully, which
    timed out, and which failed, without downloading the CSV.

    `limit` is the number of *most recent* rows to return (tail). `status`
    optionally filters to one of `ok`, `ok_partial`, `failed`, `timeout`.
    A row is treated as `timeout` when its `attempts` column contains
    "hard_timeout" — that's how process_crawl_entry tags wall-clock skips.
    """
    job = get_job_store().get(job_id)
    if not job:
        raise HTTPException(404, f"job {job_id} not found")
    csv_path = job_dir(job_id) / "output" / "summary.csv"
    if not csv_path.exists():
        return {"job_id": job_id, "total": 0, "rows": []}

    limit = max(1, min(2000, int(limit)))

    try:
        with csv_path.open("r", encoding="utf-8", newline="") as f:
            reader = csvlib.DictReader(f)
            rows = list(reader)
    except Exception as exc:
        raise HTTPException(500, f"failed to read summary.csv: {exc}")

    total = len(rows)

    out: list[dict] = []
    for r in rows:
        raw_status = (r.get("status") or "").lower()
        attempts = (r.get("attempts") or "").lower()
        if raw_status == "failed" and "hard_timeout" in attempts:
            kind = "timeout"
        elif raw_status == "failed" and "unreachable" in attempts:
            kind = "unreachable"
        elif raw_status == "ok":
            kind = "ok"
        elif raw_status == "ok_partial":
            kind = "ok_partial"
        elif raw_status == "failed":
            kind = "failed"
        else:
            applied = (r.get("applied") or "").lower()
            kind = "ok" if applied in ("true", "1") else (
                "failed" if r.get("error") else "ok"
            )
        r["status_kind"] = kind
        out.append(r)

    if status:
        out = [r for r in out if r["status_kind"] == status.lower()]

    tail = out[-limit:]
    return {
        "job_id": job_id,
        "total": total,
        "returned": len(tail),
        "rows": tail,
    }


@router.get("/jobs/{job_id}/summary.csv")
async def download_summary_csv(job_id: str) -> FileResponse:
    job = get_job_store().get(job_id)
    if not job:
        raise HTTPException(404, f"job {job_id} not found")
    csv_path = job_dir(job_id) / "output" / "summary.csv"
    if not csv_path.exists():
        raise HTTPException(409, "summary.csv not yet available")
    return FileResponse(
        csv_path,
        media_type="text/csv",
        filename=f"phishgen_bulk_{job_id[:8]}_summary.csv",
    )


@router.post("/jobs/{job_id}/pause")
async def pause_job(job_id: str) -> dict:
    """Pause a running or pending job. In-flight workers are cancelled at
    their next await point and the job transitions to `paused`. Already-
    completed entries (in summary.csv) are preserved. POST /jobs/{id}/resume
    to continue.
    """
    store = get_job_store()
    job = store.get(job_id)
    if not job:
        raise HTTPException(404, f"job {job_id} not found")
    if job["status"] not in ("pending", "running"):
        raise HTTPException(409, f"job is {job['status']}, cannot pause")
    if not store.request_pause(job_id):
        raise HTTPException(409, "job is no longer pause-eligible")
    return {"status": "pause_requested", "id": job_id}


@router.post("/jobs/{job_id}/resume")
async def resume_job(job_id: str) -> dict:
    """Resume a paused job. The runner re-reads summary.csv, skips entries
    already processed, and picks up where it left off.
    """
    store = get_job_store()
    job = store.get(job_id)
    if not job:
        raise HTTPException(404, f"job {job_id} not found")
    if job["status"] != "paused":
        raise HTTPException(409, f"job is {job['status']}, not paused")
    if not store.resume_paused(job_id):
        raise HTTPException(409, "job is no longer resume-eligible")
    get_job_runner().notify_new_job()
    return {"status": "pending", "id": job_id}


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: str) -> dict:
    """Cancel a running/pending job, or delete a paused/terminal one."""
    store = get_job_store()
    job = store.get(job_id)
    if not job:
        raise HTTPException(404, f"job {job_id} not found")
    if job["status"] in ("pending", "running"):
        store.request_cancel(job_id)
        return {"status": "cancel_requested", "id": job_id}
    shutil.rmtree(job_dir(job_id), ignore_errors=True)
    store.delete(job_id)
    return {"status": "deleted", "id": job_id}
