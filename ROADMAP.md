# DeepGuard Roadmap

## Implemented by v1.2

### Product / deployment foundation
- FastAPI health and capabilities endpoints
- streamed upload-size enforcement
- magic/signature validation instead of MIME-only trust
- image decompression/pixel limit
- bounded audio duration
- bounded video duration, sample count and frame size
- CPU detector work moved off the async event loop
- bounded concurrent heavy analyses
- request IDs, rate limiting and security headers
- configurable CORS + browser-extension origin support
- optional trusted-host and HSTS controls
- Docker + Render Blueprint
- privacy and terms pages
- PWA shell caching without fake offline analysis
- dev/prod dependency split
- tests + coverage CI
- CodeQL
- Dependabot
- benchmark evaluation CLI

### Claim verification
- selected claim or bounded page claim extraction
- live public-web evidence retrieval
- independent-domain counting
- origin article excluded as independent corroboration
- support / contradiction / mixed / inconclusive states
- Unicode-aware query terms
- claim-kind classification
- verification questions for statements/promises/outcomes
- optional Google Fact Check Tools provider
- official/fact-check/general source typing
- evidence links shown in website and extension

### Browser extension
- Chromium Manifest V3
- selected-text verification
- bounded full-page claim extraction
- right-click “Verify with DeepGuard”
- server permission requested only for configured origin
- server health check before saving
- selected-text privacy improvement (no full article body)
- privacy/store-listing documentation
- packaged icon entry

### Media provenance foundation
- SHA-256 fingerprints for uploaded media
- perceptual image hash
- image dimensions/format/EXIF-count metadata
- video duration/resolution/sample metadata
- outputs explicitly marked uncalibrated when heuristic

### Trained-model integration foundation
- opt-in external model gateway for image/audio/video
- stable multipart input / score-output contract
- media is never forwarded unless operator explicitly enables it
- model integration and benchmark requirements documented

## Remaining production intelligence

These items require external weights, datasets, services or accounts and should
not be simulated.

### 1. Benchmarked trained media model pack
Deploy and validate production-grade:
- image synthetic/deepfake classifier
- audio anti-spoof / cloned-voice classifier
- temporal video deepfake classifier

For each model, document licence, weight checksum, preprocessing, datasets,
threshold calibration, false-positive rate and failure modes. Connect them using
`MODEL_INTEGRATION.md`.

### 2. Real provenance / reverse-search provider
For viral flood/war/disaster media, add a licensed or otherwise reliable provider
that can perform:
- reverse image / video-keyframe matching
- earliest-known source search
- canonical/source-chain grouping
- date/location/event matching

Return synthetic-media risk separately from context/provenance risk.

### 3. Reproducible production benchmarks
Acquire appropriate labelled datasets and use `scripts/evaluate_detector.py`
(or model-specific evaluation code) to publish:
- precision / recall / F1
- false-positive rate
- ROC/PR curves where applicable
- codec/social-media robustness
- unseen-generator/generalisation tests

### 4. Higher-end claim reasoning
After dependable retrieval is configured:
- canonical article extraction and publisher relationship detection
- publication-date timeline construction
- primary-source transcript/document matching
- source-grounded NLI/LLM entailment with citations
- promise → official notification → effective date → observed outcome timeline

Absence of search results must continue to mean `INCONCLUSIVE`, never “false”.

## Account/operator steps

- deploy the Render Blueprint (or another production host)
- optionally set `GOOGLE_FACT_CHECK_API_KEY`
- configure custom domain/DNS if desired
- configure exact CORS/trusted hosts after the final domain is known
- publish the extension through the browser-store account when ready
- configure external trained-model endpoints when the model pack is deployed
