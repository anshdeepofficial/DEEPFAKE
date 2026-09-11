# Contributing

DeepGuard is a research-oriented project. Contributions are welcome when they
improve reproducibility, security, explainability, test coverage or real-world
validation.

## Local setup

```bash
python -m venv .venv
# activate the environment
pip install -r requirements-dev.txt
pytest tests/ -q
uvicorn app.main:app --reload --port 8000
```

## Pull requests

- Keep detector claims scientifically cautious.
- Do not label a heuristic as a trained AI model.
- Add tests for API or scoring changes.
- Do not commit model weights, private datasets, API keys or user uploads.
- Explain any new third-party service and its privacy impact.
- Prefer evidence links and calibrated uncertainty over absolute “true/false”
  claims.

## Trained models

Use the optional model gateway contract documented in `MODEL_INTEGRATION.md`.
Model licences, benchmark datasets and calibration results must be documented
before a model is promoted as a production detector.
