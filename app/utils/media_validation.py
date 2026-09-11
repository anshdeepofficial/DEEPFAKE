"""Lightweight upload validation helpers for DeepGuard."""
from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image, UnidentifiedImageError


@dataclass(slots=True)
class MediaValidationError(Exception):
    message: str
    status_code: int = 415

    def __str__(self) -> str:
        return self.message


def sniff_media_kind(data: bytes) -> str:
    """Return a coarse media kind from file signatures, never from the filename."""
    if len(data) < 12:
        return "unknown"

    head = data[:64]

    if head.startswith(b"\xff\xd8\xff"):
        return "image"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image"
    if head[:6] in {b"GIF87a", b"GIF89a"}:
        return "image"
    if head.startswith(b"BM"):
        return "image"
    if head[:4] in {b"II*\x00", b"MM\x00*"}:
        return "image"
    if head.startswith(b"RIFF") and head[8:12] == b"WEBP":
        return "image"

    if head.startswith(b"fLaC"):
        return "audio"
    if head.startswith(b"OggS"):
        return "audio_or_video"
    if head.startswith(b"ID3"):
        return "audio"
    if len(head) >= 2 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0:
        return "audio"
    if head.startswith(b"RIFF") and head[8:12] == b"WAVE":
        return "audio"

    if head[4:8] == b"ftyp":
        return "audio_or_video"

    if head.startswith(b"\x1aE\xdf\xa3"):
        return "audio_or_video"
    if head.startswith(b"RIFF") and head[8:12] == b"AVI ":
        return "video"
    if head.startswith(b"\x00\x00\x01\xba") or head.startswith(b"\x00\x00\x01\xb3"):
        return "video"

    return "unknown"


def validate_upload_bytes(data: bytes, expected_kind: str) -> str:
    if not data:
        raise MediaValidationError("Uploaded file is empty.", 400)

    actual = sniff_media_kind(data)
    allowed = {expected_kind}
    if expected_kind in {"audio", "video"}:
        allowed.add("audio_or_video")

    if actual not in allowed:
        raise MediaValidationError(
            f"File signature does not match an expected {expected_kind} file.", 415
        )
    return actual


def validate_image_dimensions(data: bytes, max_pixels: int) -> tuple[int, int]:
    """Decode only enough to validate image dimensions and decompression risk."""
    try:
        with Image.open(io.BytesIO(data)) as image:
            width, height = image.size
            if width <= 0 or height <= 0:
                raise MediaValidationError("Image has invalid dimensions.", 422)
            pixels = width * height
            if pixels > max_pixels:
                raise MediaValidationError(
                    f"Image is too large to analyse safely ({pixels:,} pixels; "
                    f"limit {max_pixels:,}).",
                    413,
                )
            image.verify()
            return width, height
    except MediaValidationError:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise MediaValidationError("Could not decode the uploaded image.", 422) from exc
