"""T14 — Hidden iframes. Verifies an iframe is injected with a meaningful
src (derived from target URL when not specified), the clip-path hiding
strategy is used by default, and a postMessage listener is wired."""
from app.techniques.group3_html.t14_iframe import HiddenIframeTechnique


def test_t14_derives_src_from_target_when_blank(english_login_html, sample_url):
    tech = HiddenIframeTechnique()
    opts = tech.get_default_options()
    opts["iframe_src"] = ""
    res = tech.apply(english_login_html, sample_url, opts)
    assert res.modified_html is not None
    change = res.change_log[0]
    assert change.details["src"].startswith("https://example.com/")
    assert "/login" in change.details["src"]


def test_t14_uses_clip_path_hiding_by_default(english_login_html, sample_url):
    tech = HiddenIframeTechnique()
    res = tech.apply(english_login_html, sample_url, tech.get_default_options())
    assert "clip-path:inset(100%)" in res.modified_html
    assert res.change_log[0].details["hide_strategy"] == "clip_path"


def test_t14_listener_wired_by_default(english_login_html, sample_url):
    tech = HiddenIframeTechnique()
    res = tech.apply(english_login_html, sample_url, tech.get_default_options())
    assert "addEventListener('message'" in res.modified_html
    assert res.change_log[0].details["listener_wired"] is True
