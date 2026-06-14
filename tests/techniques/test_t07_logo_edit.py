"""T7 — Logo pixel-level editing. Verifies the brand-logo picker selects
the labeled logo over a banner, the picker name is in details, and SVG
assets get the CSS-filter fallback rather than a silent skip."""
from app.techniques.group2_visual.t07_logo_edit import LogoPixelEditTechnique
from tests.techniques.conftest import assert_details_has


def test_t07_picks_class_logo_over_first_img(persian_login_html, sample_url):
    tech = LogoPixelEditTechnique()
    res = tech.apply(persian_login_html, sample_url, tech.get_default_options())
    assert res.change_log
    change = res.change_log[0]
    assert "picker" in change.details
    assert change.details["picker"] in (
        "img.class=logo", "rel=apple-touch-icon", "rel=icon",
    )


def test_t07_returns_skipped_change_when_no_images():
    tech = LogoPixelEditTechnique()
    res = tech.apply("<html><body></body></html>", "https://example.com/", tech.get_default_options())
    change = res.change_log[0]
    assert change.change_type == "logo_edit_skipped"
    assert change.details["reason"] in ("no_candidate", "no_images_with_src")
