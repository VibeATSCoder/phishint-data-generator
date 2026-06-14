from __future__ import annotations

import base64
from typing import Any, ClassVar

from app.techniques.base import (
    ApplyResult, BaseTechnique, Category, OptionSpec, Requirement, TechniqueGroup,
)
from app.utils.html_utils import (
    ensure_head, parse_html, serialize_html,
)
from app.utils.js_templates import DYNAMIC_DOM_TEMPLATE


class DynamicDomTechnique(BaseTechnique):
    """
    T10 — Dynamic / Polymorphic DOM generation via JS.

    Encodes the entire <body> content as base64, removes it from the HTML,
    and injects a script that reconstructs it at runtime via JavaScript.
    Static HTML analysers see an empty body; the real content only appears
    after JS execution.
    """

    TECHNIQUE_ID: ClassVar[int] = 10
    TECHNIQUE_NAME: ClassVar[str] = "Dynamic DOM Generation via JS"
    GROUP: ClassVar[TechniqueGroup] = TechniqueGroup.HTML_DOM_JS
    CATEGORIES: ClassVar[list[Category]] = [Category.CREDENTIAL_THEFT]
    REQUIREMENTS: ClassVar[list[Requirement]] = [Requirement.HAS_HTML]
    DESCRIPTION: ClassVar[str] = (
        "Encodes the entire <body> as base64 and removes it from the HTML. "
        "A small injected script reconstructs the body at runtime, making the "
        "page appear empty to static HTML analysers."
    )
    OPTION_SPECS: ClassVar[list[OptionSpec]] = []

    def apply(
        self,
        html: str,
        url: str,
        options: dict[str, Any],
        screenshot_bytes: bytes | None = None,
    ) -> ApplyResult:
        soup = parse_html(html)
        body = soup.find("body")

        if body is None:
            body_content = str(soup)
        else:
            body_content = body.decode_contents()

        body_content_safe = body_content.replace("</script>", "<\\/script>")

        body_bytes_orig = len(body_content.encode("utf-8"))

        if body_bytes_orig < 20:
            return ApplyResult(
                modified_html=None, modified_url=None, extra_files={},
                change_log=[self._make_change(
                    "dynamic_dom_skipped",
                    "Original HTML body is empty; skipping dynamic DOM injection",
                    details={"body_bytes": body_bytes_orig},
                )],
            )

        b64_body = base64.b64encode(body_content_safe.encode("utf-8")).decode("ascii")
        body_bytes_encoded = len(b64_body)

        head = soup.find("head")
        scripts_external = (
            sum(1 for s in head.find_all("script") if s.get("src")) if head else 0
        )
        stylesheets = (
            sum(1 for l in head.find_all("link") if "stylesheet" in (l.get("rel") or [])) if head else 0
        )

        ensure_head(soup)
        if body:
            body.clear()
        else:
            body = soup.new_tag("body")
            html_tag = soup.find("html")
            if html_tag:
                html_tag.append(body)
            else:
                soup.append(body)

        loader_script = soup.new_tag("script")
        loader_script.string = DYNAMIC_DOM_TEMPLATE.format(b64_body=b64_body)
        soup.find("head").append(loader_script)

        self.log("info", "dynamic_dom_applied",
                 body_bytes=body_bytes_orig, b64_bytes=body_bytes_encoded,
                 scripts_external=scripts_external, stylesheets=stylesheets)

        return ApplyResult(
            modified_html=serialize_html(soup),
            modified_url=None,
            extra_files={},
            change_log=[
                self._make_change(
                    "dynamic_dom_injection",
                    "Body content base64-encoded and replaced with runtime JS reconstructor",
                    before=f"<body>{body_content[:60]}...</body>",
                    after="<body></body> + <script>atob reconstructor</script>",
                    details={
                        "body_bytes_orig": body_bytes_orig,
                        "body_bytes_encoded": body_bytes_encoded,
                        "scripts_external": scripts_external,
                        "stylesheets": stylesheets,
                    },
                )
            ],
        )

    def evaluate(self, html, url, change_log, extra_files):
        from app.techniques.base import EvaluationResult
        signals, issues = [], []

        body_minimal = False
        if html:
            from app.utils.html_utils import parse_html
            soup = parse_html(html)
            body = soup.find("body")
            body_text = body.get_text(strip=True) if body else ""
            body_tags = len(body.find_all(True)) if body else 0
            if body_tags <= 1:
                body_minimal = True
                signals.append(f"Static body is empty/minimal ({body_tags} child tag(s))")
            else:
                issues.append(f"Static body has {body_tags} visible tag(s) — content may not be hidden")

        has_atob = html and "atob(" in html
        has_inner = html and "innerHTML" in html
        if has_atob and has_inner:
            signals.append("HTML has atob()+innerHTML JS reconstructor")
        else:
            issues.append(f"Missing {'atob()' if not has_atob else ''} {'innerHTML' if not has_inner else ''}")

        entry = next((e for e in change_log if e.change_type == "dynamic_dom_injection"), None)
        if entry:
            orig = entry.details.get("body_bytes_orig", 0)
            if orig >= 20:
                signals.append(f"change_log: {orig} bytes of body content encoded")
            else:
                issues.append(f"change_log body_bytes_orig={orig} — suspiciously small")
        else:
            issues.append("No dynamic_dom_injection in change_log")

        passed = body_minimal and has_atob and has_inner
        return EvaluationResult(
            passed=passed,
            score=self._eval_score(signals, issues),
            signals=signals,
            issues=issues,
            details={"body_minimal": body_minimal, "has_atob": has_atob, "has_innerhtml": has_inner},
        )
