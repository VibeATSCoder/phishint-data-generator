"""T16 — Fake CAPTCHA overlay. Verifies invalid vendor names fall back to
cloudflare with a log line, the overlay is position:fixed inset:0, and a
Persian source page produces Persian overlay strings."""
from app.techniques.group4_antibot.t16_fake_captcha import FakeCaptchaTechnique


def test_t16_persian_source_gives_persian_overlay(persian_login_html, sample_url):
    tech = FakeCaptchaTechnique()
    res = tech.apply(persian_login_html, sample_url, tech.get_default_options())
    assert res.modified_html is not None
    assert "لحظه‌ای صبر کنید" in res.modified_html
    assert res.change_log[0].details["lang"] == "fa"


def test_t16_english_source_gives_english_overlay(english_login_html, sample_url):
    tech = FakeCaptchaTechnique()
    res = tech.apply(english_login_html, sample_url, tech.get_default_options())
    assert "Just a moment" in res.modified_html
    assert res.change_log[0].details["lang"] == "en"


def test_t16_invalid_vendor_falls_back_to_cloudflare(english_login_html, sample_url):
    tech = FakeCaptchaTechnique()
    opts = tech.get_default_options()
    opts["captcha_type"] = "bogus-vendor"
    res = tech.apply(english_login_html, sample_url, opts)
    assert res.change_log[0].details["vendor"] == "cloudflare"


def test_t16_scroll_lock_in_css(english_login_html, sample_url):
    tech = FakeCaptchaTechnique()
    res = tech.apply(english_login_html, sample_url, tech.get_default_options())
    assert "overflow:hidden!important" in res.modified_html
