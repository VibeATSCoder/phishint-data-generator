"""T25 — Baseline phishing form. Verifies the form action is rewritten,
the injected baseline form lands inside the SPA root (when one exists),
theme-color sniffing populates the button background, and a Persian
source page produces Persian form labels."""
from app.techniques.group7_advanced.t25_baseline import BaselinePhishingTechnique


def test_t25_redirects_existing_form_action(english_login_html, sample_url):
    tech = BaselinePhishingTechnique()
    res = tech.apply(english_login_html, sample_url, tech.get_default_options())
    assert res.modified_html is not None
    assert 'action="/collect"' in res.modified_html or "action='/collect'" in res.modified_html


def test_t25_injects_into_spa_root(spa_html, sample_url):
    tech = BaselinePhishingTechnique()
    res = tech.apply(spa_html, sample_url, tech.get_default_options())
    assert res.modified_html is not None
    root_idx = res.modified_html.find('id="root"')
    form_idx = res.modified_html.find("__phish_form_wrapper__")
    assert root_idx > 0 and form_idx > root_idx
    assert res.change_log[0].details["spa_root"] == "#root"


def test_t25_persian_form_labels():
    tech = BaselinePhishingTechnique()
    persian_spa = (
        '<!DOCTYPE html><html lang="fa" dir="rtl"><head><meta charset="utf-8">'
        '<title>خوش آمدید</title></head>'
        '<body><div id="root"></div></body></html>'
    )
    res = tech.apply(persian_spa, "https://example.com/", tech.get_default_options())
    assert "نام کاربری" in res.modified_html
    assert "گذرواژه" in res.modified_html
    assert res.change_log[0].details["lang"] == "fa"


def test_t25_theme_color_used_for_button():
    tech = BaselinePhishingTechnique()
    html = (
        '<!DOCTYPE html><html lang="en"><head>'
        '<meta name="theme-color" content="#e91e63">'
        '</head><body><div id="root"></div></body></html>'
    )
    res = tech.apply(html, "https://example.com/", tech.get_default_options())
    assert "#e91e63" in res.modified_html
    assert res.change_log[0].details["theme_color"] == "#e91e63"
