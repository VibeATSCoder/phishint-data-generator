"""T18 — QR code generation. Verifies EC auto-tunes by URL length, invalid
EC values produce a clear skip, and an email-safe plain-URL file is
emitted alongside the PNG."""
import pytest

from app.techniques.group5_delivery.t18_qr_code import QrCodeTechnique


qrcode_available = True
try:
    import qrcode  # noqa: F401
except ImportError:
    qrcode_available = False


@pytest.mark.skipif(not qrcode_available, reason="qrcode lib not installed")
def test_t18_auto_tunes_ec_level(english_login_html, sample_url):
    tech = QrCodeTechnique()
    opts = tech.get_default_options()
    opts["error_correction"] = "auto"
    res = tech.apply(english_login_html, sample_url, opts)
    change = res.change_log[0]
    assert change.details["ec_level"] in ("H", "Q", "M")


@pytest.mark.skipif(not qrcode_available, reason="qrcode lib not installed")
def test_t18_rejects_unknown_ec_level(english_login_html, sample_url):
    tech = QrCodeTechnique()
    opts = tech.get_default_options()
    opts["error_correction"] = "Z"
    res = tech.apply(english_login_html, sample_url, opts)
    assert res.change_log[0].change_type == "qr_skipped"


@pytest.mark.skipif(not qrcode_available, reason="qrcode lib not installed")
def test_t18_emits_email_safe_url_file(english_login_html, sample_url):
    tech = QrCodeTechnique()
    res = tech.apply(english_login_html, sample_url, tech.get_default_options())
    assert "qr_url_for_email.txt" in res.extra_files
