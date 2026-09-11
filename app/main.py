"""DeepGuard – media forensics and source-backed claim verification API."""
from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.detectors import AudioDetector, ImageDetector, TextDetector, VideoDetector
from app.models import ModelGateway
from app.utils.media_validation import (
    MediaValidationError,
    validate_image_dimensions,
    validate_upload_bytes,
)
from app.verifier import ClaimVerifier

logging.basicConfig(
    level=os.getenv("DEEPGUARD_LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)-8s %(name)s – %(message)s",
)
logger = logging.getLogger("deepguard")

VERSION = "1.2.0"

_image = ImageDetector()
_audio = AudioDetector()
_video = VideoDetector()
_text = TextDetector()
_verifier = ClaimVerifier(timeout_seconds=float(os.getenv("DEEPGUARD_SEARCH_TIMEOUT", "8")))
_models = ModelGateway(timeout_seconds=float(os.getenv("DEEPGUARD_MODEL_TIMEOUT", "30")))

app = FastAPI(
    title="DeepGuard",
    description="Media forensic signals and source-backed public-web claim verification",
    version=VERSION,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

_cors_raw = os.getenv(
    "DEEPGUARD_CORS_ORIGINS",
    "http://localhost:8000,http://127.0.0.1:8000",
)
_cors_origins = [x.strip() for x in _cors_raw.split(",") if x.strip()]
_cors_regex = os.getenv(
    "DEEPGUARD_CORS_ORIGIN_REGEX",
    r"^(chrome-extension|moz-extension)://.+$",
).strip() or None
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_origin_regex=_cors_regex,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Accept", "X-Request-ID"],
    expose_headers=["X-Request-ID", "X-Process-Time"],
    allow_credentials=False,
)

_trusted_hosts = [
    x.strip()
    for x in os.getenv("DEEPGUARD_TRUSTED_HOSTS", "*").split(",")
    if x.strip()
]
if _trusted_hosts != ["*"]:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=_trusted_hosts)

_static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

_MAX_BYTES = int(float(os.getenv("DEEPGUARD_MAX_UPLOAD_MB", "50")) * 1024 * 1024)
_MAX_IMAGE_PIXELS = max(
    1_000_000,
    int(float(os.getenv("DEEPGUARD_MAX_IMAGE_MEGAPIXELS", "25")) * 1_000_000),
)
_RATE_LIMIT = max(1, int(os.getenv("DEEPGUARD_RATE_LIMIT_PER_MIN", "30")))
_TRUST_PROXY = os.getenv("DEEPGUARD_TRUST_PROXY", "0") == "1"
_MAX_CONCURRENT_ANALYSES = max(
    1, int(os.getenv("DEEPGUARD_MAX_CONCURRENT_ANALYSES", "2"))
)
_analysis_slots = asyncio.Semaphore(_MAX_CONCURRENT_ANALYSES)
_rate_buckets: dict[str, deque[float]] = defaultdict(deque)


def _client_key(request: Request) -> str:
    if _TRUST_PROXY:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",", 1)[0].strip()[:128]
    return (request.client.host if request.client else "unknown")[:128]


@app.middleware("http")
async def request_controls(request: Request, call_next):
    start = time.perf_counter()
    request_id = request.headers.get("x-request-id", "").strip()[:80] or uuid.uuid4().hex

    if request.url.path.startswith("/api/") and request.url.path != "/api/health":
        key = _client_key(request)
        now = time.monotonic()
        bucket = _rate_buckets[key]
        while bucket and bucket[0] < now - 60:
            bucket.popleft()
        if not bucket and len(_rate_buckets) > 10_000:
            stale = [k for k, q in list(_rate_buckets.items())[:2000] if not q]
            for stale_key in stale:
                _rate_buckets.pop(stale_key, None)
        if len(bucket) >= _RATE_LIMIT:
            return JSONResponse(
                {"detail": "Rate limit exceeded. Try again shortly.", "request_id": request_id},
                status_code=429,
                headers={"Retry-After": "60", "X-Request-ID": request_id},
            )
        bucket.append(now)

    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time"] = f"{time.perf_counter() - start:.3f}s"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"

    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"

    if request.url.path.endswith(".html") or request.url.path in {"/", "/verify", "/privacy", "/terms"}:
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "img-src 'self' data: blob:; "
            "media-src 'self' blob:; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "script-src 'self' 'unsafe-inline'; "
            "connect-src 'self'; "
            "base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
        )

    if os.getenv("DEEPGUARD_HTTPS_ONLY", "0") == "1":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

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
            raise HTTPException(
                413,
                f"File exceeds {round(_MAX_BYTES / 1024 / 1024)} MB limit",
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _check_content_type(ct: str | None, allowed: set[str]):
    normalized = (ct or "").split(";")[0].strip().lower()
    if normalized and normalized not in allowed:
        raise HTTPException(415, f"Unsupported media type: {ct}")


def _validate_bytes(data: bytes, kind: str):
    try:
        validate_upload_bytes(data, kind)
        if kind == "image":
            validate_image_dimensions(data, _MAX_IMAGE_PIXELS)
    except MediaValidationError as exc:
        raise HTTPException(exc.status_code, exc.message) from exc


def _homepage_html() -> str:
    page = (_static_dir / "index.html").read_text(encoding="utf-8")
    replacements = {
        "DeepGuard – Deepfake & Fake-News Detector": "DeepGuard – Media Forensics & Claim Verification",
        "AI-powered deepfake and fake-news detection. Analyse images, videos, audio and text for synthetic manipulation.": "Evidence-assisted media forensics and live web claim verification for images, video, audio and text.",
        "Multimodal AI-powered forensic analysis to stop fraud and fake news.": "Multimodal forensic signals plus source-backed public-web claim verification.",
        "v1.0 – Research Edition": f"v{VERSION} – Research Edition",
        "AI-Powered Detection": "Evidence-Assisted Detection",
        "Install <strong>DeepGuard</strong> as an app for offline access": "Install <strong>DeepGuard</strong> for quick access",
        "🛡️ <strong>DeepGuard</strong> — Protecting truth with AI": "🛡️ <strong>DeepGuard</strong> — Media forensics & evidence verification",
        "📰 Text / News": "📰 Text Signals",
        "Paste a news headline, article, social media post, or any text you want to verify for authenticity...": "Paste text to inspect writing-risk signals. For factual verification, use Verify Claim.",
        "Analyse Text": "Analyse Writing Signals",
        "NLP Credibility Scoring": "Text Risk Signals",
        "and structural red-flags are combined to produce a fake-news\n           probability score.": "and structural red-flags are combined into an explainable writing-risk\n           indicator. Writing style alone cannot prove a factual claim true or false.",
        "The platform operates entirely locally — no content is uploaded to\n         third-party servers — ensuring privacy and making it suitable for\n         sensitive investigations.": "Uploaded media is processed by your DeepGuard server. Core heuristic detectors do not forward media to third-party AI services. Claim verification sends claim text to configured search/fact-check providers.",
        "✅ No cloud dependency — runs 100 % on-device": "✅ Self-hostable backend with transparent REST API",
        "https://github.com/Ansh200618/DEEPFAKE": "https://github.com/anshdeepofficial/DEEPFAKE",
    }
    for old, new in replacements.items():
        page = page.replace(old, new)

    page = page.replace(
        '<a href="/api/docs"  class="nav-link" target="_blank">API Docs</a>',
        '<a href="/verify" class="nav-link">Verify Claim</a>\n'
        '      <a href="/privacy" class="nav-link">Privacy</a>\n'
        '      <a href="/api/docs" class="nav-link" target="_blank">API Docs</a>',
    )
    page = page.replace(
        '<a href="/api/docs">API Docs</a>',
        '<a href="/api/docs">API Docs</a>\n'
        '      <a href="/privacy">Privacy</a>\n'
        '      <a href="/terms">Terms</a>',
    )
    return page


@app.get("/", include_in_schema=False, response_class=HTMLResponse)
async def index():
    return HTMLResponse(_homepage_html())


@app.get("/verify", include_in_schema=False)
async def verify_page():
    return FileResponse(str(_static_dir / "verify.html"))


@app.get("/privacy", include_in_schema=False)
async def privacy_page():
    return FileResponse(str(_static_dir / "privacy.html"))


@app.get("/terms", include_in_schema=False)
async def terms_page():
    return FileResponse(str(_static_dir / "terms.html"))


@app.get("/offline.html", include_in_schema=False)
async def offline():
    return FileResponse(str(_static_dir / "offline.html"))


@app.get("/robots.txt", include_in_schema=False)
async def robots():
    return PlainTextResponse("User-agent: *\nAllow: /\nDisallow: /api/\n")


@app.get("/sitemap.xml", include_in_schema=False)
async def sitemap(request: Request):
    base = str(request.base_url).rstrip("/")
    urls = "".join(
        f"<url><loc>{base}{path}</loc></url>"
        for path in ("/", "/verify", "/privacy", "/terms")
    )
    return HTMLResponse(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{urls}</urlset>",
        media_type="application/xml",
    )


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "version": VERSION,
        "modes": ["image", "video", "audio", "text-signals", "claim-verification"],
        "media_detectors": "heuristic_forensics",
        "claim_verification": _verifier.capabilities(),
        "external_models": _models.capabilities(),
    }


@app.get("/api/capabilities")
async def capabilities():
    return {
        "version": VERSION,
        "built_in": {
            "image": {
                "method": "ELA + frequency + noise + face luminance heuristics",
                "trained_model": False,
                "provenance": ["sha256", "perceptual_hash", "EXIF tag count"],
            },
            "audio": {
                "method": "MFCC + spectral flatness + pitch + silence heuristics",
                "trained_model": False,
                "max_analyzed_seconds": float(os.getenv("DEEPGUARD_MAX_AUDIO_SECONDS", "60")),
            },
            "video": {
                "method": "bounded frame forensics + optical flow + face/eye consistency",
                "trained_model": False,
                "max_analyzed_seconds": float(os.getenv("DEEPGUARD_MAX_VIDEO_SECONDS", "60")),
                "max_sampled_frames": int(os.getenv("DEEPGUARD_MAX_VIDEO_SAMPLES", "40")),
            },
            "text": {
                "method": "writing-style risk signals",
                "fact_checker": False,
            },
            "claim_verification": _verifier.capabilities(),
        },
        "optional": {
            "external_trained_models": _models.capabilities(),
        },
        "limits": {
            "max_upload_mb": round(_MAX_BYTES / 1024 / 1024, 2),
            "max_image_megapixels": round(_MAX_IMAGE_PIXELS / 1_000_000, 2),
            "max_concurrent_media_analyses": _MAX_CONCURRENT_ANALYSES,
        },
    }


async def _run_media_detector(
    modality: str,
    detector,
    data: bytes,
    *,
    filename: str,
    content_type: str,
) -> dict:
    async with _analysis_slots:
        result = await run_in_threadpool(detector.analyze, data)
    payload = result.to_dict()

    try:
        external = await _models.infer(
            modality,
            data,
            filename=filename,
            content_type=content_type,
        )
    except Exception as exc:
        logger.warning("External %s model failed: %s", modality, exc)
        external = {
            "error": "Configured external model was unavailable.",
        }

    payload["external_model"] = external
    if external and "score" in external:
        payload["recommended_review"] = (
            "Use the trained-model result together with the local forensic signals; "
            "do not treat either one as legal proof."
        )
    return payload


@app.post("/api/detect/image")
async def detect_image(file: UploadFile = File(...)):
    _check_content_type(file.content_type, {
        "image/jpeg", "image/png", "image/webp", "image/gif", "image/bmp", "image/tiff",
        "application/octet-stream",
    })
    data = await _read_upload(file)
    _validate_bytes(data, "image")
    payload = await _run_media_detector(
        "image",
        _image,
        data,
        filename=file.filename or "image.bin",
        content_type=file.content_type or "application/octet-stream",
    )
    return JSONResponse(payload)


@app.post("/api/detect/audio")
async def detect_audio(file: UploadFile = File(...)):
    _check_content_type(file.content_type, {
        "audio/mpeg", "audio/wav", "audio/ogg", "audio/flac", "audio/x-wav",
        "audio/mp3", "audio/x-m4a", "audio/aac", "audio/mp4", "audio/webm", "application/octet-stream",
    })
    data = await _read_upload(file)
    _validate_bytes(data, "audio")
    payload = await _run_media_detector(
        "audio",
        _audio,
        data,
        filename=file.filename or "audio.bin",
        content_type=file.content_type or "application/octet-stream",
    )
    return JSONResponse(payload)


@app.post("/api/detect/video")
async def detect_video(file: UploadFile = File(...)):
    _check_content_type(file.content_type, {
        "video/mp4", "video/mpeg", "video/webm", "video/ogg", "video/quicktime",
        "video/x-msvideo", "application/octet-stream",
    })
    data = await _read_upload(file)
    _validate_bytes(data, "video")
    payload = await _run_media_detector(
        "video",
        _video,
        data,
        filename=file.filename or "video.bin",
        content_type=file.content_type or "application/octet-stream",
    )
    return JSONResponse(payload)


class TextBody(BaseModel):
    text: str = Field(min_length=1, max_length=100_000)


@app.post("/api/detect/text")
async def detect_text(body: TextBody):
    if not body.text.strip():
        raise HTTPException(400, "text field must not be empty")
    async with _analysis_slots:
        result = await run_in_threadpool(_text.analyze, body.text)
    payload = result.to_dict()
    payload["purpose"] = "writing_style_risk_only"
    payload["fact_verification_endpoint"] = "/api/verify/claim"
    payload["limitations"] = list(dict.fromkeys([
        *payload.get("limitations", []),
        "Writing style cannot establish whether a factual claim is true or false.",
    ]))
    return JSONResponse(payload)


class VerifyBody(BaseModel):
    claim: str | None = Field(default=None, max_length=2_000)
    context_url: str | None = Field(default=None, max_length=2_000)
    page_title: str | None = Field(default=None, max_length=500)
    page_text: str | None = Field(default=None, max_length=12_000)


@app.post("/api/verify/claim")
async def verify_claim(body: VerifyBody):
    result = await _verifier.verify(
        body.claim,
        context_url=body.context_url,
        page_title=body.page_title,
        page_text=body.page_text,
    )
    return JSONResponse(result)
