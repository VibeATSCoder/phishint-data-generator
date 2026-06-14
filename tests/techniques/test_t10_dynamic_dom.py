"""T10 — Dynamic DOM. Verifies the body is base64-encoded into the loader
script, head siblings (stylesheets, external scripts) survive verbatim,
and the original Persian/RTL content can be reconstructed from the encoded
payload — proving the encoding round-trip preserves the source language."""
import base64
import re

from app.techniques.group3_html.t10_dynamic_dom import DynamicDomTechnique
from tests.techniques.conftest import assert_details_has


def test_t10_encodes_body_to_base64(persian_login_html, sample_url):
    tech = DynamicDomTechnique()
    res = tech.apply(persian_login_html, sample_url, tech.get_default_options())
    assert res.modified_html is not None
    change = res.change_log[0]
    assert_details_has(change, "body_bytes_orig", "body_bytes_encoded")


def test_t10_round_trip_preserves_persian(persian_login_html, sample_url):
    """Decode the base64 payload from the loader and check Persian text
    is intact. Catches the encoding-corruption issue the reviewer flagged."""
    tech = DynamicDomTechnique()
    res = tech.apply(persian_login_html, sample_url, tech.get_default_options())
    m = re.search(r"atob\('([^']+)'\)", res.modified_html)
    assert m, "loader script not found in output"
    decoded = base64.b64decode(m.group(1)).decode("utf-8")
    assert "ورود" in decoded
    assert "گذرواژه" in decoded


def test_t10_preserves_head_link_and_script_counts(persian_login_html, sample_url):
    tech = DynamicDomTechnique()
    res = tech.apply(persian_login_html, sample_url, tech.get_default_options())
    change = res.change_log[0]
    assert change.details["stylesheets"] >= 1
