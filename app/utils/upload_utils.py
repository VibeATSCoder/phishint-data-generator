"""Helpers for safely reading FastAPI UploadFile objects with a hard size cap.

The default Starlette/FastAPI behaviour is to buffer the whole upload into
memory (or a SpooledTemporaryFile) before the route handler sees it. We
still call `.read()`, but stream it in chunks so we can short-circuit
with HTTP 413 as soon as we cross the cap, rather than letting a 10 GB
upload finish and then rejecting it.
"""
from __future__ import annotations

from fastapi import HTTPException, UploadFile

DEFAULT_CHUNK = 1024 * 1024


async def read_with_cap(
    upload: UploadFile,
    cap_bytes: int,
    *,
    chunk_size: int = DEFAULT_CHUNK,
    field_name: str = "upload",
) -> bytes:
    """Read the upload but refuse anything larger than `cap_bytes`.

    Raises HTTPException(413) once accumulated bytes exceed the cap.
    Returns the full bytes when under the cap.
    """
    if cap_bytes <= 0:
        return await upload.read()

    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(chunk_size)
        if not chunk:
            break
        total += len(chunk)
        if total > cap_bytes:
            raise HTTPException(
                413,
                f"{field_name} exceeds size cap ({total} > {cap_bytes} bytes)",
            )
        chunks.append(chunk)
    return b"".join(chunks)
