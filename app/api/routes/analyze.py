from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.api.schemas.analyze import (
    AnalyzeResponse, AnalyzeTechniqueResult, HTMLFeaturesSchema,
)
from app.config import get_settings
from app.core.analyzer import HTMLAnalyzer
from app.core.registry import TechniqueRegistry
from app.utils.upload_utils import read_with_cap

router = APIRouter()


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(
    url: str = Form(..., description="Target URL"),
    html_file: UploadFile = File(..., description="HTML file to analyze"),
    screenshot: UploadFile | None = File(None, description="Optional screenshot"),
    category_filter: str = Form(
        "",
        description=(
            "Optional comma-separated list of categories to keep "
            "(credential_theft, brand_impersonation, malware_distribution, "
            "personal_info_harvesting). Empty = all techniques."
        ),
    ),
) -> AnalyzeResponse:
    """
    Analyze an HTML file + URL and return which of the 25 phishing techniques
    are applicable (and why inapplicable ones cannot be used).
    """
    raw = await read_with_cap(
        html_file, get_settings().max_html_size_bytes, field_name="html_file",
    )
    if not raw:
        raise HTTPException(status_code=400, detail="html_file is empty")

    html = raw.decode("utf-8", errors="replace")

    cat_filter = [c.strip() for c in category_filter.split(",") if c.strip()]

    analyzer = HTMLAnalyzer()
    features = analyzer.analyze(html, url)
    all_techniques = TechniqueRegistry.all()
    eligibility_list = analyzer.evaluate_eligibility(
        features, all_techniques, category_filter=cat_filter or None,
    )

    applicable: list[AnalyzeTechniqueResult] = []
    inapplicable: list[AnalyzeTechniqueResult] = []

    for e in eligibility_list:
        item = AnalyzeTechniqueResult(**e.to_dict())
        if e.is_applicable:
            applicable.append(item)
        else:
            inapplicable.append(item)

    return AnalyzeResponse(
        url=url,
        html_features=HTMLFeaturesSchema(**features.to_dict()),
        applicable=applicable,
        inapplicable=inapplicable,
        applicable_count=len(applicable),
        inapplicable_count=len(inapplicable),
    )
