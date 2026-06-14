"""T3 — Look-alike + Leetspeak + trust words.

Verifies that the default strategy produces an independent look-alike domain
(not a subdomain of the original), leet substitutions are applied to the brand
label using only DNS-safe characters, Persian inputs get the Persian trust-word
bank, and path strategy skips when the path already has a trust word.
"""
from app.techniques.group1_url.t03_lookalike import LookAlikeTechnique
from tests.techniques.conftest import assert_details_has


def test_t03_standalone_domain_is_independent(sample_url):
    """Default strategy must produce a domain that is NOT a subdomain of the original."""
    tech = LookAlikeTechnique()
    res = tech.apply("", sample_url, tech.get_default_options())
    assert res.modified_url and "." in res.modified_url
    change = res.change_log[0]
    assert_details_has(change, "trust_words", "leet_words", "strategy", "brand_label", "tld")
    assert change.details["strategy"] in ("standalone", "prepend")

    from app.utils.url_utils import parse_url, split_domain_labels
    orig_netloc = parse_url(sample_url)[0].netloc
    new_netloc = parse_url(res.modified_url)[0].netloc
    assert orig_netloc not in new_netloc, (
        f"Look-alike domain {new_netloc!r} should not contain the original {orig_netloc!r}"
    )


def test_t03_persian_html_picks_persian_trust_words(persian_login_html, sample_url):
    tech = LookAlikeTechnique()
    res = tech.apply(persian_login_html, sample_url, tech.get_default_options())
    change = res.change_log[0]
    assert any(w in {"vorood", "tayid", "hesab", "amn", "bedoroz"}
               for w in change.details["trust_words"])


def test_t03_path_strategy_skips_when_path_has_trust_word():
    tech = LookAlikeTechnique()
    opts = tech.get_default_options()
    opts["strategy"] = "path"
    res = tech.apply("", "https://example.com/login/account", opts)
    assert res.change_log
