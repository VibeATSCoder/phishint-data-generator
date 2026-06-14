from __future__ import annotations

import io
import struct
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
    from PIL import Image
    _PIL_OK = True
except ImportError:
    _PIL_OK = False


class SteganographyTechnique(BaseTechnique):
    """
    T24 — Steganography: hidden payload embedded in images.

    Uses LSB (Least Significant Bit) steganography to hide a text payload
    inside the pixels of an image on the page. The image looks identical
    to humans but carries hidden data that bypasses content scanners.
    """

    TECHNIQUE_ID: ClassVar[int] = 24
    TECHNIQUE_NAME: ClassVar[str] = "LSB Steganography in Images"
    GROUP: ClassVar[TechniqueGroup] = TechniqueGroup.ADVANCED_AI
    CATEGORIES: ClassVar[list[Category]] = [Category.MALWARE_DISTRIBUTION]
    REQUIREMENTS: ClassVar[list[Requirement]] = [Requirement.HAS_IMAGES]
    DESCRIPTION: ClassVar[str] = (
        "Hides a text payload inside image pixels using LSB steganography. "
        "The image appears identical to humans but carries hidden data that "
        "content-scanning tools miss."
    )
    OPTION_SPECS: ClassVar[list[OptionSpec]] = [
        OptionSpec(
            name="payload",
            description="Text payload to hide inside the image",
            type=str,
            default="phish_marker_v1",
        ),
        OptionSpec(
            name="target_image_index",
            description="0-based index of the <img> to use as carrier",
            type=int,
            default=0,
            min_value=0,
            max_value=99,
        ),
        OptionSpec(
            name="channel",
            description="Colour channel to use: 'red', 'green', or 'blue'",
            type=str,
            default="blue",
        ),
        OptionSpec(
            name="bits_per_pixel",
            description="LSB bits to use per channel per pixel (1–4)",
            type=int,
            default=1,
            min_value=1,
            max_value=4,
        ),
        OptionSpec(
            name="base_url",
            description="Base URL for resolving relative image src paths",
            type=str,
            default="",
        ),
    ]

    _CHANNEL_MAP = {"red": 0, "green": 1, "blue": 2}

    def apply(
        self,
        html: str,
        url: str,
        options: dict[str, Any],
        screenshot_bytes: bytes | None = None,
    ) -> ApplyResult:
        if not _PIL_OK:
            return ApplyResult(
                modified_html=None, modified_url=None, extra_files={},
                change_log=[self._make_change("stego_skipped", "Pillow not installed")]
            )

        payload: str = options.get("payload", "phish_marker_v1")
        target_idx: int = int(options.get("target_image_index", 0))
        channel_name: str = options.get("channel", "blue")
        bpp: int = int(options.get("bits_per_pixel", 1))
        base_url: str = options.get("base_url", "") or url

        channel_idx = self._CHANNEL_MAP.get(channel_name, 2)

        soup = parse_html(html)
        images = soup.find_all("img", src=True)

        if not images:
            self.log("warning", "stego_skip", reason="no_images")
            return ApplyResult(
                modified_html=None, modified_url=None, extra_files={},
                change_log=[self._make_change(
                    "stego_skipped", "No <img> tags in page",
                    details={"reason": "no_images"},
                )]
            )

        payload_bytes_len = len(payload.encode("utf-8")) + 4
        required_bits = payload_bytes_len * 8

        carrier_idx = -1
        pil_img = None
        carrier_dims = ""
        capacity_bytes = 0
        truncated = False

        order = list(range(target_idx, len(images))) + list(range(0, target_idx))
        _MAX_NET_FETCHES = 5
        net_fetches = 0
        for idx in order:
            img_tag = images[idx]
            src = img_tag["src"]
            if src.startswith("data:"):
                raw = self._decode_data_uri(src)
            else:
                if net_fetches >= _MAX_NET_FETCHES:
                    break
                abs_src = urllib.parse.urljoin(base_url, src)
                raw = fetch_image_bytes(abs_src)
                net_fetches += 1
            if not raw:
                continue
            candidate = pil_image_from_bytes(raw)
            if candidate is None:
                continue
            w, h = candidate.size
            pixels = w * h
            cap_bits = pixels * bpp
            if cap_bits >= required_bits:
                pil_img = candidate
                carrier_idx = idx
                carrier_dims = f"{w}x{h}"
                capacity_bytes = cap_bits // 8
                break
            self.log("info", "stego_capacity_check",
                     idx=idx, dims=f"{w}x{h}", capacity=cap_bits // 8,
                     required=payload_bytes_len)

        if pil_img is None:
            net_fetches = 0
            for idx in order:
                img_tag = images[idx]
                src = img_tag["src"]
                if src.startswith("data:"):
                    raw = self._decode_data_uri(src)
                else:
                    if net_fetches >= _MAX_NET_FETCHES:
                        break
                    raw = fetch_image_bytes(urllib.parse.urljoin(base_url, src))
                    net_fetches += 1
                if not raw:
                    continue
                candidate = pil_image_from_bytes(raw)
                if candidate is not None:
                    pil_img = candidate
                    carrier_idx = idx
                    w, h = candidate.size
                    carrier_dims = f"{w}x{h}"
                    capacity_bytes = (w * h * bpp) // 8
                    truncated = True
                    break

        if pil_img is None:
            self.log("warning", "stego_skip", reason="no_decodable_image")
            return ApplyResult(
                modified_html=None, modified_url=None, extra_files={},
                change_log=[self._make_change(
                    "stego_skipped", "No decodable image found",
                    details={"reason": "no_decodable_image"},
                )]
            )

        img_tag = images[carrier_idx]
        effective_payload = payload
        if truncated:
            max_payload_bytes = max(0, capacity_bytes - 4)
            effective_payload = payload.encode("utf-8")[:max_payload_bytes].decode("utf-8", errors="ignore")
            self.log("warning", "stego_payload_truncated",
                     original=len(payload), kept=len(effective_payload))

        alpha = None
        if pil_img.mode == "RGBA":
            alpha = pil_img.split()[-1]
            pil_img = pil_img.convert("RGB")

        stego_img = self._embed_lsb(pil_img, effective_payload, channel_idx, bpp)
        if alpha is not None:
            stego_img.putalpha(alpha)

        stego_bytes = pil_image_to_bytes(stego_img, "PNG")
        data_uri = image_to_data_uri(stego_bytes, "image/png")
        img_tag["src"] = data_uri

        self.log("info", "stego_applied",
                 carrier_idx=carrier_idx, dims=carrier_dims,
                 capacity=capacity_bytes, payload=len(effective_payload),
                 channel=channel_name, bpp=bpp, truncated=truncated)

        return ApplyResult(
            modified_html=serialize_html(soup),
            modified_url=None,
            extra_files={"images/stego_carrier.png": stego_bytes},
            change_log=[
                self._make_change(
                    "stego_embedded",
                    f"LSB payload hidden in img[{carrier_idx}] "
                    f"channel={channel_name} bpp={bpp}"
                    + (" (TRUNCATED)" if truncated else ""),
                    after=f"payload length={len(effective_payload)} chars",
                    details={
                        "carrier_idx": carrier_idx,
                        "carrier_dims": carrier_dims,
                        "capacity_bytes": capacity_bytes,
                        "payload_bytes": len(effective_payload),
                        "channel": channel_name,
                        "bpp": bpp,
                        "truncated": truncated,
                    },
                )
            ],
        )

    def evaluate(self, html, url, change_log, extra_files):
        from app.techniques.base import EvaluationResult
        signals, issues = [], []

        has_data_img = html and "data:image/" in html
        if has_data_img:
            signals.append("HTML has inline data:image URI (stego carrier)")
        else:
            issues.append("HTML missing inline data:image URI")

        stego_png = extra_files.get("images/stego_carrier.png", b"")
        if len(stego_png) > 100:
            signals.append(f"stego_carrier.png in extra_files ({len(stego_png)} bytes)")
        else:
            issues.append("stego_carrier.png missing or empty")

        entry = next((e for e in change_log if e.change_type == "stego_embedded"), None)
        payload_recovered = None
        if len(stego_png) > 100:
            channel = entry.details.get("channel", "blue") if entry else "blue"
            bpp = int(entry.details.get("bpp", 1)) if entry else 1
            try:
                payload_recovered = self.extract_payload(stego_png, channel=channel, bpp=bpp)
            except Exception:
                payload_recovered = None
            if payload_recovered:
                signals.append(f"Payload extracted from PNG: {payload_recovered[:40]!r}")
            else:
                issues.append("Could not extract payload from carrier PNG (may be PIL-unavailable)")

        if entry:
            channel = entry.details.get("channel", "?")
            bpp = entry.details.get("bpp", 0)
            capacity = entry.details.get("capacity_bytes", 0)
            signals.append(f"change_log: channel={channel!r} bpp={bpp} capacity={capacity}B")
        else:
            issues.append("No stego_embedded entry in change_log (supplementary check)")

        passed = has_data_img and len(stego_png) > 100
        return EvaluationResult(
            passed=passed,
            score=self._eval_score(signals, issues),
            signals=signals,
            issues=issues,
            details={
                "stego_png_bytes": len(stego_png),
                "payload_recovered": payload_recovered[:40] if payload_recovered else None,
            },
        )

    def extract_payload(
        self, image_bytes: bytes, channel: str = "blue", bpp: int = 1,
    ) -> str | None:
        """Companion to apply() — recover the embedded payload from a carrier
        image produced with the same channel/bpp. Returns None on failure."""
        if not _PIL_OK:
            return None
        pil = pil_image_from_bytes(image_bytes)
        if pil is None:
            return None
        if pil.mode == "RGBA":
            pil = pil.convert("RGB")
        channel_idx = self._CHANNEL_MAP.get(channel, 2)
        mask = (1 << bpp) - 1
        pixels = list(pil.getdata())
        bits: list[int] = []
        for px in pixels:
            if len(px) <= channel_idx:
                continue
            group = px[channel_idx] & mask
            for shift in range(bpp - 1, -1, -1):
                bits.append((group >> shift) & 1)
                if len(bits) >= 32 + 8 * (1 << 24):
                    break
        def _bits_to_bytes(bs: list[int]) -> bytes:
            out = bytearray()
            for i in range(0, len(bs) - 7, 8):
                byte = 0
                for j in range(8):
                    byte = (byte << 1) | bs[i + j]
                out.append(byte)
            return bytes(out)

        head_bits = bits[:32]
        if len(head_bits) < 32:
            return None
        length = struct.unpack(">I", _bits_to_bytes(head_bits))[0]
        needed_bits = length * 8
        body_bits = bits[32:32 + needed_bits]
        if len(body_bits) < needed_bits:
            return None
        try:
            return _bits_to_bytes(body_bits).decode("utf-8", errors="replace")
        except Exception:
            return None

    def _embed_lsb(
        self, img: "Image.Image", payload: str, channel: int, bpp: int
    ) -> "Image.Image":
        pixels = list(img.getdata())
        payload_bytes = payload.encode("utf-8")
        header = struct.pack(">I", len(payload_bytes))
        data = header + payload_bytes

        bits: list[int] = []
        for byte in data:
            for shift in range(7, -1, -1):
                bits.append((byte >> shift) & 1)

        mask = (1 << bpp) - 1
        bit_groups = [
            sum(bits[i + j] << (bpp - 1 - j) for j in range(bpp) if i + j < len(bits))
            for i in range(0, len(bits), bpp)
        ]

        new_pixels = list(pixels)
        for i, group in enumerate(bit_groups):
            if i >= len(new_pixels):
                break
            px = list(new_pixels[i])
            if len(px) > channel:
                px[channel] = (px[channel] & ~mask) | (group & mask)
                new_pixels[i] = tuple(px)

        out = Image.new(img.mode, img.size)
        out.putdata(new_pixels)
        return out

    def _decode_data_uri(self, src: str) -> bytes | None:
        import base64
        try:
            _, data = src.split(",", 1)
            return base64.b64decode(data)
        except Exception:
            return None
