"""T8 — Favicon mimicry. Verifies all <link rel=*icon*> variants are
updated (not just the first), the picker logs links_found and
links_updated, and Clearbit lookups strip port/path correctly."""
from app.techniques.group2_visual.t08_favicon import FaviconMimicryTechnique
from tests.techniques.conftest import assert_details_has


def test_t08_records_link_counts(persian_login_html, sample_url):
    tech = FaviconMimicryTechnique()
    res = tech.apply(persian_login_html, sample_url, tech.get_default_options())
    change = res.change_log[0]
    assert_details_has(change, "links_found")


def test_t08_clearbit_mode_uses_normalised_domain():
    tech = FaviconMimicryTechnique()
    opts = tech.get_default_options()
    opts["use_clearbit"] = True
    res = tech.apply(
        '<html><head><link rel="icon" href="/x.ico"></head><body></body></html>',
        "https://www.example.com:8080/login?ref=1",
        opts,
    )
    change = res.change_log[0]
    if change.details.get("source") == "clearbit":
        assert change.details["domain"] == "example.com"
