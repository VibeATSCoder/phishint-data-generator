from __future__ import annotations

from typing import Any, ClassVar

from bs4 import BeautifulSoup

from app.techniques.base import (
    ApplyResult, BaseTechnique, Category, OptionSpec, Requirement, TechniqueGroup,
)
import random

from app.utils.html_utils import parse_html, safe_append_fragment, serialize_html


class CssHidingTechnique(BaseTechnique):
    """
    T12 — CSS hiding (display:none, off-viewport, opacity:0).

    Injects hidden elements (inputs, tracking pixels, honeypot fields) using
    CSS techniques that are invisible to users but count toward ML feature
    vectors, or hides the real credential-harvest form from static scanners.
    """

    TECHNIQUE_ID: ClassVar[int] = 12
    TECHNIQUE_NAME: ClassVar[str] = "CSS Hiding (Off-Viewport / Opacity 0)"
    GROUP: ClassVar[TechniqueGroup] = TechniqueGroup.HTML_DOM_JS
    CATEGORIES: ClassVar[list[Category]] = [Category.CREDENTIAL_THEFT]
    REQUIREMENTS: ClassVar[list[Requirement]] = [Requirement.HAS_HTML]
    DESCRIPTION: ClassVar[str] = (
        "Injects a hidden honeypot form and several off-viewport elements "
        "using display:none, opacity:0, and position:absolute with negative "
        "coordinates. Also adds a hidden class to conceal the real form from "
        "simple static scanners."
    )
    OPTION_SPECS: ClassVar[list[OptionSpec]] = [
        OptionSpec(
            name="honeypot_variants",
            description="Number of distinct honeypot field shapes to inject",
            type=int,
            default=2,
            min_value=1,
            max_value=6,
        ),
    ]

    _HONEYPOT_SHAPES: ClassVar[list[dict]] = [
        {"user": "username", "pass": "password"},
        {"user": "email", "pass": "passwd"},
        {"user": "user_email", "pass": "pass"},
        {"user": "full_name", "pass": "user_password"},
        {"user": "login", "pass": "secret"},
        {"user": "account", "pass": "key"},
    ]

    def apply(
        self,
        html: str,
        url: str,
        options: dict[str, Any],
        screenshot_bytes: bytes | None = None,
    ) -> ApplyResult:
        n_variants: int = max(1, int(options.get("honeypot_variants", 2)))
        chosen_shapes = random.sample(
            self._HONEYPOT_SHAPES, min(n_variants, len(self._HONEYPOT_SHAPES))
        )

        soup = parse_html(html)
        field_names: list[str] = []

        honeypot_fragments: list[str] = []
        for i, shape in enumerate(chosen_shapes):
            field_names.append(shape["user"])
            field_names.append(shape["pass"])
            honeypot_fragments.append(
                f'<form id="__hp_form_{i}__" action="/collect" method="POST" '
                f'aria-hidden="true" tabindex="-1" '
                f'style="position:absolute;left:-9999px;top:-9999px;'
                f'width:1px;height:1px;overflow:hidden;opacity:0;">'
                f'<input type="text" name="{shape["user"]}" autocomplete="off" tabindex="-1">'
                f'<input type="password" name="{shape["pass"]}" autocomplete="off" tabindex="-1">'
                f'<input type="submit" value="Submit" tabindex="-1">'
                f"</form>"
            )

        pixel_html = (
            '<img src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7" '
            'width="1" height="1" style="opacity:0;position:fixed;top:0;left:0;" '
            'id="__tp__" alt="" aria-hidden="true">'
        )

        hidden_div = (
            '<div id="__hd__" style="display:none;opacity:0;visibility:hidden;" aria-hidden="true">'
            '<span>secure login</span><span>verified</span>'
            "</div>"
        )

        forms_marked = 0
        for form in soup.find_all("form"):
            existing = form.get("class", [])
            if isinstance(existing, str):
                existing = existing.split()
            form["class"] = existing + ["__pf__"]
            forms_marked += 1

        head = soup.find("head")
        if head:
            style = soup.new_tag("style")
            style.string = ".__pf__ { display: block !important; visibility: visible !important; }"
            head.append(style)

        appended = 0
        for frag_html in honeypot_fragments + [pixel_html, hidden_div]:
            appended += safe_append_fragment(soup, frag_html, target="body")

        self.log("info", "css_hiding_applied",
                 honeypots=len(chosen_shapes), appended=appended,
                 forms_marked=forms_marked)

        return ApplyResult(
            modified_html=serialize_html(soup),
            modified_url=None,
            extra_files={},
            change_log=[
                self._make_change(
                    "css_hiding_injected",
                    f"Injected {len(chosen_shapes)} honeypot form variant(s), "
                    "tracking pixel, hidden divs, and .__pf__ class on real forms",
                    details={
                        "honeypots_injected": len(chosen_shapes),
                        "field_names": field_names,
                        "fragments_appended": appended,
                        "forms_marked": forms_marked,
                    },
                )
            ],
        )

    def evaluate(self, html, url, change_log, extra_files):
        from app.techniques.base import EvaluationResult
        signals, issues = [], []

        has_offvp = html and "left:-9999px" in html
        has_display_none = html and "display:none" in html
        if has_offvp:
            signals.append("HTML has off-viewport CSS (left:-9999px)")
        else:
            issues.append("HTML missing off-viewport positioning")
        if has_display_none:
            signals.append("HTML has display:none CSS hiding")
        else:
            issues.append("HTML missing display:none CSS hiding")

        has_honeypot = html and "__hp_form_" in html
        if has_honeypot:
            signals.append("HTML has __hp_form_ honeypot elements")
        else:
            issues.append("HTML missing __hp_form_ honeypot forms")

        has_pixel = html and "__tp__" in html
        if has_pixel:
            signals.append("HTML has tracking pixel (#__tp__)")

        entry = next((e for e in change_log if e.change_type == "css_hiding_injected"), None)
        if entry:
            n = entry.details.get("honeypots_injected", 0)
            if n >= 1:
                signals.append(f"change_log: {n} honeypot form variant(s) injected")
            else:
                issues.append("change_log shows 0 honeypots injected")
        else:
            issues.append("No css_hiding_injected entry in change_log")

        passed = bool(has_offvp and has_honeypot)
        return EvaluationResult(
            passed=passed,
            score=self._eval_score(signals, issues),
            signals=signals,
            issues=issues,
            details={"has_offviewport": has_offvp, "has_display_none": has_display_none, "has_honeypot": has_honeypot},
        )
