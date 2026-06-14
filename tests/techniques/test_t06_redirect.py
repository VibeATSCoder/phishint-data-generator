"""T6 — Multi-stage redirect chain. Verifies a Persian-source page gets a
Persian waiting-room screen, the redirect chain is reported in details,
and non-HTTP schemes are rejected without producing a broken meta refresh."""
from app.techniques.group1_url.t06_redirect import RedirectChainTechnique
from tests.techniques.conftest import assert_details_has


def test_t06_builds_hop_chain(persian_login_html, sample_url):
    tech = RedirectChainTechnique()
    res = tech.apply(persian_login_html, sample_url, tech.get_default_options())
    assert res.modified_html is not None
    change = res.change_log[0]
    assert_details_has(change, "hops", "chain", "html_validates")
    assert change.details["html_validates"] is True


def test_t06_persian_source_gives_persian_waiting_text(persian_login_html, sample_url):
    tech = RedirectChainTechnique()
    res = tech.apply(persian_login_html, sample_url, tech.get_default_options())
    assert res.modified_html is not None
    assert "در حال انتقال" in res.modified_html
    assert 'lang="fa"' in res.modified_html
    assert 'dir="rtl"' in res.modified_html


def test_t06_english_source_keeps_english_waiting_text(english_login_html, sample_url):
    tech = RedirectChainTechnique()
    res = tech.apply(english_login_html, sample_url, tech.get_default_options())
    assert "Redirecting" in res.modified_html


def test_t06_rejects_non_http_scheme():
    tech = RedirectChainTechnique()
    res = tech.apply("", "javascript:alert(1)", tech.get_default_options())
    assert res.modified_html is None
    assert res.change_log[0].change_type == "url_redirect_skipped"
    assert res.change_log[0].details.get("reason") == "bad_scheme"
