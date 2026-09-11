"""
Image forensic signal detector.

Built-in signals are lightweight heuristics (ELA, DCT/frequency energy, noise
residuals and face/background luminance consistency). They are useful for
triage, but they are not a trained modern deepfake classifier and should not be
treated as a calibrated probability of authenticity.
"""
from __future__ import annotations

import hashlib
import io
import logging
from typing import Tuple

import cv2
import numpy as np
from PIL import Image, ImageChops, ImageEnhance

from app.utils.helpers import (
    DetectionResult,
    class_confidence_from_score,
    clamp,
    label_from_score,
)

logger = logging.getLogger(__name__)

_ELA_WEIGHT = 0.35
_FREQ_WEIGHT = 0.30
_NOISE_WEIGHT = 0.20
_FACE_WEIGHT = 0.15
_JPEG_QUALITY = 90


class ImageDetector:
    """Stateless lightweight image forensic analyser."""

    _face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )

    def analyze(self, image_bytes: bytes) -> DetectionResult:
        try:
            with Image.open(io.BytesIO(image_bytes)) as source:
                source.load()
                original_format = (source.format or "unknown").upper()
                exif_count = len(source.getexif())
                pil_img = source.convert("RGB")
        except Exception as exc:
            logger.error("Cannot open image: %s", exc)
            return DetectionResult(
                label="ERROR",
                confidence=0.0,
                score=0.0,
                flags=["Could not decode image"],
                limitations=["No forensic conclusion was produced."],
            )

        cv_img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        height, width = cv_img.shape[:2]

        ela_score, ela_detail = self._ela_score(pil_img)
        freq_score, freq_detail = self._frequency_score(cv_img)
        noise_score, noise_detail = self._noise_score(cv_img)
        face_score, face_detail = self._face_consistency_score(cv_img)

        composite = clamp(
            ela_score * _ELA_WEIGHT
            + freq_score * _FREQ_WEIGHT
            + noise_score * _NOISE_WEIGHT
            + face_score * _FACE_WEIGHT
        )

        flags: list[str] = []
        if ela_score > 0.6:
            flags.append("High recompression variance; editing or repeated encoding may be present")
        if freq_score > 0.6:
            flags.append("Low high-frequency energy; this can occur in synthetic or heavily processed images")
        if noise_score > 0.6:
            flags.append("Noise residual is unusually inconsistent")
        if face_score > 0.6:
            flags.append("Face/background luminance differs strongly")

        label = label_from_score(composite)
        confidence = class_confidence_from_score(composite)

        return DetectionResult(
            label=label,
            confidence=confidence,
            score=composite,
            details={
                "ela": ela_detail,
                "frequency": freq_detail,
                "noise": noise_detail,
                "face_consistency": face_detail,
            },
            flags=flags,
            method="image_heuristic_forensics_v2",
            calibrated=False,
            meta={
                "width": width,
                "height": height,
                "megapixels": round((width * height) / 1_000_000, 3),
                "format": original_format,
                "exif_tag_count": exif_count,
                "sha256": hashlib.sha256(image_bytes).hexdigest(),
                "perceptual_hash": self._perceptual_hash(cv_img),
            },
            limitations=[
                "Built-in image scoring uses forensic heuristics, not a trained deepfake model.",
                "A real image can still be used with a false caption, date or location.",
            ],
        )

    @staticmethod
    def _perceptual_hash(cv_img: np.ndarray) -> str:
        """64-bit pHash-like fingerprint for later provenance comparisons."""
        gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
        small = cv2.resize(gray, (32, 32), interpolation=cv2.INTER_AREA).astype(np.float32)
        dct = cv2.dct(small)
        low = dct[:8, :8].flatten()
        median = float(np.median(low[1:])) if len(low) > 1 else 0.0
        bits = (low > median).astype(np.uint8)
        value = 0
        for bit in bits:
            value = (value << 1) | int(bit)
        return f"{value:016x}"

    @staticmethod
    def _ela_score(pil_img: Image.Image) -> Tuple[float, float]:
        buffer = io.BytesIO()
        pil_img.save(buffer, format="JPEG", quality=_JPEG_QUALITY)
        buffer.seek(0)
        recompressed = Image.open(buffer).convert("RGB")
        ela = ImageChops.difference(pil_img, recompressed)
        ela_arr = np.array(ImageEnhance.Brightness(ela).enhance(20)).astype(float)
        mean_val = float(np.mean(ela_arr))
        return clamp(mean_val / 40.0), mean_val

    @staticmethod
    def _frequency_score(cv_img: np.ndarray) -> Tuple[float, float]:
        gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY).astype(np.float32)
        dct = cv2.dct(gray)
        total_energy = float(np.sum(dct ** 2)) + 1e-9
        h, w = dct.shape
        hf_energy = float(np.sum(dct[h // 2:, w // 2:] ** 2))
        ratio = hf_energy / total_energy
        return clamp(1.0 - (ratio / 0.12)), ratio

    @staticmethod
    def _noise_score(cv_img: np.ndarray) -> Tuple[float, float]:
        gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY).astype(np.float32)
        blurred = cv2.medianBlur(gray.astype(np.uint8), 3).astype(np.float32)
        residual = np.abs(gray - blurred)
        std_val = float(np.std(residual))
        return clamp(std_val / 25.0), std_val

    def _face_consistency_score(self, cv_img: np.ndarray) -> Tuple[float, float]:
        gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
        faces = self._face_cascade.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30)
        )
        if len(faces) == 0:
            return 0.3, 0.0

        x, y, fw, fh = max(faces, key=lambda r: r[2] * r[3])
        face_region = cv_img[y:y + fh, x:x + fw]
        mask = np.ones(cv_img.shape[:2], dtype=bool)
        mask[y:y + fh, x:x + fw] = False
        background = cv_img[mask]

        face_lum = float(np.mean(cv2.cvtColor(face_region, cv2.COLOR_BGR2GRAY)))
        if background.size == 0:
            return 0.3, 0.0
        bg_lum = float(np.mean(cv2.cvtColor(
            background.reshape(-1, 1, 3), cv2.COLOR_BGR2GRAY
        )))
        delta = abs(face_lum - bg_lum)
        return clamp(delta / 80.0), delta
