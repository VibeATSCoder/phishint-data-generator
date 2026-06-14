from __future__ import annotations

from typing import Any, ClassVar

from app.techniques.base import (
    ApplyResult, BaseTechnique, Category, OptionSpec, Requirement, TechniqueGroup,
)
from app.utils.html_utils import parse_html, serialize_html
from app.utils.url_utils import parse_url


class MfaFatigueTechnique(BaseTechnique):
    """
    T21 — MFA fatigue / push-bombing simulation page.

    Injects JavaScript into the page that repeatedly shows MFA push
    notification simulation dialogs at configurable intervals, attempting
    to wear down the victim into approving.
    """

    TECHNIQUE_ID: ClassVar[int] = 21
    TECHNIQUE_NAME: ClassVar[str] = "MFA Fatigue / Push-Bombing Simulation"
    GROUP: ClassVar[TechniqueGroup] = TechniqueGroup.MFA_AUTH_BYPASS
    CATEGORIES: ClassVar[list[Category]] = [Category.CREDENTIAL_THEFT]
    REQUIREMENTS: ClassVar[list[Requirement]] = [Requirement.HAS_INPUT_FIELDS]
    DESCRIPTION: ClassVar[str] = (
        "Injects a JS-powered MFA push notification simulation that repeatedly "
        "prompts users to approve a login request. Repeated prompts ('push bombing') "
        "wear victims into accidentally approving."
    )
    _DEVICE_TEMPLATES: ClassVar[list[dict]] = [
        {"device": "iPhone 15 Pro", "location": "Tehran, Iran", "ip": "5.232.18.44"},
        {"device": "Samsung Galaxy S24", "location": "Dubai, UAE", "ip": "94.200.12.6"},
        {"device": "Pixel 8", "location": "Istanbul, Turkey", "ip": "78.180.7.221"},
        {"device": "MacBook Pro", "location": "London, UK", "ip": "82.13.4.91"},
    ]

    OPTION_SPECS: ClassVar[list[OptionSpec]] = [
        OptionSpec(
            name="prompt_type",
            description="Type of MFA simulation: 'push' or 'otp'",
            type=str,
            default="push",
        ),
        OptionSpec(
            name="prompt_interval_ms",
            description="Milliseconds between repeated prompts",
            type=int,
            default=5000,
            min_value=500,
            max_value=60000,
        ),
        OptionSpec(
            name="max_prompts",
            description="Maximum number of prompt repetitions",
            type=int,
            default=5,
            min_value=1,
            max_value=20,
        ),
    ]

    def apply(
        self,
        html: str,
        url: str,
        options: dict[str, Any],
        screenshot_bytes: bytes | None = None,
    ) -> ApplyResult:
        import random
        prompt_type: str = options.get("prompt_type", "push")
        interval_ms: int = int(options.get("prompt_interval_ms", 5000))
        max_prompts: int = int(options.get("max_prompts", 5))

        device_ctx = random.choice(self._DEVICE_TEMPLATES)
        parsed, _ = parse_url(url)
        domain = parsed.netloc or "example.com"
        lang = self._detect_lang(html, url)

        soup = parse_html(html)
        head = soup.find("head")
        if not head:
            head = soup.new_tag("head")
            html_tag = soup.find("html")
            if html_tag:
                html_tag.insert(0, head)

        style = soup.new_tag("style")
        style.string = self._get_css()
        head.append(style)

        body = soup.find("body")
        if not body:
            body = soup.new_tag("body")
            html_tag = soup.find("html")
            if html_tag:
                html_tag.append(body)
            else:
                soup.append(body)

        from bs4 import BeautifulSoup
        overlay = BeautifulSoup(
            self._get_overlay_html(domain, prompt_type, device_ctx, lang), "lxml"
        )
        overlay_div = overlay.find("div")
        if overlay_div:
            body.append(overlay_div)

        script = soup.new_tag("script")
        script.string = self._get_js(prompt_type, interval_ms, max_prompts, domain)
        body.append(script)

        self.log("info", "mfa_fatigue_applied",
                 type=prompt_type, interval=interval_ms,
                 max=max_prompts, device=device_ctx["device"])

        return ApplyResult(
            modified_html=serialize_html(soup),
            modified_url=None,
            extra_files={},
            change_log=[
                self._make_change(
                    "mfa_fatigue_injected",
                    f"Injected {prompt_type} MFA fatigue simulation: "
                    f"interval={interval_ms}ms, max={max_prompts} prompts",
                    details={
                        "prompt_type": prompt_type,
                        "interval_ms": interval_ms,
                        "max_prompts": max_prompts,
                        "device_name": device_ctx["device"],
                        "device_location": device_ctx["location"],
                        "spoofed_ip": device_ctx["ip"],
                        "lang": lang,
                    },
                )
            ],
        )

    def evaluate(self, html, url, change_log, extra_files):
        from app.techniques.base import EvaluationResult
        signals, issues = [], []

        has_overlay = html and "__mfa_overlay__" in html
        if has_overlay:
            signals.append("HTML has #__mfa_overlay__ div")
        else:
            issues.append("HTML missing #__mfa_overlay__ div")

        has_timer = html and ("setInterval" in html or "setTimeout" in html)
        if has_timer:
            signals.append("HTML has setInterval/setTimeout (push-bombing timer)")
        else:
            issues.append("HTML missing interval/timeout timer for repeated prompts")

        has_approve = html and "__mfa_btn_approve__" in html
        has_deny = html and "__mfa_btn_deny__" in html
        if has_approve and has_deny:
            signals.append("HTML has approve/deny buttons")
        else:
            issues.append("HTML missing MFA approve/deny buttons")

        has_success_div = html and "__mfa_success_msg__" in html
        if has_success_div:
            signals.append("MFA success message div present (__mfa_success_msg__)")
        else:
            issues.append("MFA success message div missing (__mfa_success_msg__)")

        entry = next((e for e in change_log if e.change_type == "mfa_fatigue_injected"), None)
        if entry:
            interval = entry.details.get("interval_ms", 0)
            max_p = entry.details.get("max_prompts", 0)
            signals.append(f"change_log: interval={interval}ms max_prompts={max_p}")
        else:
            issues.append("No mfa_fatigue_injected in change_log")

        passed = bool(has_overlay and has_timer and has_approve)
        return EvaluationResult(
            passed=passed,
            score=self._eval_score(signals, issues),
            signals=signals,
            issues=issues,
            details={"has_overlay": has_overlay, "has_timer": has_timer, "has_buttons": has_approve and has_deny},
        )

    def _get_css(self) -> str:
        return """
#__mfa_overlay__{position:fixed;top:0;left:0;width:100%;height:100%;
background:rgba(0,0,0,.6);z-index:99999;display:none;
align-items:center;justify-content:center;transition:opacity 0.4s ease;}
#__mfa_box__{background:#fff;border-radius:12px;padding:32px;max-width:340px;
width:90%;text-align:center;box-shadow:0 4px 24px rgba(0,0,0,.3);}
#__mfa_icon__{font-size:48px;margin-bottom:12px;}
#__mfa_title__{font-size:20px;font-weight:600;margin-bottom:8px;}
#__mfa_msg__{font-size:14px;color:#555;margin-bottom:24px;}
#__mfa_btn_approve__{background:#1a73e8;color:#fff;border:none;
border-radius:4px;padding:12px 24px;font-size:16px;cursor:pointer;width:100%;margin-bottom:8px;}
#__mfa_btn_deny__{background:#f1f3f4;color:#333;border:none;
border-radius:4px;padding:12px 24px;font-size:16px;cursor:pointer;width:100%;}
#__mfa_success__{display:none;text-align:center;padding:16px 0;}
#__mfa_success_icon__{font-size:52px;color:#1a73e8;margin-bottom:10px;}
#__mfa_success_msg__{font-size:16px;font-weight:600;color:#202124;}
#__mfa_success_sub__{font-size:13px;color:#5f6368;margin-top:6px;}
"""

    def _get_overlay_html(
        self, domain: str, prompt_type: str, device_ctx: dict, lang: str = "fa",
    ) -> str:
        from app.utils.i18n import t as _t
        dir_attr = "rtl" if lang == "fa" else "ltr"
        ctx_line = (
            f'<div style="font-size:12px;color:#888;margin-top:6px;">'
            f'{_t("mfa.context.device", lang, device=device_ctx["device"])}<br>'
            f'{_t("mfa.context.location", lang, location=device_ctx["location"], ip=device_ctx["ip"])}<br>'
            f'<span style="color:#c12;">{_t("mfa.context.threat", lang)}</span></div>'
        )
        success_block = f"""
  <div id="__mfa_success__">
    <div id="__mfa_success_icon__">&#10003;</div>
    <div id="__mfa_success_msg__">{_t("mfa.success.msg", lang)}</div>
    <div id="__mfa_success_sub__">{_t("mfa.success.sub", lang)}</div>
  </div>"""
        if prompt_type == "otp":
            return f"""<div id="__mfa_overlay__" dir="{dir_attr}" style="display:none;">
  <div id="__mfa_box__">
    <div id="__mfa_icon__">&#128274;</div>
    <div id="__mfa_title__">{_t("mfa.otp.title", lang)}</div>
    <div id="__mfa_msg__">{_t("mfa.otp.instructions", lang, domain=domain)}{ctx_line}</div>
    <input type="text" id="__mfa_otp__" placeholder="{_t("form.placeholder.otp", lang)}"
           style="width:100%;padding:10px;font-size:18px;text-align:center;
                  border:1px solid #dadce0;border-radius:4px;margin-bottom:16px;">
    <button id="__mfa_btn_approve__" onclick="__mfaApprove()">{_t("form.button.verify", lang)}</button>
    <button id="__mfa_btn_deny__" onclick="__mfaDeny()">{_t("form.button.cancel", lang)}</button>
    {success_block}
  </div>
</div>"""
        return f"""<div id="__mfa_overlay__" dir="{dir_attr}" style="display:none;">
  <div id="__mfa_box__">
    <div id="__mfa_icon__">&#128241;</div>
    <div id="__mfa_title__">{_t("mfa.push.title", lang)}</div>
    <div id="__mfa_msg__">{_t("mfa.push.instructions", lang, domain=domain)}<br>
      <small>{_t("mfa.push.disclaimer", lang)}</small>{ctx_line}</div>
    <button id="__mfa_btn_approve__" onclick="__mfaApprove()">{_t("form.button.approve", lang)}</button>
    <button id="__mfa_btn_deny__" onclick="__mfaDeny()">{_t("form.button.deny", lang)}</button>
    {success_block}
  </div>
</div>"""

    def _get_js(
        self, prompt_type: str, interval_ms: int, max_prompts: int, domain: str
    ) -> str:
        return f"""
var __mfaCount = 0;
var __mfaMax = {max_prompts};
var __mfaInterval = {interval_ms};
var __mfaTimer = null;

function __mfaShow() {{
  if (__mfaCount >= __mfaMax) {{
    if (__mfaTimer) {{ clearInterval(__mfaTimer); __mfaTimer = null; }}
    return;
  }}
  __mfaCount++;
  var ov = document.getElementById('__mfa_overlay__');
  var sc = document.getElementById('__mfa_success__');
  var ic = document.getElementById('__mfa_icon__');
  var ti = document.getElementById('__mfa_title__');
  var mg = document.getElementById('__mfa_msg__');
  var ba = document.getElementById('__mfa_btn_approve__');
  var bd = document.getElementById('__mfa_btn_deny__');
  if (sc) sc.style.display = 'none';
  if (ic) ic.style.display = 'block';
  if (ti) ti.style.display = 'block';
  if (mg) mg.style.display = 'block';
  if (ba) ba.style.display = 'block';
  if (bd) bd.style.display = 'block';
  if (ov) {{ ov.style.opacity = '1'; ov.style.display = 'flex'; }}
}}

function __mfaHide(ov) {{
  if (!ov) return;
  ov.style.opacity = '0';
  setTimeout(function() {{ ov.style.display = 'none'; }}, 460);
}}

function __mfaApprove() {{
  if (__mfaTimer) {{ clearInterval(__mfaTimer); __mfaTimer = null; }}
  var ov = document.getElementById('__mfa_overlay__');
  var sc = document.getElementById('__mfa_success__');
  var ic = document.getElementById('__mfa_icon__');
  var ti = document.getElementById('__mfa_title__');
  var mg = document.getElementById('__mfa_msg__');
  var ba = document.getElementById('__mfa_btn_approve__');
  var bd = document.getElementById('__mfa_btn_deny__');
  if (ic) ic.style.display = 'none';
  if (ti) ti.style.display = 'none';
  if (mg) mg.style.display = 'none';
  if (ba) ba.style.display = 'none';
  if (bd) bd.style.display = 'none';
  if (sc) sc.style.display = 'block';
  setTimeout(function() {{ __mfaHide(ov); }}, 1600);
}}

function __mfaDeny() {{
  var ov = document.getElementById('__mfa_overlay__');
  __mfaHide(ov);
  if (__mfaCount < __mfaMax) {{
    setTimeout(__mfaShow, __mfaInterval);
  }}
}}

setTimeout(function() {{
  __mfaShow();
  __mfaTimer = setInterval(function() {{
    if (__mfaCount >= __mfaMax) {{
      clearInterval(__mfaTimer); __mfaTimer = null; return;
    }}
    var ov = document.getElementById('__mfa_overlay__');
    if (ov && ov.style.display === 'none') {{ __mfaShow(); }}
  }}, __mfaInterval);
}}, 2000);
"""
