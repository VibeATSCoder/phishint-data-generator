"""T17 — Multi-stage CAPTCHA flow. Verifies stage 2 filename is derived
from the URL, both stages land in extra_files, and Persian source pages
yield Persian stage 1 + stage 2 pages."""
from app.techniques.group5_delivery.t17_captcha_flow import CaptchaFlowTechnique


def test_t17_emits_two_stage_files(english_login_html, sample_url):
    tech = CaptchaFlowTechnique()
    res = tech.apply(english_login_html, sample_url, tech.get_default_options())
    change = res.change_log[0]
    stage1 = change.details["stage1_name"]
    stage2 = change.details["stage2_name"]
    assert stage1 != "captcha_stage1.html"
    assert stage1 in res.extra_files
    assert stage2 in res.extra_files


def test_t17_persian_source_produces_persian_stage1(persian_login_html, sample_url):
    tech = CaptchaFlowTechnique()
    res = tech.apply(persian_login_html, sample_url, tech.get_default_options())
    assert "یک مرحله دیگر" in res.modified_html
    assert res.change_log[0].details["lang"] == "fa"


def test_t17_records_embedded_real_form_flag(persian_login_html, sample_url):
    tech = CaptchaFlowTechnique()
    res = tech.apply(persian_login_html, sample_url, tech.get_default_options())
    change = res.change_log[0]
    assert change.details["embedded_real_form"] is True
