"""T11 — Shadow DOM encapsulation. Verifies the login form (NOT the
search bar) is the one moved, the form count is recorded, and orphan
password inputs get wrapped in a synthetic form when no <form> exists."""
from app.techniques.group3_html.t11_shadow_dom import ShadowDomTechnique


def test_t11_picks_login_form_not_search(multi_form_html, sample_url):
    tech = ShadowDomTechnique()
    res = tech.apply(multi_form_html, sample_url, tech.get_default_options())
    assert res.modified_html is not None
    change = res.change_log[0]
    assert change.details["forms_moved"] == 1
    assert change.details["picker"] == "form_with_password"
    assert "id=\"loginform\"" not in res.modified_html
    assert "id=\"searchbar\"" in res.modified_html


def test_t11_wraps_orphan_password_input():
    tech = ShadowDomTechnique()
    res = tech.apply(
        '<html><body><input type="email" name="email">'
        '<input type="password" name="pwd"></body></html>',
        "https://example.com/", tech.get_default_options(),
    )
    change = res.change_log[0]
    assert change.details["synthetic_form_built"] is True


def test_t11_skips_when_no_password_anywhere():
    tech = ShadowDomTechnique()
    res = tech.apply(
        "<html><body><p>just text</p></body></html>",
        "https://example.com/", tech.get_default_options(),
    )
    assert res.modified_html is None
    assert res.change_log[0].change_type == "shadow_dom_skipped"
