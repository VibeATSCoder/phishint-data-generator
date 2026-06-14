from __future__ import annotations

import random
import urllib.parse
from typing import Any, ClassVar

from app.techniques.base import (
    ApplyResult, BaseTechnique, Category, OptionSpec, Requirement, TechniqueGroup,
)


class PolymorphicUrlTechnique(BaseTechnique):
    """
    T5 — Polymorphic URL + AI-generated variations.

    Generates multiple unique URL variants for each attack run using
    N-gram substitution, typo injection, and path variation strategies.
    Each variant looks slightly different, defeating signature-based detection.
    """

    TECHNIQUE_ID: ClassVar[int] = 5
    TECHNIQUE_NAME: ClassVar[str] = "Polymorphic URL Variations"
    GROUP: ClassVar[TechniqueGroup] = TechniqueGroup.URL_MANIPULATION
    CATEGORIES: ClassVar[list[Category]] = [Category.CREDENTIAL_THEFT, Category.MALWARE_DISTRIBUTION]
    REQUIREMENTS: ClassVar[list[Requirement]] = [Requirement.HAS_URL]
    DESCRIPTION: ClassVar[str] = (
        "Produces N unique URL variants per run using N-gram substitution, "
        "typo injection, and random path/parameter variations. "
        "Each request gets a unique URL, defeating signature-based detection."
    )
    OPTION_SPECS: ClassVar[list[OptionSpec]] = [
        OptionSpec(
            name="variation_count",
            description="Number of URL variants to generate",
            type=int,
            default=5,
            min_value=1,
            max_value=20,
        ),
        OptionSpec(
            name="strategy",
            description="Mutation strategy: 'ngram', 'typo', or 'mixed'",
            type=str,
            default="mixed",
        ),
    ]

    _TYPO_MAP: dict[str, list[str]] = {
        "a": ["s", "q", "z"],
        "e": ["r", "w", "d"],
        "i": ["o", "u", "k"],
        "o": ["p", "i", "l"],
        "s": ["a", "d", "w"],
        "n": ["m", "b", "h"],
        "g": ["f", "h", "t"],
        "l": ["k", "p", "o"],
    }

    _MIN_DIFF_CHARS = 1

    def apply(
        self,
        html: str,
        url: str,
        options: dict[str, Any],
        screenshot_bytes: bytes | None = None,
    ) -> ApplyResult:
        count: int = int(options.get("variation_count", 5))
        strategy: str = options.get("strategy", "mixed")

        from app.utils.url_utils import parse_url, rebuild_url
        parsed, injected = parse_url(url)
        domain = parsed.netloc

        seen: set[str] = {url}
        variations: list[str] = []
        duplicates_dropped = 0
        attempts = 0
        max_attempts = count * 6
        while len(variations) < count and attempts < max_attempts:
            attempts += 1
            if strategy == "ngram":
                candidate = rebuild_url(
                    parsed._replace(netloc=self._ngram_mutate(domain)),
                    strip_scheme=injected,
                )
            elif strategy == "typo":
                candidate = rebuild_url(
                    parsed._replace(netloc=self._typo_mutate(domain)),
                    strip_scheme=injected,
                )
            else:
                fn = random.choices(
                    [self._ngram_mutate, self._typo_mutate, self._path_vary],
                    weights=[4, 4, 1],
                    k=1,
                )[0]
                if fn == self._path_vary:
                    candidate = self._path_vary(url, parsed, injected)
                else:
                    candidate = rebuild_url(
                        parsed._replace(netloc=fn(domain)),
                        strip_scheme=injected,
                    )

            if candidate in seen:
                duplicates_dropped += 1
                continue
            if self._char_diff(candidate, url) < self._MIN_DIFF_CHARS:
                duplicates_dropped += 1
                continue
            seen.add(candidate)
            variations.append(candidate)

        if duplicates_dropped:
            self.log("info", "polymorphic_dedup", dropped=duplicates_dropped)

        primary = variations[0] if variations else url
        variations_text = "\n".join(variations).encode()

        self.log("info", "polymorphic_applied",
                 strategy=strategy, variants=len(variations))

        return ApplyResult(
            modified_html=None,
            modified_url=primary,
            extra_files={"url_polymorphic_variants.txt": variations_text},
            change_log=[
                self._make_change(
                    "url_polymorphic",
                    f"Generated {len(variations)} URL variants using '{strategy}' strategy",
                    before=url,
                    after=primary,
                    details={
                        "strategy": strategy,
                        "variants": variations,
                        "duplicates_dropped": duplicates_dropped,
                        "requested": count,
                    },
                )
            ],
        )

    @staticmethod
    def _char_diff(a: str, b: str) -> int:
        if len(a) != len(b):
            return max(len(a), len(b)) - min(len(a), len(b)) + sum(
                1 for x, y in zip(a, b) if x != y
            )
        return sum(1 for x, y in zip(a, b) if x != y)

    def _ngram_mutate(self, domain: str) -> str:
        """Insert/delete a single character at a random position."""
        if len(domain) < 4:
            return domain
        pos = random.randint(1, len(domain) - 2)
        op = random.choice(["insert", "delete", "swap"])
        if op == "insert":
            ch = random.choice("abcdefghijklmnopqrstuvwxyz0123456789")
            return domain[:pos] + ch + domain[pos:]
        if op == "delete":
            return domain[:pos] + domain[pos + 1:]
        lst = list(domain)
        lst[pos], lst[pos - 1] = lst[pos - 1], lst[pos]
        return "".join(lst)

    def _typo_mutate(self, domain: str) -> str:
        """Replace a char with a keyboard-adjacent neighbour."""
        candidates = [(i, ch) for i, ch in enumerate(domain) if ch in self._TYPO_MAP]
        if not candidates:
            return self._ngram_mutate(domain)
        idx, ch = random.choice(candidates)
        replacement = random.choice(self._TYPO_MAP[ch])
        return domain[:idx] + replacement + domain[idx + 1:]

    def evaluate(self, html, url, change_log, extra_files):
        from app.techniques.base import EvaluationResult
        signals, issues = [], []

        variants_file = extra_files.get("url_polymorphic_variants.txt", b"")
        variants_lines = [v for v in variants_file.decode("utf-8", errors="replace").splitlines() if v.strip()]
        variant_count = len(variants_lines)

        if variant_count >= 2:
            signals.append(f"variants file has {variant_count} unique URL(s)")
        else:
            issues.append(f"variants file has only {variant_count} URL(s) — expected ≥ 2")

        from urllib.parse import urlparse
        primary_netloc = urlparse(url if "://" in url else "https://" + url).netloc
        domain_changes = sum(
            1 for v in variants_lines
            if urlparse(v if "://" in v else "https://" + v).netloc != primary_netloc
        )
        if domain_changes >= 1:
            signals.append(f"{domain_changes}/{variant_count} variant(s) have domain-level mutations")
        else:
            issues.append("No domain-level mutations found — all variants are path-only")

        unique_count = len(set(variants_lines))
        if unique_count == variant_count and variant_count > 0:
            signals.append(f"All {unique_count} variants are unique strings")
        elif variant_count > 0:
            issues.append(f"Duplicate variants detected: {variant_count} entries but only {unique_count} unique")

        entry = next((e for e in change_log if e.change_type == "url_polymorphic"), None)
        strategy = ""
        if entry:
            strategy = entry.details.get("strategy", "")
            if strategy:
                signals.append(f"Strategy recorded: {strategy!r}")
        else:
            issues.append("No url_polymorphic entry in change_log (supplementary check)")

        passed = variant_count >= 2 and unique_count == variant_count
        return EvaluationResult(
            passed=passed,
            score=self._eval_score(signals, issues),
            signals=signals,
            issues=issues,
            details={"variant_count": variant_count, "domain_changes": domain_changes, "strategy": strategy},
        )

    def _path_vary(self, url: str, parsed=None, injected: bool = False) -> str:
        """Append a random path segment."""
        from app.utils.url_utils import parse_url, rebuild_url
        if parsed is None:
            parsed, injected = parse_url(url)
        suffix = "/" + "".join(random.choices("abcdefghijklmnopqrstuvwxyz", k=6))
        new_path = (parsed.path or "") + suffix
        return rebuild_url(parsed._replace(path=new_path), strip_scheme=injected)
