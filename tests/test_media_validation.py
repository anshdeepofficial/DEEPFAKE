import io

from PIL import Image

from app.utils.media_validation import (
    MediaValidationError,
    sniff_media_kind,
    validate_image_dimensions,
    validate_upload_bytes,
)


def test_sniff_jpeg_and_wav():
    img = Image.new("RGB", (10, 10), "white")
    buf = io.BytesIO()
    img.save(buf, "JPEG")
    assert sniff_media_kind(buf.getvalue()) == "image"

    wav_header = b"RIFF" + b"\x00" * 4 + b"WAVE" + b"\x00" * 20
    assert sniff_media_kind(wav_header) == "audio"


def test_iso_bmff_is_accepted_for_audio_or_video():
    data = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 32
    assert sniff_media_kind(data) == "audio_or_video"
    validate_upload_bytes(data, "audio")
    validate_upload_bytes(data, "video")


def test_wrong_signature_is_rejected():
    try:
        validate_upload_bytes(b"not-a-media-file-at-all", "image")
    except MediaValidationError as exc:
        assert exc.status_code == 415
    else:
        raise AssertionError("invalid content was accepted")


def test_image_pixel_limit():
    img = Image.new("RGB", (100, 100), "white")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    assert validate_image_dimensions(buf.getvalue(), 20_000) == (100, 100)

    try:
        validate_image_dimensions(buf.getvalue(), 5_000)
    except MediaValidationError as exc:
        assert exc.status_code == 413
    else:
        raise AssertionError("oversized pixel count was accepted")
