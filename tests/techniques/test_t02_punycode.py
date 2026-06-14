"""T2 — Punycode / IDN homograph: replace Latin chars with Cyrillic look-
alikes then IDNA-encode each label. Verifies the result is ASCII (xn-- or
plain), every label is reported in details, and IPv6 hosts are skipped."""
from app.techniques.group1_url.t02_punycode import PunycodeTechnique
from tests.techniques.conftest import assert_details_has


def test_t02_produces_ascii_url(sample_url):
    tech = PunycodeTechnique()
    res = tech.apply("", sample_url, tech.get_default_options())
    assert res.modified_url is not None
    res.modified_url.encode("ascii")
    change = res.change_log[0]
    assert_details_has(change, "char_set", "labels_encoded", "labels_skipped")


def test_t02_skips_ipv6(ipv6_url):
    tech = PunycodeTechnique()
    res = tech.apply("", ipv6_url, tech.get_default_options())
    assert res.modified_url is None
    assert res.change_log[0].change_type == "url_punycode_skipped"


def test_t02_mixed_script_only_keeps_label_when_no_substitution():
    tech = PunycodeTechnique()
    opts = tech.get_default_options()
    opts["mixed_script_only"] = True
    res = tech.apply("", "https://123.example.com/", opts)
    assert res.modified_url is not None
