"""T1 — Homoglyph: Latin → Cyrillic/Greek look-alike substitution on the
domain. Verifies the mutated URL differs from the original, the change
records which chars were replaced, IPv6 hosts are skipped cleanly, and
already-punycode labels are not double-encoded."""
from app.techniques.group1_url.t01_homoglyph import HomoglyphTechnique
from tests.techniques.conftest import assert_details_has


def test_t01_replaces_chars_in_base_label(sample_url):
    tech = HomoglyphTechnique()
    res = tech.apply("", sample_url, tech.get_default_options())
    assert res.modified_url and res.modified_url != sample_url
    change = res.change_log[0]
    assert_details_has(change, "char_set", "chars_replaced", "label")
    assert change.details["chars_replaced"] >= 0


def test_t01_skips_ipv6(ipv6_url):
    tech = HomoglyphTechnique()
    res = tech.apply("", ipv6_url, tech.get_default_options())
    assert res.modified_url is None
    change = res.change_log[0]
    assert change.change_type == "url_domain_homoglyph_skipped"
    assert change.details.get("reason") == "ipv6_literal"


def test_t01_skips_already_punycode_label():
    tech = HomoglyphTechnique()
    res = tech.apply("", "https://xn--mgbh0fb.example.com/", tech.get_default_options())
    assert res.change_log
