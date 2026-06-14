from __future__ import annotations

import random
import urllib.parse
from typing import Any, ClassVar

from app.techniques.base import (
    ApplyResult, BaseTechnique, Category, OptionSpec, Requirement, TechniqueGroup,
)
from app.utils.homoglyph_map import LEET_MAP
from app.utils.url_utils import random_string


class LookAlikeTechnique(BaseTechnique):
    """
    T3 — Look-alike domains + Leetspeak + trust words.

    Injects trust-building words (login, secure, verify) into the subdomain
    or path, and optionally applies leet-speak character substitutions to
    mask keyword detection.
    """

    TECHNIQUE_ID: ClassVar[int] = 3
    TECHNIQUE_NAME: ClassVar[str] = "Look-alike + Leetspeak + Trust Words"
    GROUP: ClassVar[TechniqueGroup] = TechniqueGroup.URL_MANIPULATION
    CATEGORIES: ClassVar[list[Category]] = [Category.CREDENTIAL_THEFT, Category.BRAND_IMPERSONATION]
    REQUIREMENTS: ClassVar[list[Requirement]] = [Requirement.HAS_URL]
    DESCRIPTION: ClassVar[str] = (
        "Creates an independent look-alike domain by combining a leet-ified "
        "version of the brand label with trust words (login, secure, verify). "
        "Produces e.g. `secur3-brand.ir` — a standalone domain visually similar "
        "to the target, with leet substitutions to evade keyword blacklists."
    )
    OPTION_SPECS: ClassVar[list[OptionSpec]] = [
        OptionSpec(
            name="trust_words",
            description="Words to combine with the leet-ified domain label",
            type=list,
            default=["login", "secure", "verify", "account", "update", "signin"],
        ),
        OptionSpec(
            name="leet_density",
            description="Fraction of chars to leet-ify (0.0 = none, 1.0 = all)",
            type=float,
            default=0.4,
            min_value=0.0,
            max_value=1.0,
        ),
        OptionSpec(
            name="strategy",
            description=(
                "'standalone' (default): independent domain like `secur3-brand.ir`. "
                "'path': inject trust word into URL path."
            ),
            type=str,
            default="standalone",
        ),
        OptionSpec(
            name="num_words",
            description="Number of trust words to inject",
            type=int,
            default=1,
            min_value=1,
            max_value=3,
        ),
    ]

    def apply(
        self,
        html: str,
        url: str,
        options: dict[str, Any],
        screenshot_bytes: bytes | None = None,
    ) -> ApplyResult:
        lang = self._detect_lang(html, url)
        default_words = (
            ["vorood", "tayid", "hesab", "amn", "bedoroz"]
            if lang == "fa"
            else ["login", "secure", "verify", "account"]
        )
        trust_words: list[str] = options.get("trust_words", default_words)
        leet_density: float = float(options.get("leet_density", 0.4))
        strategy: str = options.get("strategy", "prepend")
        num_words: int = int(options.get("num_words", 1))

        from app.utils.url_utils import (
            is_ipv6_literal, parse_url, rebuild_url, split_domain_labels,
        )
        parsed, injected = parse_url(url)
        host = parsed.hostname or parsed.netloc

        if is_ipv6_literal(host):
            self.log("info", "lookalike_skip", reason="ipv6_literal")
            return ApplyResult(
                modified_html=None, modified_url=None, extra_files={},
                change_log=[self._make_change(
                    "url_lookalike_skipped", "Skipped: IPv6 literal",
                    before=url, after=url, details={"reason": "ipv6_literal"},
                )],
            )

        chosen = random.sample(trust_words, min(num_words, len(trust_words)))
        leet_words: list[str] = []
        leet_chars_total = 0
        for w in chosen:
            mutated, n = self._leetify(w, leet_density)
            leet_words.append(mutated)
            leet_chars_total += n

        base, _subs = split_domain_labels(parsed.netloc)
        target_label = base.split(".")[0] if base else ""

        base_parts = base.split(".")
        if len(base_parts) >= 3:
            tld = "." + ".".join(base_parts[-2:])
        elif len(base_parts) == 2:
            tld = "." + base_parts[-1]
        else:
            tld = ".ir"

        if strategy in ("standalone", "prepend"):
            leet_label, n = self._leetify_safe(target_label, leet_density)
            leet_chars_total += n
            trust_suffix = "-".join(leet_words)
            if random.random() < 0.5:
                new_netloc = f"{leet_label}-{trust_suffix}{tld}"
            else:
                new_netloc = f"{trust_suffix}-{leet_label}{tld}"
            new_url = rebuild_url(
                parsed._replace(netloc=new_netloc, path="", query="", fragment=""),
                strip_scheme=injected,
            )
        else:
            existing_path = (parsed.path or "/").lower()
            if any(f"/{w}" in existing_path for w in ("login", "signin", "verify", "secure")):
                self.log("info", "lookalike_path_skip",
                         reason="path_already_has_trust_word", path=parsed.path)
                return ApplyResult(
                    modified_html=None, modified_url=None, extra_files={},
                    change_log=[self._make_change(
                        "url_lookalike_skipped",
                        "Skipped: path already contains a trust word",
                        before=url, after=url,
                        details={"reason": "path_collision", "path": parsed.path},
                    )],
                )
            prefix = "/" + "/".join(leet_words)
            new_path = prefix + (parsed.path or "/")
            new_url = rebuild_url(parsed._replace(path=new_path), strip_scheme=injected)

        self.log("info", "lookalike_applied", strategy=strategy,
                 trust_words=",".join(chosen), leet_chars=leet_chars_total,
                 new_netloc=new_url)

        return ApplyResult(
            modified_html=None,
            modified_url=new_url,
            extra_files={},
            change_log=[
                self._make_change(
                    "url_lookalike_standalone",
                    f"Generated standalone look-alike domain '{new_url}' "
                    f"from brand label '{target_label}' + trust words {chosen} "
                    f"(leet density {leet_density})",
                    before=url,
                    after=new_url,
                    details={
                        "trust_words": chosen,
                        "leet_words": leet_words,
                        "leet_chars": leet_chars_total,
                        "strategy": strategy,
                        "brand_label": target_label,
                        "tld": tld,
                    },
                )
            ],
        )

    def _leetify(self, text: str, density: float) -> tuple[str, int]:
        result = []
        n = 0
        for ch in text:
            if ch in LEET_MAP and random.random() < density:
                result.append(random.choice(LEET_MAP[ch]))
                n += 1
            else:
                result.append(ch)
        return "".join(result), n

    def _leetify_safe(self, text: str, density: float) -> tuple[str, int]:
        """Leet-ify but keep only DNS-safe characters (alphanumeric + hyphen)."""
        _DNS_SAFE_LEET: dict[str, list[str]] = {
            "a": ["4"],
            "e": ["3"],
            "i": ["1"],
            "l": ["1"],
            "o": ["0"],
            "s": ["5"],
            "t": ["7"],
            "g": ["9"],
            "b": ["8"],
            "A": ["4"],
            "E": ["3"],
            "I": ["1"],
            "O": ["0"],
            "S": ["5"],
            "T": ["7"],
            "B": ["8"],
        }
        result = []
        n = 0
        for ch in text:
            if ch in _DNS_SAFE_LEET and random.random() < density:
                result.append(random.choice(_DNS_SAFE_LEET[ch]))
                n += 1
            else:
                result.append(ch)
        return "".join(result), n

    def evaluate(self, html, url, change_log, extra_files):
        from app.techniques.base import EvaluationResult
        from app.utils.url_utils import parse_url
        signals, issues = [], []

        parsed, _ = parse_url(url if "://" in url else "https://" + url)
        new_netloc = parsed.netloc.lower()

        entry = next((e for e in change_log if "brand_label" in e.details), None)
        if entry:
            orig_label = entry.details.get("brand_label", "")
            tld = entry.details.get("tld", "")
            if orig_label and f".{orig_label}." in f".{new_netloc}" and tld:
                issues.append(f"Generated domain appears to still be a subdomain of the original ({new_netloc!r})")
            else:
                signals.append(f"Domain is independent of original: {new_netloc!r}")

        leet_chars = [c for c in new_netloc if c in "01345789$!@€#"]
        if leet_chars:
            signals.append(f"Leet-speak substitutions in domain: {leet_chars[:6]}")

        if entry:
            brand = entry.details.get("brand_label", "")
            rev = new_netloc.translate(str.maketrans("013457", "oieast"))
            if brand and brand.lower()[:3] in rev:
                signals.append(f"Brand label '{brand}' traceable in domain after leet-reversal")
            elif brand:
                issues.append(f"Brand label '{brand}' not recognisable in {new_netloc!r} after leet-reversal")

        _COMMON_TRUST_FULL = {
            "login", "secure", "verify", "account", "update", "signin",
            "vorood", "tayid", "hesab", "amn", "bedoroz",
        }
        _TRUST_ROOTS = {"ogin", "ecure", "erify", "ccount", "pdate", "ignin",
                        "orood", "ayid", "esab", "edoroz"}
        trust_words = entry.details.get("trust_words", []) if entry else []
        all_trust = set(w.lower() for w in (trust_words or list(_COMMON_TRUST_FULL)))
        deleet = new_netloc.translate(str.maketrans("013457", "oieast"))
        tw_found = (
            any(tw in new_netloc for tw in all_trust)
            or any(root in new_netloc for root in _TRUST_ROOTS)
            or any(tw in deleet for tw in all_trust)
            or any(root in deleet for root in _TRUST_ROOTS)
        )
        if tw_found:
            signals.append(f"Trust word (or leet variant) found in domain: {new_netloc!r}")
        else:
            issues.append(f"No trust word detected in domain {new_netloc!r}")

        passed = bool(leet_chars) or tw_found
        return EvaluationResult(
            passed=passed,
            score=self._eval_score(signals, issues),
            signals=signals,
            issues=issues,
            details={"new_domain": new_netloc, "leet_char_count": len(leet_chars)},
        )
