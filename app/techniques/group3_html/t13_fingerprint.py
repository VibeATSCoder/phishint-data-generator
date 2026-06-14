from __future__ import annotations

import json
from typing import Any, ClassVar

from app.techniques.base import (
    ApplyResult, BaseTechnique, Category, OptionSpec, Requirement, TechniqueGroup,
)
from app.utils.html_utils import inject_script_into_head, parse_html, serialize_html


_FINGERPRINT_TEMPLATE_V2 = """\
(function(){{
  function _fp(){{
    var score = 0;
    var checks = [];
    // 1. navigator.webdriver — set true by Selenium/Playwright headless flows
    try{{ if(navigator.webdriver){{ score -= 5; checks.push('webdriver'); }} }}catch(e){{}}
    // 2. plugins length zero (classic headless tell)
    try{{ if(!navigator.plugins || navigator.plugins.length === 0){{ score -= 2; checks.push('plugins0'); }} }}catch(e){{}}
    // 3. languages length zero
    try{{ if(!navigator.languages || navigator.languages.length === 0){{ score -= 2; checks.push('langs0'); }} }}catch(e){{}}
    // 4. canvas entropy
    try{{
      var c = document.createElement('canvas'); var ctx = c.getContext('2d');
      ctx.textBaseline = 'top'; ctx.font = '14px Arial'; ctx.fillText('fp_test', 2, 2);
      if (c.toDataURL().length > 100) {{ score += 1; checks.push('canvas'); }}
    }}catch(e){{}}
    // 5. WebGL renderer
    try{{
      var gl = document.createElement('canvas').getContext('webgl');
      if (gl && gl.getParameter(gl.RENDERER)) {{ score += 1; checks.push('webgl'); }}
    }}catch(e){{}}
    // 6. Screen resolution
    if (window.screen.width > 1024 && window.screen.height > 768) {{ score += 1; checks.push('screen'); }}
    // 7. Mouse / keyboard / touch — any interaction is a strong signal
    var interacted = false;
    function _mark(){{ interacted = true; }}
    document.addEventListener('mousemove', _mark, {{once:true,passive:true}});
    document.addEventListener('keydown', _mark, {{once:true,passive:true}});
    document.addEventListener('touchstart', _mark, {{once:true,passive:true}});
    setTimeout(function(){{
      if (score < 2 || !interacted) {{
        var botUrl = '{bot_redirect_url}';
        if (botUrl) window.location.href = botUrl;
        else document.body.innerHTML = '';
      }}
    }}, {check_delay_ms});
  }}
  _fp();
}})();"""


class AntiBotFingerprintTechnique(BaseTechnique):
    """
    T13 — Conditional rendering + Anti-bot / Fingerprint evasion.

    Injects a JavaScript fingerprinting script that detects bots/crawlers
    via canvas entropy, WebGL presence, screen resolution, and mouse movement.
    If a bot is detected, the page either blanks or redirects to a safe URL.
    """

    TECHNIQUE_ID: ClassVar[int] = 13
    TECHNIQUE_NAME: ClassVar[str] = "Anti-bot Fingerprinting & Conditional Rendering"
    GROUP: ClassVar[TechniqueGroup] = TechniqueGroup.HTML_DOM_JS
    CATEGORIES: ClassVar[list[Category]] = [Category.CREDENTIAL_THEFT, Category.MALWARE_DISTRIBUTION]
    REQUIREMENTS: ClassVar[list[Requirement]] = [Requirement.HAS_HTML]
    DESCRIPTION: ClassVar[str] = (
        "Injects JS that fingerprints the browser (canvas, WebGL, mouse movement). "
        "Bots and crawlers fail the check and see an empty or redirected page; "
        "real users see the phishing content."
    )
    OPTION_SPECS: ClassVar[list[OptionSpec]] = [
        OptionSpec(
            name="fingerprint_methods",
            description="Detection signals to use: canvas, webgl, screen, mouse",
            type=list,
            default=["canvas", "webgl", "screen", "mouse"],
        ),
        OptionSpec(
            name="bot_redirect_url",
            description="URL to redirect bots to (empty = blank the page)",
            type=str,
            default="",
        ),
        OptionSpec(
            name="check_delay_ms",
            description="Milliseconds to wait before applying the bot verdict",
            type=int,
            default=2500,
            min_value=500,
            max_value=10000,
        ),
    ]

    def apply(
        self,
        html: str,
        url: str,
        options: dict[str, Any],
        screenshot_bytes: bytes | None = None,
    ) -> ApplyResult:
        bot_redirect_url: str = options.get("bot_redirect_url", "")
        check_delay_ms: int = int(options.get("check_delay_ms", 2500))

        soup = parse_html(html)

        js = _FINGERPRINT_TEMPLATE_V2.format(
            bot_redirect_url=bot_redirect_url or "",
            check_delay_ms=check_delay_ms,
        )

        inject_script_into_head(soup, js)

        checks_emitted = [
            "webdriver", "plugins0", "langs0", "canvas",
            "webgl", "screen", "mouse_kbd_touch",
        ]
        self.log("info", "fingerprint_applied",
                 checks=",".join(checks_emitted), delay_ms=check_delay_ms,
                 redirect=bool(bot_redirect_url))

        return ApplyResult(
            modified_html=serialize_html(soup),
            modified_url=None,
            extra_files={},
            change_log=[
                self._make_change(
                    "antibot_fingerprint_injected",
                    f"Injected fingerprinting script; "
                    f"bot redirect={'set' if bot_redirect_url else 'blank page'}; "
                    f"check delay={check_delay_ms}ms",
                    details={
                        "checks_emitted": checks_emitted,
                        "redirect_on_fail": bot_redirect_url or "blank_body",
                        "check_delay_ms": check_delay_ms,
                    },
                )
            ],
        )

    def evaluate(self, html, url, change_log, extra_files):
        from app.techniques.base import EvaluationResult
        signals, issues = [], []

        has_webdriver = html and "navigator.webdriver" in html
        if has_webdriver:
            signals.append("HTML checks navigator.webdriver (Selenium/Playwright detection)")
        else:
            issues.append("HTML missing navigator.webdriver check")

        has_canvas = html and "canvas" in html and "getContext" in html
        if has_canvas:
            signals.append("HTML has canvas fingerprinting code")
        else:
            issues.append("HTML missing canvas fingerprinting")

        has_timeout = html and "setTimeout" in html
        if has_timeout:
            signals.append("HTML has setTimeout() — delayed bot verdict")
        else:
            issues.append("HTML missing setTimeout()")

        has_deny = html and ("document.body.innerHTML" in html or "window.location.href" in html)
        if has_deny:
            signals.append("HTML has body-clear or redirect on bot detection")
        else:
            issues.append("HTML missing bot-detection response (body clear or redirect)")

        entry = next((e for e in change_log if e.change_type == "antibot_fingerprint_injected"), None)
        if entry:
            checks = entry.details.get("checks_emitted", [])
            signals.append(f"change_log: {len(checks)} fingerprint check(s): {checks}")
        else:
            issues.append("No antibot_fingerprint_injected in change_log")

        passed = bool(has_webdriver and has_canvas and has_timeout)
        return EvaluationResult(
            passed=passed,
            score=self._eval_score(signals, issues),
            signals=signals,
            issues=issues,
            details={"has_webdriver_check": has_webdriver, "has_canvas": has_canvas, "has_timeout": has_timeout},
        )
