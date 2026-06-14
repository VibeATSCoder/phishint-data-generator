"""T4 — Long URL: append N random query parameters. Verifies the URL
grows past the original length, the parameter count is reported, the
hard cap is enforced, and URL fragments survive."""
from app.techniques.group1_url.t04_long_url import LongUrlTechnique
from tests.techniques.conftest import assert_details_has


def test_t04_appends_params(sample_url):
    tech = LongUrlTechnique()
    res = tech.apply("", sample_url, tech.get_default_options())
    assert res.modified_url and len(res.modified_url) > len(sample_url)
    change = res.change_log[0]
    assert_details_has(change, "params_added", "final_url_len")
    assert change.details["params_added"] >= 1


def test_t04_preserves_fragment():
    tech = LongUrlTechnique()
    res = tech.apply("", "https://example.com/page#section", tech.get_default_options())
    assert res.modified_url is not None
    assert "#section" in res.modified_url
    assert res.change_log[0].details["fragment_preserved"] is True


def test_t04_clamps_runaway_param_count():
    tech = LongUrlTechnique()
    opts = tech.get_default_options()
    opts["param_count"] = 50
    opts["param_length"] = 128
    res = tech.apply("", "https://example.com/", opts)
    assert res.modified_url is not None
    assert len(res.modified_url) <= LongUrlTechnique._MAX_TOTAL_URL_LEN
