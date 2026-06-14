"""T22 — OAuth consent. Verifies the Microsoft + Google pages render in
the detected language, real MS Graph scope IDs are kept verbatim in the
hidden form fields while their human-readable descriptions are localised,
and PKCE fields are present."""
from app.techniques.group6_mfa.t22_oauth import OAuthPhishingTechnique


def test_t22_persian_ms_consent(persian_login_html):
    tech = OAuthPhishingTechnique()
    res = tech.apply(persian_login_html, "https://login.microsoftonline.com/", tech.get_default_options())
    assert res.modified_html is not None
    assert "دسترسی‌های درخواستی" in res.modified_html
    change = res.change_log[0]
    assert change.details["lang"] == "fa"
    assert change.details["pkce"] is True


def test_t22_keeps_ms_graph_scope_ids_verbatim(persian_login_html):
    tech = OAuthPhishingTechnique()
    res = tech.apply(persian_login_html, "https://login.microsoftonline.com/", tech.get_default_options())
    assert "Mail.ReadWrite" in res.modified_html
    assert "offline_access" in res.modified_html


def test_t22_google_consent(persian_login_html):
    tech = OAuthPhishingTechnique()
    opts = tech.get_default_options()
    opts["provider"] = "google"
    res = tech.apply(persian_login_html, "https://accounts.google.com/", opts)
    assert "گوگل" in res.modified_html


def test_t22_pkce_hidden_field(persian_login_html):
    tech = OAuthPhishingTechnique()
    res = tech.apply(persian_login_html, "https://example.com/", tech.get_default_options())
    assert 'name="code_challenge"' in res.modified_html
    assert 'name="code_challenge_method"' in res.modified_html
