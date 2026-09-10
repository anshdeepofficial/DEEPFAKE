<div align="center">

# 🛡️ DeepGuard

**Multimodal deepfake & fake-news analysis for images, video, audio, and text.**

![Python](https://img.shields.io/badge/Python-Backend-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-API-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![PWA](https://img.shields.io/badge/PWA-Installable-5A0FC8?style=for-the-badge&logo=pwa&logoColor=white)
![Tests](https://img.shields.io/badge/Tests-34%20Passing-16A34A?style=for-the-badge)

<a href="https://github.com/sponsors/anshdeepofficial"><img src="https://img.shields.io/badge/Sponsor-%E2%9D%A4-EA4AAA?style=for-the-badge&logo=githubsponsors&logoColor=white" alt="Sponsor on GitHub" /></a>
<a href="https://buymeacoffee.com/anshdeepofficial"><img src="https://img.shields.io/badge/Buy%20Me%20a%20Coffee-Support-FFDD00?style=for-the-badge&logo=buymeacoffee&logoColor=000" alt="Buy Me a Coffee" /></a>

</div>

---

## ✨ Overview

DeepGuard is an AI-assisted forensic platform that analyzes multiple media types for suspicious manipulation signals. It combines image, video, audio, and text analysis behind a FastAPI backend and an installable Progressive Web App interface.

> **Important:** Results are probabilistic indicators, not legal proof. Human review is recommended for important decisions.

## 🔬 Detection Modes

| Input | Analysis Focus |
| --- | --- |
| 🖼️ Image | ELA, DCT/frequency patterns, noise residuals, face consistency |
| 🎬 Video | Frame analysis, optical flow, blink and face consistency signals |
| 🎙️ Audio | MFCC, spectral characteristics, pitch consistency, silence patterns |
| 📰 Text | Structural, readability, emotional, and clickbait-style indicators |

## 📸 Screenshots

| Home | Detection Result |
| --- | --- |
| ![Home](screenshots/screenshot_home.png) | ![Result](screenshots/screenshot_result_fake.png) |

| Text Analysis | Mobile PWA |
| --- | --- |
| ![Text](screenshots/screenshot_text_analysis.png) | ![Mobile](screenshots/screenshot_mobile.png) |

## 🚀 Quick Start

```bash
git clone https://github.com/anshdeepofficial/DEEPFAKE.git
cd DEEPFAKE
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Then open `http://localhost:8000` in your browser.

## 🛠️ Stack

- **Backend:** Python + FastAPI
- **Frontend:** HTML, CSS, JavaScript
- **App model:** Progressive Web App
- **Testing:** Pytest
- **Deployment options:** Docker and Linux systemd scripts included

## 🔌 API

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/api/health` | GET | Service health |
| `/api/detect/image` | POST | Image analysis |
| `/api/detect/video` | POST | Video analysis |
| `/api/detect/audio` | POST | Audio analysis |
| `/api/detect/text` | POST | Text/news analysis |
| `/api/docs` | GET | Swagger documentation |

## 📄 Research Paper

A detailed research document is included in the repository as **`DeepGuard_Research_Paper.docx`**, covering the system architecture, detection methodologies, implementation, experiments, ethics, and references.

## 🧪 Testing

```bash
pytest tests/ -v
```

The repository currently documents **34 passing tests** across detectors and API behavior.

## 🤝 Contributing

Contributions are welcome, especially around reproducible evaluation, stronger detection methods, test coverage, explainability, and responsible-use documentation.

## ⚖️ Disclaimer

DeepGuard should be treated as a research and awareness tool. Detection scores can produce false positives or false negatives and should not be used as the sole basis for legal, disciplinary, financial, or safety-critical decisions.

---

<div align="center">
Research project by <a href="https://github.com/anshdeepofficial">Anshdeep Singh</a>
</div>
