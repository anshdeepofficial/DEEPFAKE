# Evaluation guide

Passing unit tests proves that the software behaves as expected; it does **not**
prove deepfake-detection accuracy. Production claims need labelled benchmark
data.

DeepGuard includes `scripts/evaluate_detector.py` to evaluate the built-in
detectors on a local labelled dataset without uploading that dataset anywhere.

## Dataset layout

```text
dataset/
  real/
    sample-001.jpg
    ...
  fake/
    sample-002.jpg
    ...
```

Use the same layout for `image`, `audio` or `video` evaluation.

## Run

```bash
python scripts/evaluate_detector.py --modality image --dataset /path/to/dataset
python scripts/evaluate_detector.py --modality audio --dataset /path/to/dataset
python scripts/evaluate_detector.py --modality video --dataset /path/to/dataset
```

Optional:

```bash
python scripts/evaluate_detector.py \
  --modality image \
  --dataset /path/to/dataset \
  --threshold 0.55 \
  --json-out results.json
```

The script reports sample count, skipped/error count, accuracy, precision,
recall, F1, specificity and the confusion matrix.

## Production validation checklist

Evaluate on more than one source dataset, include common recompression/social
media transformations, separate in-distribution from unseen generators, report
false-positive rates, and test important language/codec/device conditions.

A detector should not be advertised with a single “accuracy” number unless the
dataset, split, threshold and confidence interval are documented.
