"""
Audio forensic signal detector.

The built-in pipeline measures MFCC motion, spectral flatness, pitch variation
and silence structure. It is a lightweight triage signal, not a trained
anti-spoofing model or calibrated probability of human/synthetic origin.
"""
from __future__ import annotations

import hashlib
import io
import logging
import os
from typing import Tuple

import librosa
import numpy as np

from app.utils.helpers import (
    DetectionResult,
    class_confidence_from_score,
    clamp,
    label_from_score,
)

logger = logging.getLogger(__name__)

_MFCC_WEIGHT = 0.30
_FLAT_WEIGHT = 0.25
_PITCH_WEIGHT = 0.25
_SILENCE_WEIGHT = 0.20

_SR = 22_050
_HOP = 512
_MAX_SECONDS = max(5.0, float(os.getenv("DEEPGUARD_MAX_AUDIO_SECONDS", "60")))


class AudioDetector:
    """Stateless lightweight audio forensic analyser."""

    def analyze(self, audio_bytes: bytes) -> DetectionResult:
        try:
            y, sr = librosa.load(
                io.BytesIO(audio_bytes),
                sr=_SR,
                mono=True,
                duration=_MAX_SECONDS + 0.75,
            )
        except Exception as exc:
            logger.error("Cannot decode audio: %s", exc)
            return DetectionResult(
                label="ERROR",
                confidence=0.0,
                score=0.0,
                flags=["Could not decode audio file"],
                limitations=["No forensic conclusion was produced."],
            )

        if len(y) < _SR * 0.5:
            return DetectionResult(
                label="INSUFFICIENT_DATA",
                confidence=0.0,
                score=0.0,
                flags=["Audio too short (< 0.5 s) for analysis"],
                limitations=["Use a longer speech sample when possible."],
            )

        decoded_seconds = len(y) / float(sr)
        truncated = decoded_seconds > _MAX_SECONDS
        if truncated:
            y = y[: int(_MAX_SECONDS * sr)]

        mfcc_score, mfcc_val = self._mfcc_score(y, sr)
        flat_score, flat_val = self._spectral_flatness_score(y, sr)
        pitch_score, pitch_val = self._pitch_score(y, sr)
        silence_score, silence_val = self._silence_score(y, sr)

        composite = clamp(
            mfcc_score * _MFCC_WEIGHT
            + flat_score * _FLAT_WEIGHT
            + pitch_score * _PITCH_WEIGHT
            + silence_score * _SILENCE_WEIGHT
        )

        flags: list[str] = []
        if mfcc_score > 0.6:
            flags.append("MFCC trajectory is unusually smooth")
        if flat_score > 0.6:
            flags.append("Spectral flatness is elevated")
        if pitch_score > 0.6:
            flags.append("Pitch trajectory is unusually regular")
        if silence_score > 0.6:
            flags.append("Silence structure is atypical")
        if truncated:
            flags.append(f"Only the first {_MAX_SECONDS:g} seconds were analysed")

        label = label_from_score(composite)
        confidence = class_confidence_from_score(composite)

        return DetectionResult(
            label=label,
            confidence=confidence,
            score=composite,
            details={
                "mfcc_variance": mfcc_val,
                "spectral_flatness": flat_val,
                "pitch_consistency": pitch_val,
                "silence_ratio": silence_val,
            },
            flags=flags,
            method="audio_heuristic_forensics_v2",
            calibrated=False,
            meta={
                "sample_rate": sr,
                "analyzed_seconds": round(len(y) / float(sr), 3),
                "truncated": truncated,
                "sha256": hashlib.sha256(audio_bytes).hexdigest(),
            },
            limitations=[
                "Built-in audio scoring is not a trained anti-spoofing model.",
                "Codec, microphone, noise reduction and music can change these signals.",
            ],
        )

    @staticmethod
    def _mfcc_score(y: np.ndarray, sr: int) -> Tuple[float, float]:
        mfccs = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13, hop_length=_HOP)
        delta = np.diff(mfccs, axis=1)
        mean_var = float(np.mean(np.var(delta, axis=1)))
        return clamp(1.0 - (mean_var / 80.0)), mean_var

    @staticmethod
    def _spectral_flatness_score(y: np.ndarray, sr: int) -> Tuple[float, float]:
        del sr
        flatness = librosa.feature.spectral_flatness(y=y, hop_length=_HOP)[0]
        mean_flat = float(np.mean(flatness))
        return clamp(mean_flat / 0.15), mean_flat

    @staticmethod
    def _pitch_score(y: np.ndarray, sr: int) -> Tuple[float, float]:
        f0, _, _ = librosa.pyin(
            y,
            fmin=librosa.note_to_hz("C2"),
            fmax=librosa.note_to_hz("C7"),
            hop_length=_HOP,
        )
        voiced = f0[~np.isnan(f0)]
        if len(voiced) < 10:
            return 0.3, 0.0
        std_f0 = float(np.std(voiced))
        return clamp(1.0 - (std_f0 / 60.0)), std_f0

    @staticmethod
    def _silence_score(y: np.ndarray, sr: int) -> Tuple[float, float]:
        del sr
        rms = librosa.feature.rms(y=y, hop_length=_HOP)[0]
        threshold = float(np.percentile(rms, 20))
        silence_ratio = float(np.mean(rms < threshold * 1.5))
        return clamp((silence_ratio - 0.30) / 0.40), silence_ratio
