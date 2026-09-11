#!/usr/bin/env python3
"""Evaluate a DeepGuard detector against a local labelled dataset."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.detectors import AudioDetector, ImageDetector, VideoDetector

EXTENSIONS = {
    "image": {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"},
    "audio": {".wav", ".mp3", ".ogg", ".flac", ".m4a", ".aac"},
    "video": {".mp4", ".webm", ".mov", ".avi", ".mpeg", ".mpg"},
}


def detector_for(modality: str):
    return {
        "image": ImageDetector,
        "audio": AudioDetector,
        "video": VideoDetector,
    }[modality]()


def collect(folder: Path, modality: str) -> list[Path]:
    allowed = EXTENSIONS[modality]
    return sorted(
        p for p in folder.rglob("*")
        if p.is_file() and p.suffix.lower() in allowed
    )


def safe_div(a: int, b: int) -> float:
    return a / b if b else 0.0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--modality", choices=sorted(EXTENSIONS), required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--threshold", type=float, default=0.55)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()

    if not 0.0 <= args.threshold <= 1.0:
        parser.error("--threshold must be between 0 and 1")

    real_dir = args.dataset / "real"
    fake_dir = args.dataset / "fake"
    if not real_dir.is_dir() or not fake_dir.is_dir():
        parser.error("dataset must contain real/ and fake/ directories")

    detector = detector_for(args.modality)
    samples = [(p, 0) for p in collect(real_dir, args.modality)]
    samples += [(p, 1) for p in collect(fake_dir, args.modality)]
    if not samples:
        parser.error("no supported files found")

    tp = tn = fp = fn = skipped = 0
    rows = []

    for path, truth in samples:
        try:
            result = detector.analyze(path.read_bytes())
        except Exception as exc:
            skipped += 1
            rows.append({"file": str(path), "error": str(exc)})
            continue

        if result.label in {"ERROR", "INSUFFICIENT_DATA", "LIMIT_EXCEEDED"}:
            skipped += 1
            rows.append({"file": str(path), "label": result.label})
            continue

        pred = 1 if result.score >= args.threshold else 0
        if truth == 1 and pred == 1:
            tp += 1
        elif truth == 0 and pred == 0:
            tn += 1
        elif truth == 0 and pred == 1:
            fp += 1
        else:
            fn += 1

        rows.append({
            "file": str(path),
            "truth": "fake" if truth else "real",
            "score": round(float(result.score), 6),
            "predicted": "fake" if pred else "real",
        })

    evaluated = tp + tn + fp + fn
    precision = safe_div(tp, tp + fp)
    recall = safe_div(tp, tp + fn)
    specificity = safe_div(tn, tn + fp)
    f1 = safe_div(2 * precision * recall, precision + recall)

    report = {
        "modality": args.modality,
        "threshold": args.threshold,
        "total_files": len(samples),
        "evaluated": evaluated,
        "skipped": skipped,
        "metrics": {
            "accuracy": round(safe_div(tp + tn, evaluated), 6),
            "precision": round(precision, 6),
            "recall": round(recall, 6),
            "f1": round(f1, 6),
            "specificity": round(specificity, 6),
        },
        "confusion_matrix": {"tp": tp, "tn": tn, "fp": fp, "fn": fn},
    }

    print(json.dumps(report, indent=2))
    if args.json_out:
        args.json_out.write_text(
            json.dumps({**report, "samples": rows}, indent=2),
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
