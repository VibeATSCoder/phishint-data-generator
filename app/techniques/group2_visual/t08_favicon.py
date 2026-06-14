from __future__ import annotations

import urllib.parse
from typing import Any, ClassVar

from app.techniques.base import (
    ApplyResult, BaseTechnique, Category, OptionSpec, Requirement, TechniqueGroup,
)
from app.utils.html_utils import parse_html, serialize_html
from app.utils.image_utils import (
    fetch_image_bytes, image_to_data_uri,
    pil_image_from_bytes, pil_image_to_bytes,
)

try:
    from PIL import ImageEnhance
    _PIL_OK = True
except ImportError:
    _PIL_OK = False


class FaviconMimicryTechnique(BaseTechnique):
    """
    T8 — Favicon mimicry / loading from Clearbit API.

    Replaces or clones the page favicon with a slightly modified version
    (hue/brightness tweak) or loads it from the Clearbit Logo API to
    appear legitimate. The modified favicon evades hash-based favicon
    matching used by anti-phishing tools.
    """

    TECHNIQUE_ID: ClassVar[int] = 8
    TECHNIQUE_NAME: ClassVar[str] = "Favicon Mimicry"
    GROUP: ClassVar[TechniqueGroup] = TechniqueGroup.VISUAL_MIMICRY
    CATEGORIES: ClassVar[list[Category]] = [Category.BRAND_IMPERSONATION]
    REQUIREMENTS: ClassVar[list[Requirement]] = [Requirement.HAS_IMAGES]
    DESCRIPTION: ClassVar[str] = (
        "Clones or replaces the page favicon with a micro-edited version "
        "(brightness shift) or loads it from Clearbit's logo API to appear "
        "legitimate while evading favicon-based detection."
    )
    OPTION_SPECS: ClassVar[list[OptionSpec]] = [
        OptionSpec(
            name="use_clearbit",
            description="Load favicon from Clearbit logo API (requires internet)",
            type=bool,
            default=False,
        ),
        OptionSpec(
            name="clearbit_domain",
            description="Domain for Clearbit lookup (blank = use input URL's domain)",
            type=str,
            default="",
        ),
        OptionSpec(
            name="brightness_delta",
            description="Brightness factor offset for favicon clone (0.0 = unchanged)",
            type=float,
            default=0.05,
            min_value=0.0,
            max_value=0.3,
        ),
        OptionSpec(
            name="base_url",
            description="Base URL for resolving relative favicon paths",
            type=str,
            default="",
        ),
    ]

    @staticmethod
    def _is_icon_link(tag) -> bool:
        rel = tag.get("rel")
        if not rel:
            return False
        items = rel if isinstance(rel, list) else [rel]
        return any("icon" in str(r).lower() for r in items)

    @staticmethod
    def _mime_from_type_or_href(tag, href: str) -> str:
        t = (tag.get("type") or "").lower() if tag is not None else ""
        if t:
            return t
        lo = href.lower()
        if lo.endswith(".png"):
            return "image/png"
        if lo.endswith(".ico"):
            return "image/x-icon"
        if lo.endswith(".svg"):
            return "image/svg+xml"
        if lo.endswith(".webp"):
            return "image/webp"
        return "image/png"

    def apply(
        self,
        html: str,
        url: str,
        options: dict[str, Any],
        screenshot_bytes: bytes | None = None,
    ) -> ApplyResult:
        from app.utils.url_utils import domain_for_clearbit
        use_clearbit: bool = bool(options.get("use_clearbit", False))
        clearbit_domain: str = options.get("clearbit_domain", "")
        brightness_delta: float = float(options.get("brightness_delta", 0.05))
        base_url: str = options.get("base_url", "") or url

        domain = clearbit_domain or domain_for_clearbit(url)

        soup = parse_html(html)
        changes: list = []

        all_icons = [
            t for t in soup.find_all("link", rel=True) if self._is_icon_link(t)
        ]
        self.log("info", "favicon_scan", links_found=len(all_icons))

        if use_clearbit:
            clearbit_url = f"https://logo.clearbit.com/{domain}" if domain else ""
            if not clearbit_url:
                self.log("warning", "favicon_skip", reason="no_domain_for_clearbit")
                return ApplyResult(
                    modified_html=None, modified_url=None, extra_files={},
                    change_log=[self._make_change(
                        "favicon_skipped", "No usable domain for Clearbit lookup",
                        details={"reason": "no_domain"},
                    )],
                )
            updated = 0
            if all_icons:
                for tag in all_icons:
                    tag["href"] = clearbit_url
                    updated += 1
            else:
                head = soup.find("head")
                if head:
                    new_tag = soup.new_tag(
                        "link", rel="icon", type="image/png", href=clearbit_url
                    )
                    head.append(new_tag)
                    updated += 1

            self.log("info", "favicon_clearbit", domain=domain, updated=updated)
            changes.append(self._make_change(
                "favicon_clearbit",
                f"Pointed {updated} favicon link(s) at Clearbit for {domain}",
                after=clearbit_url,
                details={
                    "domain": domain, "links_found": len(all_icons),
                    "links_updated": updated, "source": "clearbit",
                },
            ))
            return ApplyResult(
                modified_html=serialize_html(soup),
                modified_url=None, extra_files={}, change_log=changes,
            )

        primary_tag = all_icons[0] if all_icons else None
        favicon_href = (
            primary_tag.get("href") if primary_tag is not None else None
        ) or "/favicon.ico"
        abs_href = urllib.parse.urljoin(base_url, favicon_href)

        raw = fetch_image_bytes(abs_href)
        extra_files: dict[str, bytes] = {}

        if raw and _PIL_OK and brightness_delta != 0.0:
            pil_img = pil_image_from_bytes(raw)
            if pil_img:
                enhancer = ImageEnhance.Brightness(pil_img)
                pil_img = enhancer.enhance(1.0 + brightness_delta)
                modified_bytes = pil_image_to_bytes(pil_img, "PNG")
                data_uri = image_to_data_uri(modified_bytes, "image/png")
                extra_files["images/modified_favicon.png"] = modified_bytes

                updated = 0
                format_chain: list[str] = []
                if all_icons:
                    for tag in all_icons:
                        format_chain.append(self._mime_from_type_or_href(tag, tag.get("href") or ""))
                        tag["href"] = data_uri
                        if tag.get("type"):
                            tag["type"] = "image/png"
                        updated += 1
                else:
                    head = soup.find("head")
                    if head:
                        new_tag = soup.new_tag(
                            "link", rel="icon", type="image/png", href=data_uri
                        )
                        head.append(new_tag)
                        updated += 1
                        format_chain.append("image/png")

                self.log("info", "favicon_micro_edit",
                         updated=updated, brightness=brightness_delta,
                         orig_bytes=len(raw), new_bytes=len(modified_bytes))
                changes.append(self._make_change(
                    "favicon_micro_edit",
                    f"Favicon cloned, brightness {brightness_delta:+.2f}, applied to {updated} link(s)",
                    before=favicon_href[:80], after="data:image/png;base64,...",
                    details={
                        "links_found": len(all_icons), "links_updated": updated,
                        "format_chain": format_chain,
                        "orig_bytes": len(raw), "new_bytes": len(modified_bytes),
                        "source": "page",
                    },
                ))
            else:
                self.log("warning", "favicon_decode_failed")
                changes.append(self._make_change(
                    "favicon_skipped", "Could not decode favicon image",
                    details={"reason": "decode_failed"},
                ))
        else:
            reason = "no_raw" if not raw else ("no_pil" if not _PIL_OK else "delta_zero")
            self.log("warning", "favicon_skip", reason=reason)
            changes.append(self._make_change(
                "favicon_skipped",
                "Favicon not fetched or PIL unavailable; no modification made",
                details={"reason": reason},
            ))

        return ApplyResult(
            modified_html=serialize_html(soup) if extra_files else None,
            modified_url=None,
            extra_files=extra_files,
            change_log=changes,
        )

    def evaluate(self, html, url, change_log, extra_files):
        from app.techniques.base import EvaluationResult
        signals, issues = [], []

        icon_found = False
        icon_type = ""
        if html:
            from app.utils.html_utils import parse_html
            soup = parse_html(html)
            for tag in soup.find_all("link"):
                rel = tag.get("rel") or []
                items = rel if isinstance(rel, list) else [rel]
                if any("icon" in str(r).lower() for r in items):
                    href = tag.get("href") or ""
                    if href.startswith("data:image/"):
                        icon_found = True
                        icon_type = "data_uri"
                    elif "clearbit.com" in href:
                        icon_found = True
                        icon_type = "clearbit"
                    elif href:
                        icon_type = "external"
        if icon_found:
            signals.append(f"Favicon link has {icon_type} source — evasion active")
        else:
            issues.append("No favicon link with data: URI or Clearbit found")

        entry = next(
            (e for e in change_log if e.change_type in ("favicon_micro_edit", "favicon_clearbit")), None
        )
        if entry:
            updated = entry.details.get("links_updated", 0)
            source = entry.details.get("source", "")
            signals.append(f"change_log: {updated} favicon link(s) updated via {source!r}")
        else:
            issues.append("No favicon_micro_edit or favicon_clearbit in change_log")

        png = extra_files.get("images/modified_favicon.png", b"")
        if len(png) > 100:
            signals.append(f"Modified favicon PNG in extra_files ({len(png)} bytes)")

        passed = icon_found
        return EvaluationResult(
            passed=passed,
            score=self._eval_score(signals, issues),
            signals=signals,
            issues=issues,
            details={"icon_found": icon_found, "icon_type": icon_type},
        )
