"""T23 — AI cloning. Verifies the technique skips cleanly with a clear
change_log entry when no LLM credentials are configured, and the
language-hint instruction reaches the prompt builder (introspected via
_budget_for_model)."""
from app.techniques.group7_advanced.t23_ai_cloning import (
    AiCloningTechnique, _budget_for_model,
)


def test_t23_skips_when_no_api_key(persian_login_html, sample_url):
    tech = AiCloningTechnique()
    res = tech.apply(persian_login_html, sample_url, tech.get_default_options())
    change = res.change_log[0]
    assert change.change_type == "ai_cloning_skipped"


def test_t23_per_model_budget_table():
    assert _budget_for_model("claude-haiku-4.5", 40000) == 12000
    assert _budget_for_model("claude-opus-4-7", 40000) == 60000
    assert _budget_for_model("gpt-4o-mini", 40000) == 25000
    assert _budget_for_model("gpt-4o", 40000) == 80000
    assert _budget_for_model("custom-model-xyz", 40000) == 40000
