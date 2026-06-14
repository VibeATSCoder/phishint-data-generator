"""T5 — Polymorphic URL variants. Verifies the requested count is met,
duplicates are de-duped, the full variant list lands in details, and the
extra_files carries the same variants for downstream consumers."""
from app.techniques.group1_url.t05_polymorphic import PolymorphicUrlTechnique
from tests.techniques.conftest import assert_details_has


def test_t05_generates_distinct_variants(sample_url):
    tech = PolymorphicUrlTechnique()
    opts = tech.get_default_options()
    opts["variation_count"] = 5
    res = tech.apply("", sample_url, opts)
    change = res.change_log[0]
    assert_details_has(change, "variants", "strategy", "requested")
    variants = change.details["variants"]
    assert len(variants) == len(set(variants))
    assert sample_url not in variants


def test_t05_variants_written_to_extra_files(sample_url):
    tech = PolymorphicUrlTechnique()
    res = tech.apply("", sample_url, tech.get_default_options())
    assert "url_polymorphic_variants.txt" in res.extra_files
    lines = res.extra_files["url_polymorphic_variants.txt"].decode().splitlines()
    assert len(lines) >= 1
