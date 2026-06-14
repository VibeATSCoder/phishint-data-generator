from __future__ import annotations

import app.techniques  # noqa: F401
from app.core.engine import GenerationEngine, TechniqueConfig


def test_single_technique_homoglyph(simple_html, sample_url):
    engine = GenerationEngine()
    result = engine.run(
        html=simple_html,
        url=sample_url,
        technique_configs=[TechniqueConfig(technique_id=1, options={"density": 1.0})],
        hybrid_mode=False,
    )
    assert result.run_id
    assert len(result.technique_results) == 1
    tr = result.technique_results[0]
    assert tr.success is True
    assert tr.modified_url is not None
    assert tr.modified_url != sample_url


def test_hybrid_url_then_html(simple_html, sample_url):
    engine = GenerationEngine()
    result = engine.run(
        html=simple_html,
        url=sample_url,
        technique_configs=[
            TechniqueConfig(technique_id=1),
            TechniqueConfig(technique_id=10),
        ],
        hybrid_mode=True,
    )
    assert result.final_url != sample_url
    assert "atob(" in result.final_html or "DOMContentLoaded" in result.final_html


def test_inapplicable_technique_skipped(no_form_html, sample_url):
    engine = GenerationEngine()
    result = engine.run(
        html=no_form_html,
        url=sample_url,
        technique_configs=[TechniqueConfig(technique_id=11)],
        hybrid_mode=True,
    )
    assert result.technique_results[0].success is False
    assert "not applicable" in result.technique_results[0].error.lower()


def test_unknown_technique_id(simple_html, sample_url):
    engine = GenerationEngine()
    result = engine.run(
        html=simple_html,
        url=sample_url,
        technique_configs=[TechniqueConfig(technique_id=999)],
        hybrid_mode=True,
    )
    assert result.technique_results[0].success is False
    assert "not found" in result.technique_results[0].error.lower()


def test_t4_long_url_extra_params(simple_html, sample_url):
    engine = GenerationEngine()
    result = engine.run(
        html=simple_html,
        url=sample_url,
        technique_configs=[
            TechniqueConfig(technique_id=4, options={"param_count": 10})
        ],
        hybrid_mode=False,
    )
    tr = result.technique_results[0]
    assert tr.success is True
    assert tr.modified_url is not None
    assert tr.modified_url.count("=") >= 10
