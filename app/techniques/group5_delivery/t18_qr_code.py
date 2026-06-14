from __future__ import annotations

import io
from typing import Any, ClassVar

from app.techniques.base import (
    ApplyResult, BaseTechnique, Category, OptionSpec, Requirement, TechniqueGroup,
)
from app.utils.html_utils import parse_html, serialize_html
from app.utils.url_utils import parse_url, rebuild_url

try:
    import qrcode
    import qrcode.constants
    _QR_OK = True
except ImportError:
    _QR_OK = False


class QrCodeTechnique(BaseTechnique):
    """
    T18 — QR code generation (Quishing) + ASCII QR codes.

    Generates a QR code pointing to the phishing URL and embeds it in the
    HTML as a data-URI image. Also produces a plain-text ASCII QR for
    embedding in emails/PDFs where images may be scanned.
    """

    TECHNIQUE_ID: ClassVar[int] = 18
    TECHNIQUE_NAME: ClassVar[str] = "QR Code (Quishing) Generation"
    GROUP: ClassVar[TechniqueGroup] = TechniqueGroup.MULTISTAGE_DELIVERY
    CATEGORIES: ClassVar[list[Category]] = [Category.CREDENTIAL_THEFT, Category.BRAND_IMPERSONATION]
    REQUIREMENTS: ClassVar[list[Requirement]] = [Requirement.ALWAYS]
    DESCRIPTION: ClassVar[str] = (
        "Generates a PNG QR code and ASCII QR code pointing to the phishing URL. "
        "QR codes in emails and PDFs bypass many link-scanning tools. "
        "The QR is embedded in the HTML as a data-URI."
    )
    _VALID_EC: ClassVar[set[str]] = {"L", "M", "Q", "H", "auto"}

    OPTION_SPECS: ClassVar[list[OptionSpec]] = [
        OptionSpec(
            name="error_correction",
            description="QR error correction: L, M, Q, H, or 'auto' (tuned by URL length)",
            type=str,
            default="auto",
        ),
        OptionSpec(
            name="include_ascii",
            description="Also generate ASCII text QR code",
            type=bool,
            default=True,
        ),
        OptionSpec(
            name="box_size",
            description="Pixels per QR module",
            type=int,
            default=10,
            min_value=4,
            max_value=30,
        ),
        OptionSpec(
            name="target_url_override",
            description="URL to encode in QR (blank = use phishing URL from chain)",
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
        if not _QR_OK:
            return ApplyResult(
                modified_html=None,
                modified_url=None,
                extra_files={},
                change_log=[
                    self._make_change(
                        "qr_skipped",
                        "qrcode library not installed; skipping QR generation",
                    )
                ],
            )

        parsed, _ = parse_url(options.get("target_url_override", "") or url)
        target_url: str = rebuild_url(parsed)
        ec_level: str = options.get("error_correction", "auto")
        include_ascii: bool = bool(options.get("include_ascii", True))
        box_size: int = int(options.get("box_size", 10))

        if ec_level not in self._VALID_EC:
            self.log("warning", "qr_bad_ec", requested=ec_level)
            return ApplyResult(
                modified_html=None, modified_url=None, extra_files={},
                change_log=[self._make_change(
                    "qr_skipped",
                    f"Unknown error_correction value: {ec_level!r}",
                    details={"reason": "bad_ec", "requested": ec_level},
                )],
            )

        if ec_level == "auto":
            n = len(target_url)
            if n <= 100:
                ec_level_effective = "H"
            elif n <= 250:
                ec_level_effective = "Q"
            else:
                ec_level_effective = "M"
        else:
            ec_level_effective = ec_level

        ec_const = getattr(
            qrcode.constants,
            f"ERROR_CORRECT_{ec_level_effective}",
            qrcode.constants.ERROR_CORRECT_M,
        )

        qr = qrcode.QRCode(
            version=None,
            error_correction=ec_const,
            box_size=box_size,
            border=4,
        )
        qr.add_data(target_url)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png_bytes = buf.getvalue()

        import base64
        data_uri = f"data:image/png;base64,{base64.b64encode(png_bytes).decode()}"

        soup = parse_html(html)
        body = soup.find("body")
        if body:
            qr_div = soup.new_tag("div", style="text-align:center;padding:24px;")
            qr_img = soup.new_tag(
                "img",
                src=data_uri,
                alt="Scan QR code to continue",
                style="max-width:200px;",
            )
            qr_div.append(qr_img)
            body.append(qr_div)

        extra_files: dict[str, bytes] = {
            "qr_code.png": png_bytes,
            "qr_url_for_email.txt": target_url.encode("utf-8"),
        }

        if include_ascii:
            qr.clear()
            qr.add_data(target_url)
            qr.make(fit=True)
            matrix = qr.modules
            ascii_lines: list[str] = []
            for i in range(0, len(matrix), 2):
                top = matrix[i]
                bot = matrix[i + 1] if i + 1 < len(matrix) else [False] * len(matrix[i])
                line = ""
                for t, b in zip(top, bot):
                    if t and b:
                        line += "\u2588"
                    elif t:
                        line += "\u2580"
                    elif b:
                        line += "\u2584"
                    else:
                        line += " "
                ascii_lines.append(line)
            ascii_qr = "\n".join(ascii_lines)
            extra_files["qr_ascii.txt"] = (
                f"QR Code for: {target_url}\n\n{ascii_qr}\n"
            ).encode("utf-8")

        ascii_lines_count = len(extra_files.get("qr_ascii.txt", b"").splitlines()) if include_ascii else 0
        self.log("info", "qr_applied",
                 url_len=len(target_url), ec=ec_level_effective,
                 png_bytes=len(png_bytes), ascii_lines=ascii_lines_count)

        return ApplyResult(
            modified_html=serialize_html(soup) if body else None,
            modified_url=None,
            extra_files=extra_files,
            change_log=[
                self._make_change(
                    "qr_code_generated",
                    f"QR code generated (EC={ec_level_effective}, ascii={include_ascii})",
                    after=target_url[:80],
                    details={
                        "target_url_len": len(target_url),
                        "ec_level_requested": ec_level,
                        "ec_level": ec_level_effective,
                        "png_bytes": len(png_bytes),
                        "ascii_lines": ascii_lines_count,
                    },
                )
            ],
        )

    def evaluate(self, html, url, change_log, extra_files):
        from app.techniques.base import EvaluationResult
        signals, issues = [], []

        has_qr_img = html and "data:image/png;base64," in html and "qr" in (html or "").lower()[:10000]
        if has_qr_img:
            signals.append("HTML has data:image/png QR code embedded")
        else:
            if html and "data:image/png;base64," in html:
                signals.append("HTML has data:image/png (may be QR)")
            else:
                issues.append("HTML missing data:image/png QR code")

        png_bytes = extra_files.get("qr_code.png", b"")
        if len(png_bytes) > 100 and png_bytes[:4] == b'\x89PNG':
            signals.append(f"qr_code.png in extra_files ({len(png_bytes)} bytes, valid PNG)")
        else:
            issues.append("qr_code.png missing or invalid in extra_files")

        entry = next((e for e in change_log if e.change_type == "qr_code_generated"), None)
        if entry:
            pb = entry.details.get("png_bytes", 0)
            if pb > 100:
                signals.append(f"change_log: png_bytes={pb}")
            else:
                issues.append(f"change_log png_bytes={pb} — too small")
        else:
            issues.append("No qr_code_generated in change_log")

        passed = len(png_bytes) > 100 and png_bytes[:4] == b'\x89PNG'
        return EvaluationResult(
            passed=passed,
            score=self._eval_score(signals, issues),
            signals=signals,
            issues=issues,
            details={"png_bytes": len(png_bytes), "has_data_uri": bool(has_qr_img)},
        )
