# Trained model integration

DeepGuard v1.2 keeps lightweight local forensic heuristics enabled by default.
For real production detection, image/audio/video trained models should be run as
separately versioned model services and connected through the built-in gateway.

This separation keeps the web/API layer stable while allowing model weights,
GPU dependencies and licences to evolve independently.

## Enable a model service

Set:

```text
DEEPGUARD_ENABLE_EXTERNAL_MODELS=1
DEEPGUARD_IMAGE_MODEL_ENDPOINT=https://model-host/image
DEEPGUARD_AUDIO_MODEL_ENDPOINT=https://model-host/audio
DEEPGUARD_VIDEO_MODEL_ENDPOINT=https://model-host/video
DEEPGUARD_MODEL_TOKEN=<optional bearer token>
```

Only configure modalities you actually operate.

## HTTP contract

DeepGuard sends:

```text
POST <configured endpoint>
Content-Type: multipart/form-data
field name: file
```

The service returns:

```json
{
  "score": 0.83,
  "label": "LIKELY_SYNTHETIC",
  "model": "your-model-name-and-version",
  "details": {
    "optional": "model-specific evidence"
  }
}
```

`score` must be between 0 and 1. DeepGuard returns this result separately from
the local heuristic result; it does not silently average unrelated models.

## Before calling a model production-ready

Document the model licence, weight source/checksum, preprocessing, supported
media types, benchmark datasets, threshold calibration, false-positive rate,
known failure modes and privacy implications.
