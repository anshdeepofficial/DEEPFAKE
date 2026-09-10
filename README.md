<div align="center">

# 🛡️ DeepGuard

**Multimodal synthetic-media analysis + live web-evidence verification.**

</div>

DeepGuard is an open-source research platform for investigating suspicious images,
video, audio and text. Version 1.1 also includes a browser-extension workflow that
can pick a claim from the current webpage, search for independent public-web
evidence, and return the supporting/contradicting sources for human review.

> **Important:** DeepGuard is an evidence-assistance and research tool. Its current
> media detectors use forensic heuristics and are **not** a calibrated production
> deepfake model. A result is not legal proof and should not be the sole basis for
> safety, disciplinary, financial or legal decisions.

## What works today

| Input | Current analysis |
| --- | --- |
| Image | ELA, DCT/frequency patterns, noise residuals, face consistency |
| Video | Sampled-frame analysis, optical-flow consistency, face/eye signals |
| Audio | MFCC, spectral flatness, pitch consistency and silence patterns |
| Text | Writing-risk indicators such as clickbait, emotion and structure |
| Web claim | Live public-web search, relevance scoring, source diversity and evidence links |

The text detector and web claim verifier are deliberately separate: writing style
cannot prove whether a factual statement is true.

## Browser extension

`browser_extension/` contains a Chromium Manifest V3 extension called **DeepGuard
Verify**. When the user clicks it, the extension uses temporary `activeTab` access
to read either the selected sentence or a bounded amount of visible page text.
It then calls `/api/verify/claim` and displays the evidence sources.

See [`browser_extension/README.md`](browser_extension/README.md) for local loading
instructions.

## API

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/api/health` | GET | Health/readiness check |
| `/api/detect/image` | POST | Image forensic analysis |
| `/api/detect/video` | POST | Video forensic analysis |
| `/api/detect/audio` | POST | Audio forensic analysis |
| `/api/detect/text` | POST | Text writing-risk analysis |
| `/api/verify/claim` | POST | Verify a selected factual claim against live web evidence |
| `/api/docs` | GET | Swagger UI |

Example claim request:

```json
{
  "claim": "The ministry announced petrol prices will decrease by 5 percent from Monday.",
  "context_url": "https://example.com/article",
  "page_title": "Fuel price announcement"
}
```

The response contains an evidence-oriented verdict (`SUPPORTED`, `DISPUTED`,
`MIXED`, or `INCONCLUSIVE`) plus the source URLs used. The originating article's
domain is not allowed to independently corroborate itself.

## Run locally

```bash
git clone https://github.com/anshdeepofficial/DEEPFAKE.git
cd DEEPFAKE
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Open `http://localhost:8000`.

## Docker

```bash
docker compose up --build
```

The container exposes port `8000`, uses one worker by default to reduce memory
pressure, and has a health check at `/api/health`.

## Deploy on Render

A `render.yaml` Blueprint is included. Connect this repository to Render and use
the Blueprint, or create a Python Web Service manually with:

- Build: `pip install -r requirements.txt`
- Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1`
- Health check: `/api/health`

After deployment, put the HTTPS Render URL into the browser extension and press
**Save**. The extension requests permission only for that configured HTTPS origin.

## Configuration

| Environment variable | Default | Meaning |
| --- | --- | --- |
| `DEEPGUARD_MAX_UPLOAD_MB` | `50` | Maximum uploaded media size |
| `DEEPGUARD_RATE_LIMIT_PER_MIN` | `30` | Per-client API requests per minute |
| `DEEPGUARD_SEARCH_TIMEOUT` | `8` | Public-web search timeout in seconds |
| `DEEPGUARD_CORS_ORIGINS` | local URLs | Extra browser origins allowed to call the API |
| `DEEPGUARD_LOG_LEVEL` | `INFO` | Python logging level |
| `WEB_CONCURRENCY` | `1` | Docker Uvicorn worker count |

## PWA

The existing Progressive Web App remains available. DeepGuard now serves the
service worker with the root-scope permission header and provides a root
`/offline.html` fallback, fixing the previous scope/fallback mismatch.

Offline mode only covers the UI shell. Detection and live claim verification
still require the DeepGuard backend to be running; web verification also requires
outbound internet access from that backend.

## Tests and CI

```bash
pytest tests/ -q
```

GitHub Actions runs the complete test suite plus an application import/health
smoke test on every push to `main` and on pull requests.

## Security / privacy notes

- Upload size is enforced while reading the stream instead of only after the full
  file is accepted into memory.
- API calls are rate limited in-process to reduce accidental/anonymous abuse.
- Media is analyzed by your DeepGuard server; core detectors do not forward the
  uploaded media to third-party AI services.
- Claim verification sends the claim text to a public search provider to find
  evidence. Do not use it for confidential claims without understanding that.
- Search failure returns `SEARCH_UNAVAILABLE`; DeepGuard does not fabricate
  evidence when retrieval fails.

## Current limitation and model roadmap

The current image/audio/video outputs are heuristic forensic indicators. The next
major model phase is to add benchmarked pretrained detectors behind stable model
adapters, evaluate them on real/AI datasets, calibrate probabilities, and combine
them with the existing explainable forensic signals. For real-world flood/event
videos and images, a second provenance/context layer is also needed: key-frame
extraction, reverse-search/provider integration, date/location checks, source
history, and cross-source corroboration.

See [`ROADMAP.md`](ROADMAP.md) for the planned architecture.

## Research paper

`DeepGuard_Research_Paper.docx` is included as the original project research
artifact. Treat any accuracy or capability claims in documentation as research
claims unless they are backed by a reproducible benchmark in this repository.

## License

MIT License — see [`LICENSE`](LICENSE).
