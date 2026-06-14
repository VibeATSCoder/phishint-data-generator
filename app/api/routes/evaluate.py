from __future__ import annotations

import difflib
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.core.registry import TechniqueRegistry

router = APIRouter()


@router.post("/evaluate-files", tags=["Evaluation"])
async def evaluate_files(
    technique_id: int = Form(..., description="Technique ID (1–25)"),
    original_url: str = Form("", description="Original URL (used as evaluate context)"),
    original_html: UploadFile = File(..., description="Original HTML file"),
    phishing_file: UploadFile = File(..., description="Phishing output: HTML file or .txt with modified URL"),
) -> dict:
    """
    Evaluate a generated phishing artifact against the original HTML.

    - For HTML techniques (T07–T25) upload the generated .html as `phishing_file`.
    - For URL techniques (T01–T06) upload the generated .txt (one URL per line).

    Returns evaluation signals / issues / score, a technique description, and a
    structured diff (with line numbers) between original and phishing content.
    """
    technique_cls = TechniqueRegistry.get(technique_id)
    if technique_cls is None:
        raise HTTPException(status_code=404, detail=f"Technique T{technique_id:02d} not found")
    technique = technique_cls()

    orig_bytes = await original_html.read()
    phish_bytes = await phishing_file.read()

    orig_text = orig_bytes.decode("utf-8", errors="replace")
    phish_text = phish_bytes.decode("utf-8", errors="replace")

    phish_stripped = phish_text.strip()
    is_url_output = (
        len(phish_stripped.splitlines()) <= 3
        and (
            phish_stripped.startswith("http")
            or (phish_stripped and "." in phish_stripped and "<" not in phish_stripped)
        )
    )

    if is_url_output:
        eval_html = orig_text
        eval_url  = phish_stripped
    else:
        eval_html = phish_text
        eval_url  = original_url or ""

    result = technique.evaluate(eval_html, eval_url, [], {})

    if is_url_output:
        orig_lines  = [original_url] if original_url else ["(no original URL provided)"]
        phish_lines = [eval_url]
    else:
        orig_lines  = orig_text.splitlines()
        phish_lines = phish_text.splitlines()

    diff_groups = _build_diff(orig_lines, phish_lines, context=4, max_groups=60)

    total_added   = sum(1 for g in diff_groups for l in g if l["type"] == "add")
    total_removed = sum(1 for g in diff_groups for l in g if l["type"] == "del")

    reqs = [r.value if hasattr(r, "value") else str(r) for r in getattr(technique_cls, "REQUIREMENTS", [])]

    return {
        "technique_id": technique_id,
        "technique_name": technique.TECHNIQUE_NAME,
        "technique_group": technique.GROUP.value if hasattr(technique.GROUP, "value") else str(technique.GROUP),
        "technique_description": technique.DESCRIPTION,
        "technique_requirements": reqs,
        "passed": result.passed,
        "score": round(result.score, 4),
        "signals": result.signals,
        "issues": result.issues,
        "details": result.details,
        "is_url_output": is_url_output,
        "diff_groups": diff_groups,
        "diff_stats": {
            "total_added": total_added,
            "total_removed": total_removed,
            "original_lines": len(orig_lines),
            "phishing_lines": len(phish_lines),
            "original_bytes": len(orig_bytes),
            "phishing_bytes": len(phish_bytes),
            "size_delta_bytes": len(phish_bytes) - len(orig_bytes),
        },
    }


def _build_diff(
    orig_lines: list[str],
    phish_lines: list[str],
    context: int = 4,
    max_groups: int = 60,
) -> list[list[dict]]:
    sm = difflib.SequenceMatcher(None, orig_lines, phish_lines, autojunk=False)
    groups: list[list[dict]] = []
    for group in sm.get_grouped_opcodes(context):
        if len(groups) >= max_groups:
            break
        lines: list[dict] = []
        for tag, i1, i2, j1, j2 in group:
            if tag == "equal":
                for k in range(i2 - i1):
                    lines.append({"type": "ctx", "text": orig_lines[i1 + k],
                                  "orig_ln": i1 + k + 1, "phish_ln": j1 + k + 1})
            if tag in ("replace", "delete"):
                for k in range(i2 - i1):
                    lines.append({"type": "del", "text": orig_lines[i1 + k],
                                  "orig_ln": i1 + k + 1, "phish_ln": None})
            if tag in ("replace", "insert"):
                for k in range(j2 - j1):
                    lines.append({"type": "add", "text": phish_lines[j1 + k],
                                  "orig_ln": None, "phish_ln": j1 + k + 1})
        if lines:
            groups.append(lines)
    return groups
