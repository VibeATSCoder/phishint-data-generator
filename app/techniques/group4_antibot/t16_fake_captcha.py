from __future__ import annotations

import secrets
from typing import Any, ClassVar

from bs4 import BeautifulSoup

from app.techniques.base import (
    ApplyResult, BaseTechnique, Category, OptionSpec, Requirement, TechniqueGroup,
)
from app.utils.html_utils import inject_style_into_head, parse_html, serialize_html
from app.utils.url_utils import parse_url
from app.utils.js_templates import (
    FAKE_CLOUDFLARE_CSS, FAKE_CLOUDFLARE_HTML,
    FAKE_RECAPTCHA_CSS, FAKE_RECAPTCHA_HTML,
)


class FakeCaptchaTechnique(BaseTechnique):
    """
    T16 — Fake Cloudflare Turnstile / reCAPTCHA overlay.

    Injects a realistic-looking fake CAPTCHA verification screen that
    disappears after a short delay, revealing the phishing page beneath.
    Crawlers that don't interact with the overlay never see the real content.
    """

    TECHNIQUE_ID: ClassVar[int] = 16
    TECHNIQUE_NAME: ClassVar[str] = "Fake CAPTCHA Overlay (Cloudflare / reCAPTCHA)"
    GROUP: ClassVar[TechniqueGroup] = TechniqueGroup.ANTIBOT_CLOAKING
    CATEGORIES: ClassVar[list[Category]] = [Category.CREDENTIAL_THEFT]
    REQUIREMENTS: ClassVar[list[Requirement]] = [Requirement.HAS_HTML]
    DESCRIPTION: ClassVar[str] = (
        "Overlays a pixel-perfect fake Cloudflare Turnstile or reCAPTCHA "
        "verification screen. Crawlers cannot interact with it; real users "
        "click through and reach the phishing content."
    )
    _VALID_VENDORS: ClassVar[set[str]] = {
        "cloudflare", "recaptcha", "turnstile", "hcaptcha",
    }

    OPTION_SPECS: ClassVar[list[OptionSpec]] = [
        OptionSpec(
            name="captcha_type",
            description="Vendor: 'cloudflare', 'recaptcha', 'turnstile', or 'hcaptcha'",
            type=str,
            default="cloudflare",
        ),
        OptionSpec(
            name="reveal_delay_ms",
            description="Milliseconds before the overlay starts to fade",
            type=int,
            default=1500,
            min_value=0,
            max_value=10000,
        ),
        OptionSpec(
            name="scroll_lock",
            description="Lock the page scroll behind the overlay",
            type=bool,
            default=True,
        ),
    ]

    def apply(
        self,
        html: str,
        url: str,
        options: dict[str, Any],
        screenshot_bytes: bytes | None = None,
    ) -> ApplyResult:
        captcha_type: str = options.get("captcha_type", "cloudflare")
        if captcha_type not in self._VALID_VENDORS:
            self.log("warning", "captcha_vendor_fallback",
                     requested=captcha_type, fallback="cloudflare")
            captcha_type = "cloudflare"

        reveal_delay_ms: int = int(options.get("reveal_delay_ms", 1500))
        scroll_lock: bool = bool(options.get("scroll_lock", True))

        parsed_url, _ = parse_url(url)
        domain = parsed_url.netloc or "example.com"

        soup = parse_html(html)

        from app.utils.i18n import t as _t
        lang = self._detect_lang(html, url)
        dir_attr = "rtl" if lang == "fa" else "ltr"

        if captcha_type in ("cloudflare", "turnstile"):
            css = FAKE_CLOUDFLARE_CSS
            ray_id = secrets.token_hex(8).upper()
            overlay_html = FAKE_CLOUDFLARE_HTML.format(
                dir_attr=dir_attr,
                brand=_t("captcha.cf.brand", lang),
                headline=_t("captcha.cf.headline", lang),
                checking=_t("captcha.cf.checking", lang, domain=domain),
                subtext=_t("captcha.cf.subtext", lang),
                footer_left=_t("captcha.cf.footer_left", lang),
                footer_right=_t("captcha.cf.footer_right", lang, ray_id=ray_id),
                success_js=_t("captcha.cf.success", lang),
                redirecting_js=_t("captcha.cf.redirecting", lang),
            )
        else:
            css = FAKE_RECAPTCHA_CSS
            overlay_html = FAKE_RECAPTCHA_HTML.format(
                dir_attr=dir_attr,
                title=_t("captcha.rc.title", lang),
                checkbox_label=_t("captcha.rc.checkbox", lang),
                brand=_t("captcha.rc.brand", lang),
            )

        css_inset = (
            "#__cf_overlay__,#__rc_overlay__"
            "{position:fixed!important;inset:0!important;z-index:2147483647!important;}"
        )
        if scroll_lock:
            css_inset += "html,body{overflow:hidden!important;}"

        inject_style_into_head(soup, css)
        inject_style_into_head(soup, css_inset)

        body = soup.find("body")
        if not body:
            body = soup.new_tag("body")
            html_tag = soup.find("html")
            if html_tag:
                html_tag.insert(0, body)
            else:
                soup.insert(0, body)

        frag = BeautifulSoup(overlay_html, "lxml")
        overlay_div = frag.find("div")
        if overlay_div:
            overlay_div["data-reveal-delay"] = str(reveal_delay_ms)
            body.insert(0, overlay_div)

        inline_script = frag.find("script")
        if inline_script:
            body.append(inline_script)

        if reveal_delay_ms > 0:
            preamble = soup.new_tag("script")
            preamble.string = (
                "(function(){var o=document.querySelector('[data-reveal-delay]');"
                "if(o){o.style.visibility='visible';o.style.opacity='1';}})();"
            )
            body.insert(0, preamble)

        self.log("info", "fake_captcha_applied",
                 vendor=captcha_type, domain=domain,
                 reveal_ms=reveal_delay_ms, scroll_lock=scroll_lock)

        return ApplyResult(
            modified_html=serialize_html(soup),
            modified_url=None,
            extra_files={},
            change_log=[
                self._make_change(
                    "fake_captcha_injected",
                    f"Injected fake {captcha_type} overlay for domain={domain}",
                    details={
                        "vendor": captcha_type,
                        "reveal_delay_ms": reveal_delay_ms,
                        "scroll_locked": scroll_lock,
                        "domain": domain,
                        "lang": lang,
                    },
                )
            ],
        )

    def evaluate(self, html, url, change_log, extra_files):
        from app.techniques.base import EvaluationResult
        signals, issues = [], []

        has_cf_overlay = html and "__cf_overlay__" in html
        has_rc_overlay = html and "__rc_overlay__" in html
        if has_cf_overlay or has_rc_overlay:
            overlay_id = "__cf_overlay__" if has_cf_overlay else "__rc_overlay__"
            signals.append(f"HTML has CAPTCHA overlay div ({overlay_id})")
        else:
            issues.append("HTML missing CAPTCHA overlay div (__cf_overlay__ or __rc_overlay__)")

        has_fixed = html and "position:fixed" in html
        if has_fixed:
            signals.append("Overlay CSS uses position:fixed (full-screen block)")
        else:
            issues.append("HTML missing position:fixed overlay CSS")

        has_timer = html and "setTimeout" in html
        if has_timer:
            signals.append("HTML has setTimeout() — timed reveal after delay")
        else:
            issues.append("HTML missing setTimeout() delay timer")

        entry = next((e for e in change_log if e.change_type == "fake_captcha_injected"), None)
        if entry:
            vendor = entry.details.get("vendor", "")
            delay = entry.details.get("reveal_delay_ms", 0)
            signals.append(f"change_log: vendor={vendor!r} reveal_delay={delay}ms")
        else:
            issues.append("No fake_captcha_injected in change_log")

        passed = bool((has_cf_overlay or has_rc_overlay) and has_fixed)
        return EvaluationResult(
            passed=passed,
            score=self._eval_score(signals, issues),
            signals=signals,
            issues=issues,
            details={"has_cf_overlay": has_cf_overlay, "has_rc_overlay": has_rc_overlay, "has_timer": has_timer},
        )
