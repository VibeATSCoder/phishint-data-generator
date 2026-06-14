from __future__ import annotations

import app.techniques  # noqa: F401
from app.core.analyzer import HTMLAnalyzer
from app.core.registry import TechniqueRegistry


def test_features_with_form(simple_html):
    analyzer = HTMLAnalyzer()
    features = analyzer.analyze(simple_html, "https://example.com")
    assert features.has_input_fields is True
    assert features.has_password_input is True
    assert features.form_count == 1
    assert features.input_count == 2


def test_features_no_form(no_form_html):
    analyzer = HTMLAnalyzer()
    features = analyzer.analyze(no_form_html, "https://example.com")
    assert features.has_input_fields is False
    assert features.form_count == 0


def test_features_with_image(html_with_image):
    analyzer = HTMLAnalyzer()
    features = analyzer.analyze(html_with_image, "https://example.com")
    assert features.has_images is True
    assert features.image_count == 1


def test_registry_has_25_techniques():
    assert TechniqueRegistry.count() == 25


def test_eligibility_no_form_blocks_shadow_dom(no_form_html):
    analyzer = HTMLAnalyzer()
    features = analyzer.analyze(no_form_html, "https://example.com")
    from app.techniques.group3_html.t11_shadow_dom import ShadowDomTechnique
    eligibility = analyzer.evaluate_eligibility(features, [ShadowDomTechnique])[0]
    assert eligibility.is_applicable is False
    assert "input" in eligibility.reason.lower() or "form" in eligibility.reason.lower()


def test_eligibility_url_techniques_always_applicable(no_form_html):
    analyzer = HTMLAnalyzer()
    features = analyzer.analyze(no_form_html, "https://example.com")
    from app.techniques.group1_url.t01_homoglyph import HomoglyphTechnique
    eligibility = analyzer.evaluate_eligibility(features, [HomoglyphTechnique])[0]
    assert eligibility.is_applicable is True
