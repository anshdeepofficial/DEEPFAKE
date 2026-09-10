# DeepGuard Roadmap

## 1. Stable product foundation — implemented in v1.1

- FastAPI health/readiness endpoint
- streamed upload-size enforcement
- in-process rate limiting
- configurable CORS
- corrected PWA root scope/offline fallback handling
- Docker health check and dynamic `$PORT`
- Render Blueprint
- GitHub Actions CI
- Chromium Manifest V3 verification extension
- live public-web claim evidence endpoint with source links

## 2. Real image detector

Add a model adapter so DeepGuard can run a benchmarked pretrained image deepfake
classifier (preferably ONNX for portable CPU inference). Keep ELA/frequency/noise
signals as explainability, not as the primary probability. Evaluate on multiple
real-camera and generated-image datasets, plus re-compressed social-media images.

## 3. Real video detector + event provenance

- face-track extraction instead of only full-frame sampling
- temporal deepfake model
- key-frame generation
- perceptual hashes
- optional reverse-image/video-search provider adapters
- event date/location/entity extraction
- compare earliest-known sources and independent reporting
- return `synthetic-risk` and `context/provenance-risk` as separate results

This matters for flood/war/disaster videos: a real old video reused with a false
caption is misinformation even when no pixels were AI-generated.

## 4. Real audio anti-spoofing

Add a trained anti-spoof / synthetic-speech model and benchmark it across voice
cloning, TTS, codecs, phone recordings, background noise and multiple languages.
MFCC/pitch/spectral heuristics stay as secondary evidence.

## 5. Strong claim verification

The v1.1 verifier uses public search-result evidence and lightweight relevance /
stance rules. Upgrade it behind provider interfaces:

1. licensed search provider(s) for dependable web retrieval
2. article extraction and canonical URL de-duplication
3. publication date and source relationship detection
4. entity/date/number-aware claim decomposition
5. optional LLM/NLI model for source-grounded entailment/contradiction
6. citation-level answer generation where every conclusion links to evidence
7. confidence calibration and an explicit `INSUFFICIENT_EVIDENCE` state

The system must never turn absence of search results into proof that a claim is
false.

## 6. Browser extension product

- current page / selected text verification (v1.1 base exists)
- side-panel experience for longer investigations
- claim-by-claim article scan
- highlight sentences with evidence status
- one-click open-source comparison
- optional image/video capture from the current page for media analysis
- Chrome Web Store privacy disclosure and minimal permissions review

## 7. Production hardening

- Redis-backed distributed rate limiting when scaling to multiple workers
- queued video jobs for long media
- content-type magic-byte validation
- request IDs and structured logs
- metrics/alerts
- abuse controls
- retention policy and automatic temporary-file cleanup tests
- domain-specific CORS and trusted-host configuration
- reproducible benchmark reports in CI/releases
