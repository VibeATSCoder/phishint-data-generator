from __future__ import annotations

import base64
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

_BLOB_INJECT_TEMPLATE = """\
(function(){{
  var b64='{b64_png}';
  var bin=atob(b64);
  var arr=new Uint8Array(bin.length);
  for(var i=0;i<bin.length;i++)arr[i]=bin.charCodeAt(i);
  var blob=new Blob([arr],{{type:'image/png'}});
  var burl=URL.createObjectURL(blob);
  var img=document.createElement('img');
  img.src=burl;
  img.alt='Scan to continue';
  img.style.cssText='display:block;margin:8px auto;max-width:220px;border:1px solid #ccc;';
  var c=document.getElementById('__blob_qr_container__');
  if(c)c.appendChild(img);
}})();"""


class BlobQrTechnique(BaseTechnique):
    """
    T19 — Blob URI dynamic QR code generation (client-side delivery).

    Generates a real scannable QR code server-side, then injects it as a
    blob: URI via JavaScript so static network scanners never see the QR
    as a linked resource — only a transient createObjectURL reference.
    """

    TECHNIQUE_ID: ClassVar[int] = 19
    TECHNIQUE_NAME: ClassVar[str] = "Blob URI Dynamic QR (Client-side)"
    GROUP: ClassVar[TechniqueGroup] = TechniqueGroup.MULTISTAGE_DELIVERY
    CATEGORIES: ClassVar[list[Category]] = [Category.CREDENTIAL_THEFT, Category.BRAND_IMPERSONATION]
    REQUIREMENTS: ClassVar[list[Requirement]] = [Requirement.ALWAYS]
    DESCRIPTION: ClassVar[str] = (
        "Generates a real scannable QR code and injects it via createObjectURL "
        "so the QR image URL is a transient blob: URI. Network-based QR scanners "
        "see no static image URL; real users can scan it normally."
    )
    OPTION_SPECS: ClassVar[list[OptionSpec]] = [
        OptionSpec(
            name="target_url_override",
            description="URL to encode (blank = use phishing URL from chain)",
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
                        "blob_qr_skipped",
                        "qrcode library not installed; skipping blob QR generation",
                    )
                ],
            )

        raw = options.get("target_url_override", "") or url
        parsed, _ = parse_url(raw)
        target_url: str = rebuild_url(parsed)

        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=4,
        )
        qr.add_data(target_url)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png_bytes = buf.getvalue()
        b64_png = base64.b64encode(png_bytes).decode()

        qr_version = qr.version
        modules_per_side = qr.modules_count if hasattr(qr, "modules_count") else (
            len(qr.modules) if qr.modules else 0
        )
        if modules_per_side > 177:
            self.log("warning", "blob_qr_too_large", modules=modules_per_side)

        soup = parse_html(html)
        body = soup.find("body")
        if not body:
            body = soup.new_tag("body")
            html_tag = soup.find("html")
            if html_tag:
                html_tag.append(body)
            else:
                soup.append(body)

        from app.utils.i18n import t as _t
        lang = self._detect_lang(html, url)
        scan_label = _t("qr.scan_to_continue", lang)

        container = soup.new_tag(
            "div", id="__blob_qr_container__",
            style="text-align:center;padding:24px;",
        )
        if lang == "fa":
            container["dir"] = "rtl"
        p = soup.new_tag("p")
        p.string = scan_label + ":"
        container.append(p)

        noscript = soup.new_tag("noscript")
        data_uri = f"data:image/png;base64,{b64_png}"
        fallback_img = soup.new_tag(
            "img", src=data_uri, alt=scan_label,
            style="display:block;margin:8px auto;max-width:220px;border:1px solid #ccc;",
        )
        noscript.append(fallback_img)
        container.append(noscript)
        body.append(container)

        script = soup.new_tag("script")
        script.string = (
            "(function(){"
            "var ua=navigator.userAgent||'';"
            "var isSafari=/^((?!chrome|android).)*safari/i.test(ua);"
            "var b64='" + b64_png + "';"
            "var c=document.getElementById('__blob_qr_container__');"
            "if(!c) return;"
            "var img=document.createElement('img');"
            f"img.alt={scan_label!r};"
            "img.style.cssText='display:block;margin:8px auto;max-width:220px;border:1px solid #ccc;';"
            "if (isSafari) {"
            "  img.src='data:image/png;base64,'+b64;"
            "} else {"
            "  try {"
            "    var bin=atob(b64);var arr=new Uint8Array(bin.length);"
            "    for(var i=0;i<bin.length;i++)arr[i]=bin.charCodeAt(i);"
            "    var blob=new Blob([arr],{type:'image/png'});"
            "    img.src=URL.createObjectURL(blob);"
            "  } catch(e){ img.src='data:image/png;base64,'+b64; }"
            "}"
            "c.appendChild(img);"
            "})();"
        )
        body.append(script)

        self.log("info", "blob_qr_applied",
                 target_len=len(target_url), version=qr_version,
                 modules=modules_per_side, png_bytes=len(png_bytes))

        return ApplyResult(
            modified_html=serialize_html(soup),
            modified_url=None,
            extra_files={},
            change_log=[
                self._make_change(
                    "blob_qr_injected",
                    f"Injected blob+noscript QR for {target_url[:60]}",
                    details={
                        "qr_version": qr_version,
                        "modules_per_side": modules_per_side,
                        "blob_or_data": "blob_with_safari_fallback",
                        "noscript_fallback": True,
                        "png_bytes": len(png_bytes),
                    },
                )
            ],
        )

    def evaluate(self, html, url, change_log, extra_files):
        from app.techniques.base import EvaluationResult
        signals, issues = [], []

        has_container = html and "__blob_qr_container__" in html
        if has_container:
            signals.append("HTML has #__blob_qr_container__ div")
        else:
            issues.append("HTML missing #__blob_qr_container__ div")

        has_blob = html and "createObjectURL" in html
        has_b64_fallback = html and "data:image/png;base64," in html
        if has_blob:
            signals.append("HTML has createObjectURL() — blob URI QR delivery")
        else:
            issues.append("HTML missing createObjectURL() — blob QR delivery absent")
        if has_b64_fallback:
            signals.append("HTML has base64 data: URI fallback for Safari")

        has_noscript = html and "<noscript>" in html.lower()
        if has_noscript:
            signals.append("HTML has <noscript> fallback for QR display")
        else:
            issues.append("HTML missing <noscript> fallback")

        entry = next((e for e in change_log if e.change_type == "blob_qr_injected"), None)
        if entry:
            pb = entry.details.get("png_bytes", 0)
            ns = entry.details.get("noscript_fallback", False)
            if pb > 100:
                signals.append(f"change_log: png_bytes={pb}")
            else:
                issues.append(f"change_log png_bytes={pb}")
            if ns:
                signals.append("change_log: noscript_fallback=True")
        else:
            issues.append("No blob_qr_injected in change_log")

        passed = bool(has_container and (has_blob or has_b64_fallback))
        return EvaluationResult(
            passed=passed,
            score=self._eval_score(signals, issues),
            signals=signals,
            issues=issues,
            details={"has_container": has_container, "has_blob": has_blob, "has_noscript": has_noscript},
        )
