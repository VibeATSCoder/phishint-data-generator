"""T15 — Geo / UA fencing. Verifies the expanded bot UA list is injected,
the v2 template includes timezone + WebRTC checks when configured, and
the block/redirect/decoy mode is reported in details."""
from app.techniques.group4_antibot.t15_geofence import GeofenceTechnique


def test_t15_v2_includes_extended_ua_list(english_login_html, sample_url):
    tech = GeofenceTechnique()
    res = tech.apply(english_login_html, sample_url, tech.get_default_options())
    assert res.modified_html is not None
    for ua in ("googlebot", "scrapy", "okhttp", "playwright"):
        assert ua in res.modified_html


def test_t15_timezone_check_when_allowed_tzs_set(english_login_html, sample_url):
    tech = GeofenceTechnique()
    opts = tech.get_default_options()
    opts["allowed_timezones"] = ["Asia/Tehran"]
    res = tech.apply(english_login_html, sample_url, opts)
    assert "Intl.DateTimeFormat" in res.modified_html
    change = res.change_log[0]
    assert "tz" in change.details["checks"]


def test_t15_redirect_mode_emits_decoy_url(english_login_html, sample_url):
    tech = GeofenceTechnique()
    opts = tech.get_default_options()
    opts["mode"] = "redirect"
    opts["decoy_url"] = "https://example.org/decoy"
    res = tech.apply(english_login_html, sample_url, opts)
    assert "https://example.org/decoy" in res.modified_html
