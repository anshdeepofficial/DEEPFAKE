"""DeepGuard – multimodal forensic analysis and live claim verification API."""
from __future__ import annotations

import logging
import os
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.detectors import AudioDetector, ImageDetector, TextDetector, VideoDetector
from app.verifier import ClaimVerifier

logging.basicConfig(
    level=os.getenv("DEEPGUARD_LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s  %(levelname)-8s  %(name)s – %(message)s",
)
logger = logging.getLogger("deepguard")

_image = ImageDetector()
_audio = AudioDetector()
_video = VideoDetector()
_text = TextDetector()
_verifier = ClaimVerifier(timeout_seconds=float(os.getenv("DEEPGUARD_SEARCH_TIMEOUT", "8")))

app = FastAPI(
    title="DeepGuard",
    description="Multimodal forensic analysis and public-web claim verification",
    version="1.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

_cors_raw = os.getenv("DEEPGUARD_CORS_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000")
_cors_origins = [x.strip() for x in _cors_raw.split(",") if x.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins or [],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Accept"],
    allow_credentials=False,
)

_static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

_MAX_BYTES = int(float(os.getenv("DEEPGUARD_MAX_UPLOAD_MB", "50")) * 1024 * 1024)
_RATE_LIMIT = max(1, int(os.getenv("DEEPGUARD_RATE_LIMIT_PER_MIN", "30")))
_rate_buckets: dict[str, deque[float]] = defaultdict(deque)


@app.middleware("http")
async def request_controls(request: Request, call_next):
    start = time.perf_counter()
    if request.url.path.startswith("/api/") and request.url.path != "/api/health":
        key = request.client.host if request.client else "unknown"
        now = time.monotonic()
        bucket = _rate_buckets[key]
        while bucket and bucket[0] < now - 60:
            bucket.popleft()
        if len(bucket) >= _RATE_LIMIT:
            return JSONResponse({"detail": "Rate limit exceeded. Try again shortly."}, status_code=429)
        bucket.append(now)

    response = await call_next(request)
    response.headers["X-Process-Time"] = f"{time.perf_counter() - start:.3f}s"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if request.url.path == "/static/sw.js":
        response.headers["Service-Worker-Allowed"] = "/"
    return response


async def _read_upload(upload: UploadFile) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > _MAX_BYTES:
            raise HTTPException(413, f"File exceeds {round(_MAX_BYTES / 1024 / 1024)} MB limit")
        chunks.append(chunk)
    return b"".join(chunks)


def _check_content_type(ct: str | None, allowed: set[str]):
    if ct and ct.split(";")[0].strip().lower() not in allowed:
        raise HTTPException(415, f"Unsupported media type: {ct}")


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(str(_static_dir / "index.html"))


@app.get("/offline.html", include_in_schema=False)
async def offline():
    return FileResponse(str(_static_dir / "offline.html"))


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "version": "1.1.0",
        "modes": ["image", "video", "audio", "text", "claim-verification"],
        "web_verification": "duckduckgo-html-bootstrap",
    }


@app.post("/api/detect/image")
async def detect_image(file: UploadFile = File(...)):
    _check_content_type(file.content_type, {
        "image/jpeg", "image/png", "image/webp", "image/gif", "image/bmp", "image/tiff"
    })
    result = _image.analyze(await _read_upload(file))
    return JSONResponse(result.to_dict())


@app.post("/api/detect/audio")
async def detect_audio(file: UploadFile = File(...)):
    _check_content_type(file.content_type, {
        "audio/mpeg", "audio/wav", "audio/ogg", "audio/flac", "audio/x-wav",
        "audio/mp3", "audio/x-m4a", "audio/aac", "application/octet-stream",
    })
    result = _audio.analyze(await _read_upload(file))
    return JSONResponse(result.to_dict())


@app.post("/api/detect/video")
async def detect_video(file: UploadFile = File(...)):
    _check_content_type(file.content_type, {
        "video/mp4", "video/mpeg", "video/webm", "video/ogg", "video/quicktime",
        "video/x-msvideo", "application/octet-stream",
    })
    result = _video.analyze(await _read_upload(file))
    return JSONResponse(result.to_dict())


class TextBody(BaseModel):
    text: str = Field(min_length=1, max_length=100_000)


@app.post("/api/detect/text")
async def detect_text(body: TextBody):
    if not body.text.strip():
        raise HTTPException(400, "text field must not be empty")
    return JSONResponse(_text.analyze(body.text).to_dict())


class VerifyBody(BaseModel):
    claim: str | None = Field(default=None, max_length=2_000)
    context_url: str | None = Field(default=None, max_length=2_000)
    page_title: str | None = Field(default=None, max_length=500)
    page_text: str | None = Field(default=None, max_length=25_000)


@app.post("/api/verify/claim")
async def verify_claim(body: VerifyBody):
    """Verify a factual claim against live public-web evidence."""
    result = await _verifier.verify(
        body.claim,
        context_url=body.context_url,
        page_title=body.page_title,
        page_text=body.page_text,
    )
    return JSONResponse(result)
