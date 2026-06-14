"""T21 — MFA fatigue. Verifies the runaway setInterval is cleared (the
fix the reviewer mandated), a Persian source page produces Persian modal
text, and spoofed device context lands in details + the HTML."""
from app.techniques.group6_mfa.t21_mfa_fatigue import MfaFatigueTechnique


def test_t21_clears_interval_at_cap(english_login_html, sample_url):
    tech = MfaFatigueTechnique()
    res = tech.apply(english_login_html, sample_url, tech.get_default_options())
    assert res.modified_html is not None
    assert "clearInterval" in res.modified_html


def test_t21_persian_push_modal(persian_login_html, sample_url):
    tech = MfaFatigueTechnique()
    res = tech.apply(persian_login_html, sample_url, tech.get_default_options())
    assert "تأیید درخواست ورود" in res.modified_html
    assert res.change_log[0].details["lang"] == "fa"


def test_t21_records_spoofed_device(english_login_html, sample_url):
    tech = MfaFatigueTechnique()
    res = tech.apply(english_login_html, sample_url, tech.get_default_options())
    change = res.change_log[0]
    assert change.details["device_name"]
    assert change.details["device_location"]
    assert change.details["spoofed_ip"]
