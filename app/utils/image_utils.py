from __future__ import annotations

import base64
import io
from typing import TYPE_CHECKING

try:
    import httpx
    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False

try:
    from PIL import Image
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False


def image_to_data_uri(image_bytes: bytes, mime_type: str = "image/png") -> str:
    b64 = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime_type};base64,{b64}"


def fetch_image_bytes(url: str, timeout: float = 10.0) -> bytes | None:
    """Fetch raw image bytes from a URL; returns None on any failure."""
    if not _HTTPX_AVAILABLE:
        return None
    try:
        resp = httpx.get(url, timeout=timeout, follow_redirects=True)
        if resp.status_code == 200:
            return resp.content
    except Exception:
        pass
    return None


def pil_image_from_bytes(data: bytes) -> "Image.Image | None":
    if not _PIL_AVAILABLE:
        return None
    try:
        return Image.open(io.BytesIO(data)).convert("RGB")
    except Exception:
        return None


def pil_image_to_bytes(img: "Image.Image", fmt: str = "PNG") -> bytes:
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def get_image_mime(src: str) -> str:
    src_lower = src.lower()
    if src_lower.endswith(".jpg") or src_lower.endswith(".jpeg"):
        return "image/jpeg"
    if src_lower.endswith(".gif"):
        return "image/gif"
    if src_lower.endswith(".svg"):
        return "image/svg+xml"
    if src_lower.endswith(".webp"):
        return "image/webp"
    return "image/png"
