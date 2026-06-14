from __future__ import annotations

import random
import urllib.parse
from typing import Any, ClassVar

from app.techniques.base import (
    ApplyResult, BaseTechnique, Category, OptionSpec, Requirement, TechniqueGroup,
)
from app.utils.homoglyph_map import CHAR_SETS, DIGRAPH_TRICKS


class HomoglyphTechnique(BaseTechnique):
    """
    T1 — Homoglyph / Confusable characters + rn→m trick.

    Replaces Latin characters in the URL domain with visually identical
    Unicode look-alikes (Cyrillic, Greek) and applies digraph tricks
    (rn→m, cl→d, vv→w).
    """

    TECHNIQUE_ID: ClassVar[int] = 1
    TECHNIQUE_NAME: ClassVar[str] = "Homoglyph / Confusable Characters"
    GROUP: ClassVar[TechniqueGroup] = TechniqueGroup.URL_MANIPULATION
    CATEGORIES: ClassVar[list[Category]] = [
        Category.CREDENTIAL_THEFT, Category.BRAND_IMPERSONATION,
    ]
    REQUIREMENTS: ClassVar[list[Requirement]] = [Requirement.HAS_URL]
    DESCRIPTION: ClassVar[str] = (
        "Replaces Latin characters in the URL domain with Unicode look-alikes "
        "(Cyrillic/Greek) and applies digraph tricks (rn→m, cl→d). "
        "The URL looks identical to humans but is a different string."
    )
    OPTION_SPECS: ClassVar[list[OptionSpec]] = [
        OptionSpec(
            name="density",
            description="Fraction of eligible characters to replace (0.0–1.0)",
            type=float,
            default=0.5,
            min_value=0.0,
            max_value=1.0,
        ),
        OptionSpec(
            name="char_set",
            description="Unicode block for replacements: 'cyrillic' or 'greek'",
            type=str,
            default="cyrillic",
        ),
        OptionSpec(
            name="include_rn_trick",
            description="Apply rn→m, cl→d, vv→w digraph substitutions",
            type=bool,
            default=True,
        ),
        OptionSpec(
            name="target_domain_only",
            description="Only mutate the domain/netloc portion of the URL",
            type=bool,
            default=True,
        ),
        OptionSpec(
            name="mutate_subdomains",
            description="Also mutate subdomain labels (default: base domain label only)",
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
        density: float = float(options.get("density", 0.5))
        char_set: str = options.get("char_set", "cyrillic")
        include_rn: bool = bool(options.get("include_rn_trick", True))
        domain_only: bool = bool(options.get("target_domain_only", True))
        mutate_subs: bool = bool(options.get("mutate_subdomains", False))

        glyph_map = CHAR_SETS.get(char_set, CHAR_SETS["cyrillic"])

        from app.utils.url_utils import (
            is_already_punycode, is_ipv6_literal, parse_url, rebuild_url,
            split_domain_labels,
        )
        parsed, injected = parse_url(url)

        host = parsed.hostname or parsed.netloc
        if is_ipv6_literal(host):
            self.log("info", "homoglyph_skip", reason="ipv6_literal", host=host)
            return ApplyResult(
                modified_html=None, modified_url=None, extra_files={},
                change_log=[self._make_change(
                    "url_domain_homoglyph_skipped",
                    "Skipped: host is an IPv6 literal", before=url, after=url,
                    details={"reason": "ipv6_literal"},
                )],
            )

        chars_before = 0
        chars_after = 0
        skipped_punycode_labels: list[str] = []
        target_label = ""

        if domain_only:
            base, subs = split_domain_labels(parsed.netloc)
            base_labels = base.split(".") if base else []
            new_base_labels = list(base_labels)
            if new_base_labels:
                target_label = new_base_labels[0]
                if is_already_punycode(target_label):
                    skipped_punycode_labels.append(target_label)
                    self.log("info", "homoglyph_skip_label",
                             reason="already_punycode", label=target_label)
                else:
                    mutated, n = self._mutate(target_label, glyph_map, density, include_rn)
                    if n == 0:
                        eligible = [i for i, ch in enumerate(target_label) if ch in glyph_map]
                        if eligible:
                            import random as _r
                            pick = _r.choice(eligible)
                            lst = list(target_label)
                            lst[pick] = glyph_map[lst[pick]]
                            mutated = "".join(lst)
                            n = 1
                    new_base_labels[0] = mutated
                    chars_before += len(target_label)
                    chars_after += n

            new_subs = list(subs)
            if mutate_subs:
                for i, lbl in enumerate(subs):
                    if is_already_punycode(lbl):
                        skipped_punycode_labels.append(lbl)
                        continue
                    mutated, n = self._mutate(lbl, glyph_map, density, include_rn)
                    new_subs[i] = mutated
                    chars_after += n

            netloc_parts = new_subs + new_base_labels
            new_netloc = ".".join(p for p in netloc_parts if p)
            if parsed.port:
                new_netloc = f"{new_netloc}:{parsed.port}"
            new_url = rebuild_url(parsed._replace(netloc=new_netloc), strip_scheme=injected)
        else:
            full = parsed.netloc + parsed.path
            mutated_full, chars_after = self._mutate(full, glyph_map, density, include_rn)
            netloc_len = len(parsed.netloc)
            chars_before = len(full)
            new_url = rebuild_url(
                parsed._replace(netloc=mutated_full[:netloc_len], path=mutated_full[netloc_len:]),
                strip_scheme=injected,
            )

        self.log("info", "homoglyph_applied",
                 label=target_label, chars_replaced=chars_after,
                 char_set=char_set, mutate_subs=mutate_subs)

        return ApplyResult(
            modified_html=None,
            modified_url=new_url,
            extra_files={},
            change_log=[
                self._make_change(
                    "url_domain_homoglyph",
                    f"Replaced domain chars with {char_set} look-alikes "
                    f"(density={density}, rn_trick={include_rn})",
                    before=url,
                    after=new_url,
                    details={
                        "char_set": char_set,
                        "chars_replaced": chars_after,
                        "label": target_label,
                        "mutate_subdomains": mutate_subs,
                        "skipped_punycode": skipped_punycode_labels,
                    },
                )
            ],
        )

    def evaluate(self, html, url, change_log, extra_files):
        from app.techniques.base import EvaluationResult
        from app.utils.homoglyph_map import CHAR_SETS
        signals, issues = [], []

        try:
            url.encode("ascii")
            issues.append("URL is pure ASCII — no Unicode homoglyph characters found")
        except UnicodeEncodeError:
            signals.append("URL contains non-ASCII Unicode characters")

        all_glyphs: set[str] = set()
        for gmap in CHAR_SETS.values():
            all_glyphs.update(gmap.values())
        from urllib.parse import urlparse
        netloc = urlparse(url if "://" in url else "https://" + url).netloc.split(":")[0]
        matched = [c for c in netloc if c in all_glyphs]
        if matched:
            signals.append(f"Confirmed {len(matched)} Cyrillic/Greek homoglyph char(s) in domain: {matched[:5]}")
        else:
            issues.append("No Cyrillic/Greek homoglyph chars detected in domain")

        cl_entry = next(
            (e for e in change_log if e.change_type == "url_domain_homoglyph"), None
        )
        replaced = cl_entry.details.get("chars_replaced", 0) if cl_entry else 0
        if replaced > 0:
            signals.append(f"change_log: {replaced} character(s) replaced")

        target_url = extra_files.get("__target_url__", b"").decode("utf-8", errors="replace").strip()
        url_changed = bool(target_url and target_url != url)
        if url_changed and not matched:
            signals.append("URL visually modified via digraph/ASCII trick (confusable domain)")
        elif url_changed and matched:
            pass
        elif not url_changed and not matched and not replaced:
            issues.append("URL unchanged from original — no substitution applied")

        import unicodedata
        ascii_url = unicodedata.normalize("NFKD", url).encode("ascii", "ignore").decode()
        edit_dist = sum(a != b for a, b in zip(url, ascii_url)) + abs(len(url) - len(ascii_url))
        if 0 < edit_dist <= 8:
            signals.append(f"Edit distance from ASCII version: {edit_dist} (visually similar)")
        elif edit_dist == 0 and not url_changed:
            issues.append("URL identical to ASCII normalisation — no effective substitution")

        passed = bool(matched) or url_changed
        return EvaluationResult(
            passed=passed,
            score=self._eval_score(signals, issues),
            signals=signals,
            issues=issues,
            details={"glyph_chars_found": len(matched), "chars_replaced": replaced, "edit_distance": edit_dist},
        )

    def _mutate(
        self,
        text: str,
        glyph_map: dict[str, str],
        density: float,
        include_rn: bool,
    ) -> tuple[str, int]:
        replaced = 0
        if include_rn:
            for digraph, replacement in DIGRAPH_TRICKS:
                if digraph in text and random.random() < density:
                    text = text.replace(digraph, replacement, 1)
                    replaced += 1

        result = []
        for ch in text:
            if ch in glyph_map and random.random() < density:
                result.append(glyph_map[ch])
                replaced += 1
            else:
                result.append(ch)
        return "".join(result), replaced
