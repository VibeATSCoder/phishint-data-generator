from __future__ import annotations

import io
import urllib.parse
from typing import Any, ClassVar

from app.techniques.base import (
    ApplyResult, BaseTechnique, Category, OptionSpec, Requirement, TechniqueGroup,
)
from app.utils.html_utils import find_brand_logo, parse_html, serialize_html
from app.utils.image_utils import (
    fetch_image_bytes, get_image_mime, image_to_data_uri,
    pil_image_from_bytes, pil_image_to_bytes,
)

try:
    from PIL import ImageEnhance, ImageFilter
    _PIL_OK = True
except ImportError:
    _PIL_OK = False


class LogoPixelEditTechnique(BaseTechnique):
    """
    T7 — Logo pixel-level editing.

    Fetches the first (or Nth) <img> in the page, applies micro-adjustments
    (brightness, hue-rotation via HSV, pixel shift) and embeds the modified
    image as a data-URI. The result defeats perceptual-hash and SSIM detectors
    while remaining invisible to humans.
    """

    TECHNIQUE_ID: ClassVar[int] = 7
    TECHNIQUE_NAME: ClassVar[str] = "Logo Pixel-Level Editing"
    GROUP: ClassVar[TechniqueGroup] = TechniqueGroup.VISUAL_MIMICRY
    CATEGORIES: ClassVar[list[Category]] = [Category.BRAND_IMPERSONATION]
    REQUIREMENTS: ClassVar[list[Requirement]] = [Requirement.HAS_IMAGES]
    DESCRIPTION: ClassVar[str] = (
        "Applies invisible micro-edits to images (brightness tweak, pixel shift) "
        "to defeat perceptual-hash / SSIM detectors while looking identical to humans."
    )
    OPTION_SPECS: ClassVar[list[OptionSpec]] = [
        OptionSpec(
            name="pixel_shift",
            description="Pixels to shift image (0 = none)",
            type=int,
            default=1,
            min_value=0,
            max_value=5,
        ),
        OptionSpec(
            name="brightness_delta",
            description="Brightness factor offset (0.0 = unchanged, 0.02 = +2%)",
            type=float,
            default=0.02,
            min_value=0.0,
            max_value=0.2,
        ),
        OptionSpec(
            name="target_image_index",
            description="Override: index (0-based) of the <img> to modify. Negative = auto-pick brand logo.",
            type=int,
            default=-1,
            min_value=-1,
            max_value=99,
        ),
        OptionSpec(
            name="base_url",
            description="Base URL for resolving relative image src paths",
            type=str,
            default="",
        ),
        OptionSpec(
            name="svg_fallback_recolor",
            description="If the chosen brand asset is an SVG, inject a CSS fill override instead of pixel-editing",
            type=bool,
            default=True,
        ),
    ]

    def apply(
        self,
        html: str,
        url: str,
        options: dict[str, Any],
        screenshot_bytes: bytes | None = None,
    ) -> ApplyResult:
        if not _PIL_OK:
            return ApplyResult(
                modified_html=None,
                modified_url=None,
                extra_files={},
                change_log=[
                    self._make_change(
                        "logo_edit_skipped",
                        "Pillow (PIL) not installed; skipping logo edit",
                    )
                ],
            )

        pixel_shift: int = int(options.get("pixel_shift", 1))
        brightness_delta: float = float(options.get("brightness_delta", 0.02))
        target_idx: int = int(options.get("target_image_index", -1))
        base_url: str = options.get("base_url", "") or url
        svg_fallback: bool = bool(options.get("svg_fallback_recolor", True))

        soup = parse_html(html)
        images = soup.find_all("img", src=True)
        images_scanned = len(images)

        picker = "explicit_index"
        if target_idx >= 0:
            if target_idx >= len(images):
                self.log("warning", "logo_skip", reason="bad_index", idx=target_idx)
                return ApplyResult(
                    modified_html=None, modified_url=None, extra_files={},
                    change_log=[self._make_change(
                        "logo_edit_skipped", f"No image at index {target_idx}",
                        details={"reason": "bad_index", "images_scanned": images_scanned},
                    )],
                )
            img_tag = images[target_idx]
        else:
            img_tag, picker = find_brand_logo(soup)
            if img_tag is None:
                self.log("warning", "logo_skip", reason="no_candidate")
                return ApplyResult(
                    modified_html=None, modified_url=None, extra_files={},
                    change_log=[self._make_change(
                        "logo_edit_skipped", "No brand logo candidate found",
                        details={"reason": "no_candidate", "images_scanned": images_scanned},
                    )],
                )

        self.log("info", "logo_picked", picker=picker, scanned=images_scanned)

        src_attr = "src" if img_tag.name == "img" else "href"
        src = img_tag.get(src_attr) or ""
        original_src = src

        if not src:
            self.log("warning", "logo_skip", reason="empty_src")
            return ApplyResult(
                modified_html=None, modified_url=None, extra_files={},
                change_log=[self._make_change(
                    "logo_edit_skipped", "Picked tag has no usable src/href",
                    details={"reason": "empty_src", "picker": picker},
                )],
            )

        if src.startswith("data:"):
            self.log("info", "logo_skip", reason="data_uri")
            return ApplyResult(
                modified_html=None, modified_url=None, extra_files={},
                change_log=[self._make_change(
                    "logo_edit_skipped", "Picked logo is a data: URI",
                    details={"reason": "data_uri", "picker": picker},
                )],
            )

        is_svg = src.lower().endswith(".svg") or "image/svg" in (img_tag.get("type") or "").lower()
        if is_svg:
            if not svg_fallback:
                return ApplyResult(
                    modified_html=None, modified_url=None, extra_files={},
                    change_log=[self._make_change(
                        "logo_edit_skipped", "SVG fallback disabled",
                        details={"reason": "svg_no_fallback", "picker": picker},
                    )],
                )
            hue_deg = int(brightness_delta * 100)
            style = (img_tag.get("style") or "").rstrip(";")
            filt = f"filter:hue-rotate({hue_deg}deg) brightness({1.0 + brightness_delta:.3f});"
            img_tag["style"] = (style + ";" + filt) if style else filt
            self.log("info", "logo_svg_recolor", hue_deg=hue_deg, picker=picker)
            return ApplyResult(
                modified_html=serialize_html(soup),
                modified_url=None,
                extra_files={},
                change_log=[self._make_change(
                    "logo_svg_recolor",
                    f"Applied CSS filter to SVG logo (hue+{hue_deg}°, brightness+{brightness_delta})",
                    before=original_src[:80], after="<svg + css filter>",
                    details={
                        "picker": picker, "images_scanned": images_scanned,
                        "format": "svg", "hue_deg": hue_deg,
                    },
                )],
            )

        abs_src = urllib.parse.urljoin(base_url, src)
        raw = fetch_image_bytes(abs_src)
        if raw is None:
            self.log("warning", "logo_fetch_failed", src=abs_src[:120])
            return ApplyResult(
                modified_html=None, modified_url=None, extra_files={},
                change_log=[self._make_change(
                    "logo_edit_skipped", f"Could not fetch image: {abs_src[:80]}",
                    details={"reason": "fetch_failed", "picker": picker},
                )],
            )

        pil_img = pil_image_from_bytes(raw)
        if pil_img is None:
            self.log("warning", "logo_decode_failed")
            return ApplyResult(
                modified_html=None, modified_url=None, extra_files={},
                change_log=[self._make_change(
                    "logo_edit_skipped", "PIL could not decode fetched bytes",
                    details={"reason": "decode_failed", "picker": picker},
                )],
            )

        orig_bytes_len = len(raw)
        if brightness_delta != 0.0:
            enhancer = ImageEnhance.Brightness(pil_img)
            pil_img = enhancer.enhance(1.0 + brightness_delta)

        if pixel_shift > 0:
            w, h = pil_img.size
            pil_img = pil_img.crop((pixel_shift, pixel_shift, w, h))
            pil_img = pil_img.resize((w, h))

        modified_bytes = pil_image_to_bytes(pil_img, "PNG")
        data_uri = image_to_data_uri(modified_bytes, "image/png")

        img_tag[src_attr] = data_uri
        img_tag["data-original-src"] = original_src

        self.log("info", "logo_pixel_edit_applied",
                 picker=picker, scanned=images_scanned,
                 orig_bytes=orig_bytes_len, new_bytes=len(modified_bytes),
                 brightness=brightness_delta, shift=pixel_shift)

        return ApplyResult(
            modified_html=serialize_html(soup),
            modified_url=None,
            extra_files={"images/modified_logo_0.png": modified_bytes},
            change_log=[
                self._make_change(
                    "logo_pixel_edit",
                    f"Applied brightness_delta={brightness_delta}, "
                    f"pixel_shift={pixel_shift} via picker={picker}",
                    before=original_src[:80],
                    after="data:image/png;base64,...",
                    details={
                        "picker": picker,
                        "images_scanned": images_scanned,
                        "format": "png",
                        "orig_bytes": orig_bytes_len,
                        "new_bytes": len(modified_bytes),
                        "brightness_delta": brightness_delta,
                        "pixel_shift": pixel_shift,
                    },
                )
            ],
        )

    def evaluate(self, html, url, change_log, extra_files):
        from app.techniques.base import EvaluationResult
        signals, issues = [], []
        soup = None

        data_img = False
        svg_recolor = False
        if html:
            from app.utils.html_utils import parse_html
            soup = parse_html(html)
            for tag in soup.find_all(["img", "link"]):
                src = tag.get("src") or tag.get("href") or ""
                if src.startswith("data:image/"):
                    data_img = True
            for tag in soup.find_all(["img", "link", "svg"]):
                style = tag.get("style") or ""
                if "hue-rotate" in style:
                    svg_recolor = True
                    break

        if data_img:
            signals.append("HTML has inline data:image URI (logo embedded)")
        elif svg_recolor:
            signals.append("HTML has CSS hue-rotate filter on img (SVG logo recolor applied)")
        else:
            issues.append("HTML has no data:image URI and no CSS hue-rotate filter")

        png_bytes = extra_files.get("images/modified_logo_0.png", b"")
        if len(png_bytes) > 50:
            signals.append(f"Modified logo PNG in extra_files ({len(png_bytes)} bytes)")
        else:
            issues.append("Modified logo PNG not found in extra_files")

        entry = next(
            (e for e in change_log if e.change_type in ("logo_pixel_edit", "logo_svg_recolor")), None
        )
        if entry:
            picker = entry.details.get("picker", "")
            fmt = entry.details.get("format", "")
            signals.append(f"change_log: picker={picker!r} format={fmt!r}")
        else:
            issues.append("No logo_pixel_edit or logo_svg_recolor in change_log")

        passed = (len(png_bytes) > 50) or svg_recolor or (data_img and entry is not None)
        return EvaluationResult(
            passed=passed,
            score=self._eval_score(signals, issues),
            signals=signals,
            issues=issues,
            details={"has_data_uri": data_img, "svg_recolor": svg_recolor, "png_bytes": len(png_bytes)},
        )
