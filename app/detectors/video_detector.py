"""
Video forensic signal detector.

The built-in pipeline samples bounded, downscaled frames and measures image-level
forensic signals, optical-flow consistency, eye visibility and face presence.
These are research heuristics, not a trained temporal deepfake classifier.
"""
from __future__ import annotations

import hashlib
import logging
import math
import os
import tempfile
from typing import List, Tuple

import cv2
import numpy as np

from app.detectors.image_detector import ImageDetector
from app.utils.helpers import (
    DetectionResult,
    class_confidence_from_score,
    clamp,
    label_from_score,
)

logger = logging.getLogger(__name__)

_FRAME_WEIGHT = 0.40
_TEMPORAL_WEIGHT = 0.30
_BLINK_WEIGHT = 0.15
_FACE_RATIO_WT = 0.15

_MAX_SECONDS = max(5.0, float(os.getenv("DEEPGUARD_MAX_VIDEO_SECONDS", "60")))
_MAX_SAMPLES = max(4, int(os.getenv("DEEPGUARD_MAX_VIDEO_SAMPLES", "40")))
_MAX_DIMENSION = max(240, int(os.getenv("DEEPGUARD_MAX_VIDEO_DIMENSION", "720")))

_image_detector = ImageDetector()


class VideoDetector:
    """Stateless bounded video forensic analyser."""

    _face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
    _eye_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_eye.xml"
    )

    def analyze(self, video_bytes: bytes) -> DetectionResult:
        with tempfile.NamedTemporaryFile(suffix=".media", delete=False) as tmp:
            tmp.write(video_bytes)
            tmp_path = tmp.name
        try:
            return self._analyze_file(tmp_path, source_hash=hashlib.sha256(video_bytes).hexdigest())
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    def _analyze_file(self, path: str, *, source_hash: str) -> DetectionResult:
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            return DetectionResult(
                label="ERROR",
                confidence=0.0,
                score=0.0,
                flags=["Could not open video file"],
                limitations=["No forensic conclusion was produced."],
            )

        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        source_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        source_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)

        estimated_duration = (
            frame_count / fps if fps > 0.01 and frame_count > 0 else 0.0
        )
        effective_frames = frame_count
        if fps > 0.01:
            effective_frames = min(
                frame_count if frame_count > 0 else int(_MAX_SECONDS * fps),
                max(1, int(_MAX_SECONDS * fps)),
            )
        sample_step = max(1, math.ceil(effective_frames / _MAX_SAMPLES)) if effective_frames else 8

        frames: List[np.ndarray] = []
        idx = 0
        last_time_seconds = 0.0
        while len(frames) < _MAX_SAMPLES:
            ok, frame = cap.read()
            if not ok:
                break

            if fps > 0.01:
                last_time_seconds = idx / fps
                if last_time_seconds > _MAX_SECONDS:
                    break
            elif idx > _MAX_SAMPLES * sample_step:
                break

            if idx % sample_step == 0:
                frames.append(self._downscale(frame))
            idx += 1

        cap.release()

        if len(frames) < 2:
            return DetectionResult(
                label="INSUFFICIENT_DATA",
                confidence=0.0,
                score=0.0,
                flags=["Video is too short or could not provide enough frames"],
                meta={
                    "source_width": source_width,
                    "source_height": source_height,
                    "fps": round(fps, 3),
                    "estimated_duration_seconds": round(estimated_duration, 3),
                    "sha256": source_hash,
                },
                limitations=["Use a longer, decodable video sample."],
            )

        frame_score, frame_val = self._per_frame_score(frames)
        temporal_score, temporal_val = self._temporal_score(frames)
        blink_score, blink_val = self._blink_score(frames)
        face_ratio_score, face_ratio = self._face_ratio_score(frames)

        composite = clamp(
            frame_score * _FRAME_WEIGHT
            + temporal_score * _TEMPORAL_WEIGHT
            + blink_score * _BLINK_WEIGHT
            + face_ratio_score * _FACE_RATIO_WT
        )

        flags: list[str] = []
        if frame_score > 0.55:
            flags.append("Multiple sampled frames show elevated image-forensic signals")
        if temporal_score > 0.55:
            flags.append("Motion consistency varies strongly between sampled frames")
        if blink_score > 0.55:
            flags.append("Eye-visibility pattern is atypical")
        if face_ratio_score > 0.55:
            flags.append("Face presence changes inconsistently across sampled frames")

        truncated = bool(estimated_duration and estimated_duration > _MAX_SECONDS)
        if truncated:
            flags.append(f"Only the first {_MAX_SECONDS:g} seconds were considered")

        label = label_from_score(composite)
        confidence = class_confidence_from_score(composite)

        return DetectionResult(
            label=label,
            confidence=confidence,
            score=composite,
            details={
                "frame_score": frame_val,
                "temporal_score": temporal_val,
                "eye_visibility_rate": blink_val,
                "face_ratio": face_ratio,
                "frames_analyzed": float(len(frames)),
            },
            flags=flags,
            method="video_heuristic_forensics_v2",
            calibrated=False,
            meta={
                "source_width": source_width,
                "source_height": source_height,
                "fps": round(fps, 3),
                "estimated_duration_seconds": round(estimated_duration, 3),
                "frames_analyzed": len(frames),
                "sample_step": sample_step,
                "max_sample_dimension": _MAX_DIMENSION,
                "truncated": truncated,
                "sha256": source_hash,
            },
            limitations=[
                "Built-in video scoring is not a trained temporal deepfake model.",
                "Eye detection is not the same as measuring real blink events.",
                "A genuine video can still be paired with a false date, place or caption.",
            ],
        )

    @staticmethod
    def _downscale(frame: np.ndarray) -> np.ndarray:
        h, w = frame.shape[:2]
        longest = max(h, w)
        if longest <= _MAX_DIMENSION:
            return frame
        scale = _MAX_DIMENSION / float(longest)
        return cv2.resize(
            frame,
            (max(1, int(w * scale)), max(1, int(h * scale))),
            interpolation=cv2.INTER_AREA,
        )

    @staticmethod
    def _per_frame_score(frames: List[np.ndarray]) -> Tuple[float, float]:
        scores = []
        for frame in frames:
            ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
            if not ok:
                continue
            result = _image_detector.analyze(buf.tobytes())
            if result.label not in {"ERROR", "INSUFFICIENT_DATA"}:
                scores.append(result.score)
        if not scores:
            return 0.3, 0.3
        mean = float(np.mean(scores))
        return clamp(mean), mean

    def _temporal_score(self, frames: List[np.ndarray]) -> Tuple[float, float]:
        flow_mags: List[float] = []
        prev_gray = cv2.cvtColor(frames[0], cv2.COLOR_BGR2GRAY)
        for frame in frames[1:]:
            curr_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            flow = cv2.calcOpticalFlowFarneback(
                prev_gray,
                curr_gray,
                None,
                pyr_scale=0.5,
                levels=3,
                winsize=15,
                iterations=3,
                poly_n=5,
                poly_sigma=1.2,
                flags=0,
            )
            mag, _ = cv2.cartToPolar(flow[..., 0], flow[..., 1])
            flow_mags.append(float(np.mean(mag)))
            prev_gray = curr_gray

        if not flow_mags:
            return 0.3, 0.0

        mean_flow = float(np.mean(flow_mags))
        std_flow = float(np.std(flow_mags))
        cv_flow = std_flow / (mean_flow + 1e-9)
        return clamp(cv_flow / 2.0), cv_flow

    def _blink_score(self, frames: List[np.ndarray]) -> Tuple[float, float]:
        eye_detected = 0
        face_detected = 0
        for frame in frames:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = self._face_cascade.detectMultiScale(gray, 1.1, 5, minSize=(40, 40))
            if len(faces) == 0:
                continue
            face_detected += 1
            x, y, fw, fh = max(faces, key=lambda r: r[2] * r[3])
            roi = gray[y:y + fh, x:x + fw]
            eyes = self._eye_cascade.detectMultiScale(roi, 1.1, 3)
            if len(eyes) > 0:
                eye_detected += 1

        if face_detected == 0:
            return 0.3, 1.0

        eye_rate = eye_detected / face_detected
        deviation = abs(eye_rate - 0.80)
        return clamp(deviation / 0.40), eye_rate

    def _face_ratio_score(self, frames: List[np.ndarray]) -> Tuple[float, float]:
        has_face: List[int] = []
        for frame in frames:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = self._face_cascade.detectMultiScale(gray, 1.1, 5, minSize=(40, 40))
            has_face.append(1 if len(faces) > 0 else 0)

        ratio = float(np.mean(has_face))
        variance = float(np.var(has_face))
        return clamp(variance * 3.0), ratio
