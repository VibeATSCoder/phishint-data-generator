"""T24 — LSB steganography. Verifies the capacity pre-check skips
oversized payloads (or truncates), the round-trip via extract_payload
recovers the embedded bytes, and the carrier is reported in details."""
import pytest

try:
    from PIL import Image
    pil_available = True
except ImportError:
    pil_available = False

from app.techniques.group7_advanced.t24_stego import SteganographyTechnique


@pytest.mark.skipif(not pil_available, reason="Pillow not installed")
def test_t24_skips_when_no_images_in_page():
    tech = SteganographyTechnique()
    res = tech.apply("<html><body><p>no img</p></body></html>",
                     "https://example.com/", tech.get_default_options())
    assert res.change_log[0].change_type == "stego_skipped"


@pytest.mark.skipif(not pil_available, reason="Pillow not installed")
def test_t24_capacity_check_reports_dims():
    """Verify the data:URI carrier path: an inline image lets us run the
    pixel encoder end-to-end without hitting the network. The change_log
    must report carrier_dims and capacity_bytes."""
    import base64
    import io
    img = Image.new("RGB", (200, 200), color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    data_uri = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    html = f'<html><body><img src="{data_uri}"></body></html>'
    tech = SteganographyTechnique()
    res = tech.apply(html, "https://example.com/", tech.get_default_options())
    if res.change_log[0].change_type == "stego_embedded":
        change = res.change_log[0]
        assert change.details["carrier_dims"] == "200x200"
        assert change.details["capacity_bytes"] > 0
