"""Shared helper types and utilities."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class DetectionResult:
    """Standardised result returned by every detector.

    ``confidence`` is a heuristic class-confidence value, not a calibrated
    probability. ``calibrated`` stays False for the built-in forensic rules.
    """

    label: str
    confidence: float
    score: float
    details: Dict[str, float] = field(default_factory=dict)
    flags: List[str] = field(default_factory=list)
    method: str = "heuristic_forensics"
    calibrated: bool = False
    meta: Dict[str, Any] = field(default_factory=dict)
    limitations: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "confidence": round(self.confidence * 100, 2),
            "score": round(self.score, 4),
            "details": {k: round(v, 4) for k, v in self.details.items()},
            "flags": self.flags,
            "method": self.method,
            "calibrated": self.calibrated,
            "meta": self.meta,
            "limitations": self.limitations,
        }


def clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def softmax(values: List[float]) -> List[float]:
    mx = max(values)
    exps = [math.exp(v - mx) for v in values]
    total = sum(exps)
    return [e / total for e in exps]


def label_from_score(
    score: float,
    fake_thresh: float = 0.55,
    suspicious_thresh: float = 0.40,
) -> str:
    if score >= fake_thresh:
        return "FAKE"
    if score >= suspicious_thresh:
        return "SUSPICIOUS"
    return "REAL"


def class_confidence_from_score(
    score: float,
    *,
    fake_thresh: float = 0.55,
    suspicious_thresh: float = 0.40,
) -> float:
    """Heuristic confidence in the assigned band.

    This fixes the old behaviour where a SUSPICIOUS score near 0.54 could be
    reported with a misleadingly low ``1-score`` confidence.
    """
    score = clamp(score)
    if score >= fake_thresh:
        span = max(1e-9, 1.0 - fake_thresh)
        return clamp(0.5 + 0.5 * ((score - fake_thresh) / span))
    if score < suspicious_thresh:
        span = max(1e-9, suspicious_thresh)
        return clamp(0.5 + 0.5 * ((suspicious_thresh - score) / span))

    center = (fake_thresh + suspicious_thresh) / 2.0
    half = max(1e-9, (fake_thresh - suspicious_thresh) / 2.0)
    closeness = 1.0 - min(1.0, abs(score - center) / half)
    return clamp(0.5 + 0.5 * closeness)
