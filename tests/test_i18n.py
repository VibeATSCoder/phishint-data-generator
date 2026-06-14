"""Unit tests for the locale detector + message catalog."""
import pytest

from app.utils.i18n import MESSAGES, detect_language, t


def test_detects_persian_from_html_lang_attr():
    assert detect_language('<html lang="fa-IR"><body>...</body></html>') == "fa"
    assert detect_language("<html lang=\"fa\"><body></body></html>") == "fa"


def test_detects_english_from_html_lang_attr():
    assert detect_language('<html lang="en-US"><body>hi</body></html>') == "en"


def test_detects_persian_from_body_text_when_lang_absent():
    html = (
        "<html><body>"
        "<p>این یک متن فارسی نمونه است که برای تشخیص خودکار زبان استفاده می‌شود.</p>"
        "</body></html>"
    )
    assert detect_language(html) == "fa"


def test_detects_english_from_body_text_when_lang_absent():
    html = "<html><body><p>This is a sample English paragraph used to detect language.</p></body></html>"
    assert detect_language(html) == "en"


def test_empty_html_defaults_to_persian():
    assert detect_language("") == "fa"
    assert detect_language("<html><body></body></html>") == "fa"


def test_t_renders_persian_template_with_vars():
    out = t("captcha.cf.checking", "fa", domain="example.com")
    assert "example.com" in out
    assert "بررسی" in out


def test_t_falls_back_to_english_when_key_missing():
    MESSAGES.setdefault("en", {})["__test_only__"] = "english fallback"
    out = t("__test_only__", "fa")
    assert out == "english fallback"
    del MESSAGES["en"]["__test_only__"]


def test_t_returns_message_id_when_missing_everywhere():
    out = t("__definitely_not_a_real_key__", "fa")
    assert out == "__definitely_not_a_real_key__"


def test_catalog_keys_match_across_languages():
    """Every key in `fa` should also exist in `en` (and vice-versa) so a
    language switch never silently drops a string."""
    fa_keys = set(MESSAGES["fa"].keys())
    en_keys = set(MESSAGES["en"].keys())
    assert fa_keys == en_keys, (
        f"key drift: only-fa={fa_keys - en_keys} only-en={en_keys - fa_keys}"
    )
