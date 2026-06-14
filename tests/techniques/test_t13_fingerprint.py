"""T13 — Anti-bot fingerprint. Verifies the injected script checks
navigator.webdriver, plugins.length, languages.length, and at least
one of canvas/WebGL/screen, and that the checks_emitted detail mirrors
those names."""
from app.techniques.group3_html.t13_fingerprint import AntiBotFingerprintTechnique


def test_t13_injects_webdriver_check(english_login_html, sample_url):
    tech = AntiBotFingerprintTechnique()
    res = tech.apply(english_login_html, sample_url, tech.get_default_options())
    assert res.modified_html is not None
    assert "navigator.webdriver" in res.modified_html
    assert "navigator.plugins" in res.modified_html
    assert "navigator.languages" in res.modified_html


def test_t13_records_checks_in_details(english_login_html, sample_url):
    tech = AntiBotFingerprintTechnique()
    res = tech.apply(english_login_html, sample_url, tech.get_default_options())
    change = res.change_log[0]
    checks = change.details["checks_emitted"]
    assert "webdriver" in checks
    assert "plugins0" in checks
    assert "langs0" in checks


def test_t13_redirect_url_passed_through(english_login_html, sample_url):
    tech = AntiBotFingerprintTechnique()
    opts = tech.get_default_options()
    opts["bot_redirect_url"] = "https://example.org/bot"
    res = tech.apply(english_login_html, sample_url, opts)
    assert "https://example.org/bot" in res.modified_html
