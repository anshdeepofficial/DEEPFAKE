"""Optional production-model gateway.

DeepGuard's built-in detectors are lightweight forensic heuristics. Operators can
attach a separately hosted trained model for each media modality without changing
the public API. The external service must accept multipart field ``file`` and
return JSON containing ``score`` in [0, 1], plus optional ``label``, ``details``
and ``model`` fields.

External forwarding is disabled unless both an endpoint is configured and
DEEPGUARD_ENABLE_EXTERNAL_MODELS=1. This avoids silently sending uploads away
from the DeepGuard server.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(slots=True)
class ModelEndpoint:
    modality: str
    url: str


class ModelGateway:
    def __init__(self, timeout_seconds: float = 30.0):
        self.timeout_seconds = timeout_seconds
        self.enabled = os.getenv("DEEPGUARD_ENABLE_EXTERNAL_MODELS", "0") == "1"
        self.token = os.getenv("DEEPGUARD_MODEL_TOKEN", "").strip()
        self.endpoints = {
            modality: os.getenv(f"DEEPGUARD_{modality.upper()}_MODEL_ENDPOINT", "").strip()
            for modality in ("image", "audio", "video")
        }

    def capabilities(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "configured": {
                modality: bool(url)
                for modality, url in self.endpoints.items()
            },
            "contract": "multipart:file -> JSON {score,label?,details?,model?}",
        }

    async def infer(
        self,
        modality: str,
        data: bytes,
        *,
        filename: str,
        content_type: str,
    ) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        endpoint = self.endpoints.get(modality, "")
        if not endpoint:
            return None

        headers: dict[str, str] = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        async with httpx.AsyncClient(
            timeout=self.timeout_seconds,
            follow_redirects=False,
            headers=headers,
        ) as client:
            response = await client.post(
                endpoint,
                files={"file": (filename, data, content_type)},
            )
            response.raise_for_status()
            payload = response.json()

        score = float(payload.get("score"))
        if not 0.0 <= score <= 1.0:
            raise ValueError("External model returned score outside [0, 1].")

        return {
            "score": round(score, 4),
            "label": str(payload.get("label") or "").strip() or None,
            "model": str(payload.get("model") or "external-model"),
            "details": payload.get("details") if isinstance(payload.get("details"), dict) else {},
        }
