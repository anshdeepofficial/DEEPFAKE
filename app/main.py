"""DeepGuard – multimodal forensic analysis and live claim verification API."""
from __future__ import annotations

import logging
import os
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
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


def _homepage_html() -> str:
    """Serve the legacy UI with truthful v1.1 copy without duplicating the page."""
    page = (_static_dir / "index.html").read_text(encoding="utf-8")
    replacements = {
        "DeepGuard – Deepfake & Fake-News Detector": "DeepGuard – Media Forensics & Claim Verification",
        "AI-powered deepfake and fake-news detection. Analyse images, videos, audio and text for synthetic manipulation.": "Evidence-assisted media forensics and live web claim verification for images, video, audio and text.",
        "Multimodal AI-powered forensic analysis to stop fraud and fake news.": "Multimodal forensic signals plus source-backed public-web claim verification.",
        "v1.0 – Research Edition": "v1.1 – Research Edition",
        "AI-Powered Detection": "Evidence-Assisted Detection",
        "📰 Text / News": "📰 Text Signals",
        "Paste a news headline, article, social media post, or any text you want to verify for authenticity...": "Paste text to inspect writing-risk signals. For factual verification, use Verify Claim.",
        "Analyse Text": "Analyse Writing Signals",
        "NLP Credibility Scoring": "Text Risk Signals",
        "and structural red-flags are combined to produce a fake-news\n           probability score.": "and structural red-flags are combined into an explainable writing-risk\n           indicator. Writing style alone cannot prove a factual claim true or false.",
        "The platform operates entirely locally — no content is uploaded to\n         third-party servers — ensuring privacy and making it suitable for\n         sensitive investigations.": "Uploaded media is processed by your DeepGuard server and is not forwarded to third-party AI services by the core detectors.\n         Claim verification sends the claim text to a public search provider to retrieve evidence.",
        "✅ No cloud dependency — runs 100 % on-device": "✅ Self-hostable backend with transparent REST API",
        "https://github.com/Ansh200618/DEEPFAKE": "https://github.com/anshdeepofficial/DEEPFAKE",
    }
    for old, new in replacements.items():
        page = page.replace(old, new)
    page = page.replace(
        '<a href="/api/docs"  class="nav-link" target="_blank">API Docs</a>',
        '<a href="/verify" class="nav-link">Verify Claim</a>\n      <a href="/api/docs" class="nav-link" target="_blank">API Docs</a>',
    )
    return page


@app.get("/", include_in_schema=False, response_class=HTMLResponse)
async def index():
    return HTMLResponse(_homepage_html())


@app.get("/verify", include_in_schema=False)
async def verify_page():
    return FileResponse(str(_static_dir / "verify.html"))


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
