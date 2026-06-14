from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from bs4 import BeautifulSoup

from app.techniques.base import Category, Requirement

if TYPE_CHECKING:
    from app.techniques.base import BaseTechnique


@dataclass
class HTMLFeatures:
    """Structural facts extracted from the input HTML."""
    has_input_fields: bool
    has_images: bool
    has_inline_svg: bool
    has_favicon: bool
    has_scripts: bool
    has_iframes: bool
    has_password_input: bool
    image_count: int
    form_count: int
    input_count: int
    raw_html_length: int

    def to_dict(self) -> dict:
        return {
            "has_input_fields": self.has_input_fields,
            "has_images": self.has_images,
            "has_inline_svg": self.has_inline_svg,
            "has_favicon": self.has_favicon,
            "has_scripts": self.has_scripts,
            "has_iframes": self.has_iframes,
            "has_password_input": self.has_password_input,
            "image_count": self.image_count,
            "form_count": self.form_count,
            "input_count": self.input_count,
            "raw_html_length": self.raw_html_length,
        }


@dataclass
class TechniqueEligibility:
    technique_id: int
    technique_name: str
    group: str
    categories: list[str]
    is_applicable: bool
    reason: str
    ai_unavailable: bool = False

    def to_dict(self) -> dict:
        return {
            "technique_id": self.technique_id,
            "technique_name": self.technique_name,
            "group": self.group,
            "categories": self.categories,
            "is_applicable": self.is_applicable,
            "reason": self.reason,
            "ai_unavailable": self.ai_unavailable,
        }


class HTMLAnalyzer:
    """Stateless analyzer; call analyze() once per request."""

    def analyze(self, html: str, url: str) -> HTMLFeatures:
        soup = BeautifulSoup(html, "lxml")

        has_input = bool(soup.find(["input", "form"]))
        has_img = bool(soup.find("img", src=True))
        has_svg = bool(soup.find("svg"))
        has_images = has_img or has_svg

        favicon_tag = soup.find(
            "link",
            rel=lambda r: bool(r) and any(
                x in (r if isinstance(r, list) else [r])
                for x in ("icon", "shortcut icon", "apple-touch-icon")
            ),
        )

        return HTMLFeatures(
            has_input_fields=has_input,
            has_images=has_images,
            has_inline_svg=has_svg,
            has_favicon=bool(favicon_tag),
            has_scripts=bool(soup.find("script")),
            has_iframes=bool(soup.find("iframe")),
            has_password_input=bool(
                soup.find("input", attrs={"type": "password"})
            ),
            image_count=len(soup.find_all("img", src=True)),
            form_count=len(soup.find_all("form")),
            input_count=len(soup.find_all("input")),
            raw_html_length=len(html),
        )

    def evaluate_eligibility(
        self,
        features: HTMLFeatures,
        technique_cls_list: list[type[BaseTechnique]],
        category_filter: list[str] | None = None,
    ) -> list[TechniqueEligibility]:
        """Evaluate which techniques apply. Optionally pre-filter by category.

        category_filter: list of Category values (e.g. ["credential_theft"]).
                         A technique passes if any of its CATEGORIES matches.
                         When None or empty, no filtering is applied.
        """
        wanted: set[str] | None = (
            {c for c in category_filter} if category_filter else None
        )
        results: list[TechniqueEligibility] = []
        for cls in technique_cls_list:
            tech_cats = {c.value for c in cls.CATEGORIES}
            if wanted is not None and not (tech_cats & wanted):
                continue
            results.append(self._check(cls, features))
        return results

    @staticmethod
    def _ai_available() -> bool:
        """AI is considered available when at least one supported SDK is
        installed. The actual key may be supplied per-run (UI form fields)
        and is checked at apply-time, not here.
        """
        try:
            import anthropic  # noqa: F401
            return True
        except ImportError:
            pass
        try:
            import openai  # noqa: F401
            return True
        except ImportError:
            pass
        return False

    def _check(
        self,
        cls: type[BaseTechnique],
        features: HTMLFeatures,
    ) -> TechniqueEligibility:
        ai_ok = self._ai_available()
        checks: dict[Requirement, tuple[bool, str]] = {
            Requirement.ALWAYS: (True, "Always applicable"),
            Requirement.HAS_URL: (True, "URL always provided"),
            Requirement.HAS_HTML: (
                features.raw_html_length > 0,
                "Requires non-empty HTML input",
            ),
            Requirement.HAS_INPUT_FIELDS: (
                features.has_input_fields,
                "Requires <input> or <form> elements in HTML",
            ),
            Requirement.HAS_IMAGES: (
                features.has_images,
                "Requires <img> or <svg> elements in HTML",
            ),
            Requirement.REQUIRES_AI: (
                ai_ok,
                "Requires Anthropic API — ANTHROPIC_API_KEY not set or SDK not installed",
            ),
        }

        failures: list[str] = []
        ai_failed = False
        for req in cls.REQUIREMENTS:
            ok, msg = checks[req]
            if not ok:
                failures.append(msg)
                if req == Requirement.REQUIRES_AI:
                    ai_failed = True

        cat_values = [c.value for c in cls.CATEGORIES]
        if failures:
            return TechniqueEligibility(
                technique_id=cls.TECHNIQUE_ID,
                technique_name=cls.TECHNIQUE_NAME,
                group=cls.GROUP.value,
                categories=cat_values,
                is_applicable=False,
                reason="Not applicable — " + "; ".join(failures),
                ai_unavailable=ai_failed,
            )

        return TechniqueEligibility(
            technique_id=cls.TECHNIQUE_ID,
            technique_name=cls.TECHNIQUE_NAME,
            group=cls.GROUP.value,
            categories=cat_values,
            is_applicable=True,
            reason="All requirements satisfied",
        )
