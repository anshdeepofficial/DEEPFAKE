<div align="center">

# 🛡️ DeepGuard

**Media forensics + source-backed claim verification.**

</div>

DeepGuard is an open-source research platform for investigating suspicious
images, video, audio and factual claims. It combines bounded local forensic
signals with a live evidence-verification workflow and a browser extension.

> **Important:** the built-in image/audio/video detectors are heuristic forensic
> signals, not calibrated production deepfake models. DeepGuard must not be used
> as the sole basis for legal, disciplinary, financial or safety-critical action.

## Current v1.2 status

| Area | What works now |
| --- | --- |
| Image | ELA, frequency energy, noise residuals, face consistency, SHA-256, pHash, EXIF-count metadata |
| Video | Bounded/downscaled frame analysis, optical-flow consistency, face/eye signals, duration/sample limits |
| Audio | Bounded MFCC, spectral flatness, pitch and silence analysis |
| Text | Writing-style risk signals only; factual truth is handled separately |
| Claims | Live web evidence, optional Google Fact Check Tools lookup, source typing, support/contradiction signals, claim decomposition |
| Extension | Selected-text verification, full-page claim extraction, right-click context-menu verification, configurable server health check |
| Production | Rate limits, request IDs, security headers, upload signature checks, concurrency limits, CI, CodeQL, Dependabot, Render Blueprint |

## Browser extension

`browser_extension/` contains **DeepGuard Verify**, a Chromium Manifest V3
extension.

- Select text and click **Verify selected text**.
- Or right-click selected text and choose **Verify with DeepGuard**.
- Full-page mode reads a bounded visible article/main section and asks the server
  to extract a likely checkable claim.
- Selected-text mode does not send the full page body.

See:

- [`browser_extension/README.md`](browser_extension/README.md)
- [`browser_extension/PRIVACY.md`](browser_extension/PRIVACY.md)
- [`browser_extension/STORE_LISTING.md`](browser_extension/STORE_LISTING.md)

## API

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/api/health` | GET | Health/readiness and configured providers |
| `/api/capabilities` | GET | Truthful detector/model capabilities and limits |
| `/api/detect/image` | POST | Image forensic signals + provenance fingerprints |
| `/api/detect/video` | POST | Bounded video forensic analysis |
| `/api/detect/audio` | POST | Bounded audio forensic analysis |
| `/api/detect/text` | POST | Writing-style risk signals |
| `/api/verify/claim` | POST | Source-backed factual claim verification |
| `/api/docs` | GET | Swagger UI |

The claim endpoint returns `SUPPORTED`, `DISPUTED`, `MIXED` or `INCONCLUSIVE`
plus evidence URLs. Its `confidence` field is explicitly named
`evidence_strength`; it is not a mathematical probability that the claim is true.

## Claim verification providers

The zero-key bootstrap provider uses public DuckDuckGo HTML results. If the
server operator configures:

```text
GOOGLE_FACT_CHECK_API_KEY=<key>
```

DeepGuard also searches Google Fact Check Tools and marks those results
separately.

The verifier classifies the claim type (for example `attributed_promise`) and
returns questions such as:

- did the named person actually make the statement?
- was the promised action formally documented?
- after the effective date, was it actually implemented?

This supports the product direction where “what was said” and “what later
happened” are separate verification tasks.

## Run locally

```bash
git clone https://github.com/anshdeepofficial/DEEPFAKE.git
cd DEEPFAKE
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux/macOS
# source .venv/bin/activate

pip install -r requirements-dev.txt
pytest tests/ -q
uvicorn app.main:app --reload --port 8000
```

Open `http://localhost:8000`.

## Docker

```bash
docker compose up --build
```

## Deploy on Render

`render.yaml` is included.

1. Connect this GitHub repository to Render.
2. Create a Blueprint from the repository.
3. Deploy.
4. Confirm `/api/health` returns `"status": "ok"`.
5. Put the final HTTPS URL into the browser extension and press **Save**.

The included config uses one Uvicorn worker and bounded media analysis so small
instances are less likely to be exhausted. Heavy production trained models
should normally run as separate model services.

## Important configuration

| Variable | Default | Meaning |
| --- | ---: | --- |
| `DEEPGUARD_MAX_UPLOAD_MB` | `50` | Max uploaded file size |
| `DEEPGUARD_MAX_IMAGE_MEGAPIXELS` | `25` | Image decompression/pixel limit |
| `DEEPGUARD_MAX_AUDIO_SECONDS` | `60` | Max audio analysed |
| `DEEPGUARD_MAX_VIDEO_SECONDS` | `60` | Max video window analysed |
| `DEEPGUARD_MAX_VIDEO_SAMPLES` | `40` | Max sampled frames |
| `DEEPGUARD_MAX_VIDEO_DIMENSION` | `720` | Max sampled-frame dimension |
| `DEEPGUARD_MAX_CONCURRENT_ANALYSES` | `2` | Heavy media analyses in parallel |
| `DEEPGUARD_RATE_LIMIT_PER_MIN` | `30` | Per-client API requests |
| `DEEPGUARD_SEARCH_TIMEOUT` | `8` | Evidence-provider timeout |
| `DEEPGUARD_CORS_ORIGINS` | local URLs | Explicit web origins |
| `DEEPGUARD_CORS_ORIGIN_REGEX` | extension origins | Chrome/Firefox extension CORS |
| `DEEPGUARD_TRUSTED_HOSTS` | `*` | Optional trusted-host restriction |
| `DEEPGUARD_TRUST_PROXY` | `0` | Trust proxy client-IP header |
| `DEEPGUARD_HTTPS_ONLY` | `0` | Add HSTS header |
| `GOOGLE_FACT_CHECK_API_KEY` | empty | Optional Fact Check Tools integration |

## Optional trained model services

DeepGuard now has a stable external model gateway. It is disabled by default and
does not forward uploaded media unless explicitly enabled.

See [`MODEL_INTEGRATION.md`](MODEL_INTEGRATION.md).

This lets image/audio/video production models be deployed independently and
connected later without rewriting the website, extension or public detection
API.

## Evaluation

Unit tests test software behaviour, not detection accuracy.

Use [`scripts/evaluate_detector.py`](scripts/evaluate_detector.py) with a local
labelled `real/` + `fake/` dataset to calculate accuracy, precision, recall, F1,
specificity and a confusion matrix.

See [`EVALUATION.md`](EVALUATION.md).

## Privacy and responsible use

- `/privacy` documents default data flow and retention.
- `/terms` documents responsible-use limits.
- Media upload signatures are checked instead of trusting MIME headers alone.
- Image pixel count is bounded to reduce decompression-bomb risk.
- Audio/video compute is bounded.
- CPU-heavy detectors run off the FastAPI event loop.
- API results are marked uncalibrated where appropriate.
- Claim-search failure never becomes proof that a claim is false.
- External model forwarding is opt-in only.

## PWA

The UI shell can be cached for offline viewing. Analysis is never queued or
fabricated offline: media analysis and claim verification require a reachable
DeepGuard backend.

## Development / security

```bash
pip install -r requirements-dev.txt
pytest tests/ -q --cov=app
```

GitHub Actions runs syntax/manifest validation, tests, coverage and health smoke
checks. CodeQL and Dependabot are also configured.

See [`SECURITY.md`](SECURITY.md) and [`CONTRIBUTING.md`](CONTRIBUTING.md).

## What is still genuinely external

The repository is prepared for these, but they require resources that should not
be faked or silently bundled:

1. benchmarked production image/audio/video trained models and their weights;
2. labelled benchmark datasets for reproducible accuracy/calibration reports;
3. reliable licensed reverse-image/video search or provenance provider for
   earliest-source/date/location matching;
4. final hosting/domain and browser-store accounts.

See [`ROADMAP.md`](ROADMAP.md).

## Research paper

`DeepGuard_Research_Paper.docx` is the original research artifact and predates
some v1.2 production-hardening/extension work. Treat any accuracy claim as a
research claim unless it is backed by a reproducible benchmark in this repo.

## License

MIT — see [`LICENSE`](LICENSE).
