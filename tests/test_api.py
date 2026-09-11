"""Integration tests for the FastAPI endpoints."""
import io
import math
import wave

import numpy as np
import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image

from app.main import app


def _jpeg_bytes(w=120, h=120) -> bytes:
    img = Image.new("RGB", (w, h), color=(80, 120, 200))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _wav_bytes(duration=2.0, sr=22050) -> bytes:
    n = int(sr * duration)
    t = np.linspace(0, duration, n, endpoint=False)
    samples = (
        np.sin(2 * math.pi * 440 * t) * 0.5
        + 0.05 * np.random.randn(n)
    ).astype(np.float32)
    samples = np.clip(samples, -1, 1)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes((samples * 32767).astype(np.int16).tobytes())
    return buf.getvalue()


@pytest.fixture
def transport():
    return ASGITransport(app=app)


@pytest.mark.asyncio
async def test_health(transport):
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["version"] == "1.2.0"
    assert data["media_detectors"] == "heuristic_forensics"


@pytest.mark.asyncio
async def test_capabilities_are_truthful(transport):
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/capabilities")
    assert resp.status_code == 200
    data = resp.json()
    assert data["built_in"]["image"]["trained_model"] is False
    assert data["built_in"]["audio"]["trained_model"] is False
    assert data["built_in"]["video"]["trained_model"] is False


@pytest.mark.asyncio
async def test_detect_image_ok(transport):
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/detect/image",
            files={"file": ("test.jpg", _jpeg_bytes(), "image/jpeg")},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert {"label", "confidence", "score", "details", "flags"} <= set(data)
    assert data["calibrated"] is False
    assert len(data["meta"]["sha256"]) == 64
    assert len(data["meta"]["perceptual_hash"]) == 16


@pytest.mark.asyncio
async def test_rejects_mime_spoofed_image(transport):
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/detect/image",
            files={"file": ("fake.jpg", b"this is not an image", "image/jpeg")},
        )
    assert resp.status_code in {415, 422}


@pytest.mark.asyncio
async def test_detect_text_ok(transport):
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/detect/text",
            json={"text": "SHOCKING secret exposed – share before deleted!! Corrupt "
                          "elites want you to stay silent about this one weird trick."},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["label"] in ("FAKE", "SUSPICIOUS", "REAL")
    assert data["purpose"] == "writing_style_risk_only"
    assert data["fact_verification_endpoint"] == "/api/verify/claim"


@pytest.mark.asyncio
async def test_detect_text_empty(transport):
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/detect/text", json={"text": "  "})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_detect_audio_ok(transport):
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/detect/audio",
            files={"file": ("test.wav", _wav_bytes(), "audio/wav")},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "label" in data
    assert data["calibrated"] is False
    assert data["meta"]["analyzed_seconds"] > 0


@pytest.mark.asyncio
async def test_privacy_and_terms_pages(transport):
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        privacy = await client.get("/privacy")
        terms = await client.get("/terms")
    assert privacy.status_code == 200
    assert "Claim verification" in privacy.text
    assert terms.status_code == 200
    assert "legal proof" in terms.text


@pytest.mark.asyncio
async def test_index_serves_html(transport):
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/")
    assert resp.status_code == 200
    assert "DeepGuard" in resp.text
    assert "Verify Claim" in resp.text
