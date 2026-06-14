"""T19 — Blob URI dynamic QR. Verifies the script branches on Safari UA,
a noscript fallback img is present, and Persian source pages get the
Persian "scan to continue" label."""
import pytest

from app.techniques.group5_delivery.t19_blob_qr import BlobQrTechnique

qrcode_available = True
try:
    import qrcode  # noqa: F401
except ImportError:
    qrcode_available = False


@pytest.mark.skipif(not qrcode_available, reason="qrcode lib not installed")
def test_t19_includes_safari_branch(english_login_html, sample_url):
    tech = BlobQrTechnique()
    res = tech.apply(english_login_html, sample_url, tech.get_default_options())
    assert res.modified_html is not None
    assert "isSafari" in res.modified_html


@pytest.mark.skipif(not qrcode_available, reason="qrcode lib not installed")
def test_t19_emits_noscript_fallback(english_login_html, sample_url):
    tech = BlobQrTechnique()
    res = tech.apply(english_login_html, sample_url, tech.get_default_options())
    assert "<noscript>" in res.modified_html
    assert res.change_log[0].details["noscript_fallback"] is True


@pytest.mark.skipif(not qrcode_available, reason="qrcode lib not installed")
def test_t19_persian_scan_label(persian_login_html, sample_url):
    tech = BlobQrTechnique()
    res = tech.apply(persian_login_html, sample_url, tech.get_default_options())
    assert "برای ادامه اسکن کنید" in res.modified_html
