from __future__ import annotations

import urllib.parse
from typing import Any, ClassVar

from app.techniques.base import (
    ApplyResult, BaseTechnique, Category, OptionSpec, Requirement, TechniqueGroup,
)
from app.utils.homoglyph_map import CHAR_SETS


class PunycodeTechnique(BaseTechnique):
    """
    T2 — Punycode / IDN Homograph Attack.

    Registers a domain containing non-Latin Unicode characters that render
    visually like the original domain. The URL is encoded as a punycode
    xn-- domain that browsers decode back to the Unicode form.
    """

    TECHNIQUE_ID: ClassVar[int] = 2
    TECHNIQUE_NAME: ClassVar[str] = "Punycode / IDN Homograph"
    GROUP: ClassVar[TechniqueGroup] = TechniqueGroup.URL_MANIPULATION
    CATEGORIES: ClassVar[list[Category]] = [Category.CREDENTIAL_THEFT, Category.BRAND_IMPERSONATION]
    REQUIREMENTS: ClassVar[list[Requirement]] = [Requirement.HAS_URL]
    DESCRIPTION: ClassVar[str] = (
        "Encodes the domain with Punycode (xn--) using Unicode look-alike "
        "characters. Browsers render the decoded Unicode form, making the "
        "domain appear identical to the legitimate site."
    )
    OPTION_SPECS: ClassVar[list[OptionSpec]] = [
        OptionSpec(
            name="char_set",
            description="Unicode block for substitutions: 'cyrillic' or 'greek'",
            type=str,
            default="cyrillic",
        ),
        OptionSpec(
            name="mixed_script_only",
            description="Only encode labels where the substitution produces mixed scripts (safer for browser rendering)",
            type=bool,
            default=False,
        ),
    ]

    def apply(
        self,
        html: str,
        url: str,
        options: dict[str, Any],
        screenshot_bytes: bytes | None = None,
    ) -> ApplyResult:
        char_set: str = options.get("char_set", "cyrillic")
        mixed_only: bool = bool(options.get("mixed_script_only", False))
        glyph_map = CHAR_SETS.get(char_set, CHAR_SETS["cyrillic"])

        from app.utils.url_utils import (
            is_already_punycode, is_ipv6_literal, parse_url, rebuild_url,
        )
        parsed, injected = parse_url(url)
        host = parsed.hostname or parsed.netloc

        if is_ipv6_literal(host):
            self.log("info", "punycode_skip", reason="ipv6_literal")
            return ApplyResult(
                modified_html=None, modified_url=None, extra_files={},
                change_log=[self._make_change(
                    "url_punycode_skipped", "Skipped: IPv6 literal",
                    before=url, after=url, details={"reason": "ipv6_literal"},
                )],
            )

        netloc_host = parsed.hostname or parsed.netloc
        port_suffix = f":{parsed.port}" if parsed.port else ""

        labels = netloc_host.split(".")
        encoded_labels: list[str] = []
        labels_encoded: list[str] = []
        labels_skipped: list[dict] = []

        for label in labels:
            if is_already_punycode(label):
                try:
                    decoded = label.encode("ascii").decode("idna")
                    label_to_encode = "".join(glyph_map.get(ch, ch) for ch in decoded)
                except Exception:
                    encoded_labels.append(label)
                    labels_skipped.append({"label": label, "reason": "decode_failed"})
                    continue
            else:
                label_to_encode = "".join(glyph_map.get(ch, ch) for ch in label)

            if mixed_only and label_to_encode == label:
                encoded_labels.append(label)
                labels_skipped.append({"label": label, "reason": "no_substitution"})
                continue

            try:
                encoded = label_to_encode.encode("idna").decode("ascii")
                encoded_labels.append(encoded)
                if encoded != label:
                    labels_encoded.append(label)
            except Exception as e:
                encoded_labels.append(label)
                labels_skipped.append({"label": label, "reason": f"idna_error:{type(e).__name__}"})
                self.log("warning", "punycode_label_failed", label=label, error=str(e))

        punycode_domain = ".".join(encoded_labels) + port_suffix
        unicode_domain = ".".join(
            "".join(glyph_map.get(ch, ch) for ch in l) for l in labels
        ) + port_suffix

        new_url = rebuild_url(parsed._replace(netloc=punycode_domain), strip_scheme=injected)

        self.log("info", "punycode_applied",
                 encoded=len(labels_encoded), skipped=len(labels_skipped))

        return ApplyResult(
            modified_html=None,
            modified_url=new_url,
            extra_files={
                "punycode_info.txt": (
                    f"Original domain: {netloc_host}\n"
                    f"Unicode (display) domain: {unicode_domain}\n"
                    f"Punycode domain: {punycode_domain}\n"
                    f"Full phishing URL: {new_url}\n"
                ).encode()
            },
            change_log=[
                self._make_change(
                    "url_punycode_idn",
                    f"Domain encoded via Punycode/IDN using {char_set} chars",
                    before=url,
                    after=new_url,
                    details={
                        "char_set": char_set,
                        "labels_encoded": labels_encoded,
                        "labels_skipped": labels_skipped,
                        "mixed_script_only": mixed_only,
                    },
                )
            ],
        )

    def evaluate(self, html, url, change_log, extra_files):
        from app.techniques.base import EvaluationResult
        signals, issues = [], []

        from urllib.parse import urlparse
        netloc = urlparse(url if "://" in url else "https://" + url).netloc.split(":")[0]
        xn_labels = [l for l in netloc.split(".") if l.lower().startswith("xn--")]
        if xn_labels:
            signals.append(f"Found {len(xn_labels)} Punycode (xn--) label(s): {xn_labels}")
        else:
            issues.append("No xn-- Punycode labels found in URL domain")

        decoded_ok, decoded_fail = [], []
        for label in xn_labels:
            try:
                decoded = label.encode("ascii").decode("idna")
                if decoded != label:
                    decoded_ok.append(decoded)
            except Exception:
                decoded_fail.append(label)
        if decoded_ok:
            signals.append(f"Punycode decodes to Unicode: {decoded_ok[:3]}")
        if decoded_fail:
            issues.append(f"Labels failed IDN decode: {decoded_fail}")

        info = extra_files.get("punycode_info.txt", b"").decode("utf-8", errors="replace")
        if "Unicode (display) domain:" in info:
            unicode_domain = [l for l in info.splitlines() if l.startswith("Unicode")][0]
            signals.append(f"Unicode display form recorded: {unicode_domain}")
        else:
            issues.append("punycode_info.txt missing or lacks Unicode display domain")

# 4. change_log confirms encoding happened
        encoded = next(
            (e.details.get("labels_encoded", []) for e in change_log
             if e.change_type == "url_punycode_idn"), []
        )
        if encoded:
            signals.append(f"change_log: encoded labels {encoded}")
        else:
            issues.append("change_log shows no labels were encoded")

        passed = bool(xn_labels) and bool(decoded_ok)
        return EvaluationResult(
            passed=passed,
            score=self._eval_score(signals, issues),
            signals=signals,
            issues=issues,
            details={"xn_label_count": len(xn_labels), "decoded_ok": len(decoded_ok)},
        )
