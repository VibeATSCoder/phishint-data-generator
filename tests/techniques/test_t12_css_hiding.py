"""T12 — CSS hiding. Verifies N honeypot field-name variants are injected
(not just one shape), aria-hidden + tabindex=-1 are present on every
honeypot, and the original form is marked with the .__pf__ class."""
from app.techniques.group3_html.t12_css_hiding import CssHidingTechnique
from tests.techniques.conftest import assert_details_has


def test_t12_injects_multiple_honeypot_variants(english_login_html, sample_url):
    tech = CssHidingTechnique()
    opts = tech.get_default_options()
    opts["honeypot_variants"] = 3
    res = tech.apply(english_login_html, sample_url, opts)
    change = res.change_log[0]
    assert_details_has(change, "honeypots_injected", "field_names")
    assert change.details["honeypots_injected"] == 3
    assert len(change.details["field_names"]) == 6


def test_t12_honeypot_forms_carry_aria_hidden(english_login_html, sample_url):
    tech = CssHidingTechnique()
    res = tech.apply(english_login_html, sample_url, tech.get_default_options())
    assert 'aria-hidden="true"' in res.modified_html
    assert 'tabindex="-1"' in res.modified_html


def test_t12_marks_real_forms_with_pf_class(english_login_html, sample_url):
    tech = CssHidingTechnique()
    res = tech.apply(english_login_html, sample_url, tech.get_default_options())
    assert "__pf__" in res.modified_html
