"""T9 — SVG smuggling. Verifies inline <svg> elements receive the encoded
JS payload, unbalanced payloads are rejected, and the carrier source is
reported in details."""
from app.techniques.group2_visual.t09_svg_smuggling import SvgSmugglingTechnique
from tests.techniques.conftest import assert_details_has


def test_t09_injects_into_existing_svg(inline_svg_html, sample_url):
    tech = SvgSmugglingTechnique()
    res = tech.apply(inline_svg_html, sample_url, tech.get_default_options())
    assert res.modified_html is not None
    assert "<script" in res.modified_html
    change = res.change_log[0]
    assert_details_has(change, "carrier", "payload_bytes", "encoding")


def test_t09_rejects_unbalanced_payload():
    tech = SvgSmugglingTechnique()
    opts = tech.get_default_options()
    opts["safe_mode"] = False
    opts["payload_js"] = "alert('unterminated"
    res = tech.apply("<html><body><svg/></body></html>", "https://example.com/", opts)
    assert res.modified_html is None
    assert res.change_log[0].details.get("reason") == "payload_unbalanced"


def test_t09_creates_hidden_svg_when_none_inline():
    tech = SvgSmugglingTechnique()
    opts = tech.get_default_options()
    opts["inline_img_svgs"] = False
    res = tech.apply("<html><body><p>no svg</p></body></html>", "https://example.com/", opts)
    assert res.modified_html is not None
    assert "<svg" in res.modified_html
    assert res.change_log[0].details["carrier"] == "hidden_1x1"
