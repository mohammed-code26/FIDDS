# FIDDS

**Fraudulent Identity & Document Detecting System**

An AI-based assistive screening pipeline for identity and travel documents. Runs five independent analyses on an uploaded document, fuses their signals into a single explainable risk score, and always recommends human review — never an automated decision.

---

## Table of Contents

- [What It Does](#what-it-does)
- [Pipeline Architecture](#pipeline-architecture)
- [The Five Modules](#the-five-modules)
- [Explainable Risk Engine](#explainable-risk-engine)
- [Technology Stack](#technology-stack)
- [Quick Start](#quick-start)
- [API Reference](#api-reference)
- [Project Structure](#project-structure)
- [Design Principles](#design-principles)
- [Limitations](#limitations)
- [Future Scope](#future-scope)
- [License](#license)

---

## What It Does

Identity verification at checkpoints, borders, and service desks is slow, inconsistent, and vulnerable to modern forgery. FIDDS is an **assistive screening tool** for authorized personnel. It:

- Extracts structured fields from a document image (OCR + MRZ)
- Validates those fields against formal rules
- Analyzes the image for manipulation signatures
- Verifies a live face against the document photo
- Combines all signals into a **single 0-100 risk score** with attributed reasons
- Produces an **audit record** per session

**FIDDS never claims a document is fraudulent. Every high-risk case is flagged as `MANUAL REVIEW REQUIRED`, not an automatic rejection.**

---

## Pipeline Architecture

```
        Upload (document + optional selfie)
                       │
                       ▼
      ┌─────────────────────────────────┐
      │   FastAPI Backend (Python 3.11) │
      │   Router: /api/analyze          │
      └──┬──────┬──────┬──────┬─────────┘
         │      │      │      │
         ▼      ▼      ▼      ▼
       ┌───┐ ┌─────┐ ┌────┐ ┌────┐
       │OCR│ │Valid│ │Tamp│ │Face│
       └─┬─┘ └──┬──┘ └─┬──┘ └─┬──┘
         │      │      │      │
         └──────┴──────┴──────┘
                  │
                  ▼
         ┌────────────────┐
         │  Risk Engine   │
         │ (weighted 0-100)│
         └────────┬───────┘
                  ▼
       Explainable Result + Audit
```

Each module is an independent Python file in `modules/`. Modules never call each other — the API orchestrates. The risk engine consumes only the structured outputs.

---

## The Five Modules

### 1. OCR + MRZ Extraction (`modules/ocr/`)

- **Tesseract** full-image OCR for printed text
- **PassportEye** for MRZ (Machine Readable Zone) detection
- **Tesseract fallback** for MRZ when PassportEye fails on unusual layouts
- **Field parser** extracts `passport_number`, `surname`, `given_names`, `dob`, `expiry`, `nationality`

Every extracted field carries a **source label**:

- `mrz_anchored` — parsed cleanly from MRZ
- `reocr_verified` — recovered from ROI, checksum-validated
- `viz` — extracted from printed text via label anchoring
- `reocr_unverified` — recovered but not checksum-validated

### 2. Validation Rules Engine (`modules/validation/`)

Ten independent rules across five categories:

| ID | Rule | Category |
|---|---|---|
| R001 | Passport number format | Format |
| R002 | Nationality ISO-3166 code | Format |
| R003 | Required fields present | Completeness |
| R004 | DOB is in the past | Date logic |
| R005 | DOB plausible (0-120 yrs) | Date logic |
| R006 | Expiry is in the future | Date logic |
| R007 | Expiry after DOB | Consistency |
| R008 | MRZ number check digit | Checksum |
| R009 | MRZ alignment succeeded | Integrity |
| R010 | Field provenance trust | Trust |

The MRZ check-digit algorithm is implemented from the **ICAO 9303 specification**.

### 3. Tampering / Forensic Analysis (`modules/tampering/`)

Four independent detectors, weighted fusion:

| ID | Detector | Weight |
|---|---|---|
| T1 | Error Level Analysis | 0.35 |
| T2 | Metadata inspection (EXIF) | 0.15 |
| T3 | JPEG grid consistency | 0.25 |
| T4 | Noise variance | 0.25 |

Output: 0-100 tampering score with per-detector reasons.

### 4. Face Verification (`modules/face/`)

- **dlib** 128-dimensional face embeddings via `face_recognition`
- Similarity computed as `1 - face_distance`
- **Verdicts:** MATCH (≥ 0.55) · POSSIBLE MATCH (≥ 0.45) · NO MATCH · UNABLE TO VERIFY

Handles no-face, multiple-face, and low-quality-input cases gracefully.

### 5. Risk Engine (`modules/risk/`)

Weighted fusion:

```
risk_score = 0.30 × validation
           + 0.30 × tampering
           + 0.25 × face
           + 0.15 × ocr_quality
```

**Risk levels:**

| Range | Level | Recommendation |
|---|---|---|
| 0-30 | LOW | CLEAR FOR FURTHER PROCESSING |
| 31-60 | MEDIUM | MANUAL REVIEW RECOMMENDED |
| 61-100 | HIGH | MANUAL REVIEW REQUIRED |

All weights and thresholds are configurable — no hardcoded magic numbers.

---

## Explainable Risk Engine

Every risk score comes with a **reason list**, attributed to its source module:

```json
"risk": {
  "risk_score": 42,
  "risk_level": "MEDIUM",
  "recommendation": "MANUAL REVIEW RECOMMENDED",
  "reasons": [
    {"source": "validation", "severity": "warning",  "text": "R009 MRZ alignment failed."},
    {"source": "tampering",  "severity": "warning",  "text": "T1 ELA shows localized high-error regions."},
    {"source": "face",       "severity": "warning",  "text": "Face could not be verified."},
    {"source": "ocr",        "severity": "info",     "text": "Low OCR confidence (58%)."}
  ],
  "disclaimer": "This risk indicator is an assistive signal only..."
}
```

Not a black box. Every decision is auditable.

---

## Technology Stack

| Layer | Component | Version |
|---|---|---|
| Language | Python | 3.11+ |
| Web framework | FastAPI | 0.115+ |
| ASGI server | Uvicorn | 0.32+ |
| OCR engine | Tesseract | 5.x |
| OCR binding | pytesseract | 0.3+ |
| MRZ | PassportEye | 4.x |
| Image processing | OpenCV | 4.10+ |
| Image I/O | Pillow | 11.x |
| Face detection | dlib | 19.24+ |
| Face library | face_recognition | 1.3+ |
| Numeric | NumPy | 1.26+ |
| Frontend | Bootstrap | 5.3+ |
| Templates | Jinja2 | 3.1+ |

**Deployment characteristics:**

- CPU-only — no GPU required
- Peak RAM: ~1.5 GB during analysis
- Analysis time: ~8-12 seconds per document on an i5-6300U

---

## Quick Start

### Prerequisites

- Python 3.11+
- Tesseract OCR binary installed
- C++ build tools (for dlib — required on Windows)

### Installation

```bash
git clone https://github.com/YOURUSERNAME/FIDDS.git
cd FIDDS
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt
```

### Install Tesseract

**Windows:** Download from [UB-Mannheim](https://github.com/UB-Mannheim/tesseract/wiki) and install to `C:\Program Files\Tesseract-OCR`. Update `config/config.py` if installed elsewhere.

**macOS:** `brew install tesseract`

**Linux:** `sudo apt-get install tesseract-ocr`

### Run the server

```bash
uvicorn app:app --reload --port 8000
```

Then open:

- Dashboard: **http://localhost:8000**
- API docs (Swagger UI): **http://localhost:8000/docs**
- API docs (ReDoc): **http://localhost:8000/redoc**

### Try it

1. Upload a document image at the dashboard
2. Optionally add a selfie for face verification
3. The pipeline runs automatically
4. The dashboard renders the risk score, component breakdown, and reasons

---

## API Reference

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/health` | Liveness check |
| POST | `/api/upload` | Basic file upload + validation |
| POST | `/api/analyze` | Full pipeline (document + optional selfie) |
| POST | `/api/debug-ocr` | Raw OCR debug output |

### `POST /api/analyze`

**Request:** `multipart/form-data`

- `file` (required) — document image
- `selfie` (optional) — face image for verification

**Response (abbreviated):**

```json
{
  "status": "analyzed",
  "session_id": "uuid",
  "ocr_confidence": 67.3,
  "fields": { "passport_number": "...", "date_of_birth": "...", "...": "..." },
  "validation": { "overall": "WARN", "rules": [], "summary": {} },
  "tampering": { "overall": "LOW", "score": 22, "detectors": [] },
  "face_verification": { "verdict": "NOT_ATTEMPTED", "similarity": null },
  "risk": { "risk_score": 19, "risk_level": "LOW", "recommendation": "CLEAR FOR FURTHER PROCESSING", "reasons": [] }
}
```

Full interactive documentation: **http://localhost:8000/docs**

---

## Project Structure

```
FIDDS/
├── app.py                         FastAPI entry point
├── requirements.txt
├── README.md
├── config/
│   └── config.py                  Central configuration
├── api/
│   └── routes.py                  REST endpoints
├── modules/
│   ├── ocr/
│   │   ├── ocr_engine.py          Tesseract + MRZ extraction
│   │   └── passport_parser.py     Field parsing with provenance
│   ├── validation/
│   │   ├── validator.py           10-rule engine
│   │   └── mrz_validator.py       ICAO 9303 check digits
│   ├── tampering/
│   │   └── forensic_analysis.py   ELA, metadata, grid, noise
│   ├── face/
│   │   └── face_verification.py   dlib 128-D embeddings
│   └── risk/
│       └── risk_engine.py         Weighted fusion
├── templates/
│   └── index.html                 Dashboard UI
├── static/
│   ├── css/style.css
│   └── js/app.js
├── data/
│   └── synthetic/                 Demo documents
├── uploads/                       Temporary upload area
└── tests/                         (planned)
```

---

## Design Principles

1. **Assistive, not autonomous.** The system recommends; it never decides.
2. **Explainable by design.** Every score has reasons; every reason has a source.
3. **Honest failure.** When the system can't verify something, it says so.
4. **Provenance tracking.** Every field records which channel produced it.
5. **Human-in-the-loop.** HIGH risk means MANUAL REVIEW, not rejection.
6. **Privacy-conscious.** No biometric data persisted; audit records store metadata, not images.
7. **CPU-friendly.** No GPU required.
8. **Modular.** Each module is testable and replaceable independently.

---

## Limitations

- **Tested on synthetic documents only.** No production calibration on real passport distributions.
- **Thresholds are prototype defaults.** They require labeled data to calibrate properly.
- **No liveness detection.** A photo of a photo would pass face verification.
- **No deepfake detection.** Synthesized faces are not specifically handled.
- **No NFC / ePassport chip reading.** Does not verify against the digital signature on the chip.
- **Single-document type optimized.** Tuned for Indian passport layout.
- **ELA has known false positives.** Scanned and recompressed documents may trigger warnings.
- **No authentication or HTTPS in local prototype.** Deployment hardening is future work.
- **SQLite audit trail designed but not wired.** Session IDs exist; persistence pending.
- **No monitoring, load testing, or model versioning.**

**Every limitation is why the system recommends manual review rather than making automated decisions.**

---

## Future Scope

### Short term

- pytest unit test suite
- SQLite audit trail persistence
- Docker containerization
- Structured logging with session IDs

### Medium term

- ML-based tampering detection (EfficientNet fine-tune)
- Multilingual OCR (Devanagari, Arabic, Cyrillic)
- NFC / ePassport chip reading (ICAO 9303 Part 10)
- Presentation attack detection (liveness)
- Cross-document consistency checking
- Multimodal fusion model with learned weights

### Long term

- Edge deployment with quantized models
- Federated learning for privacy-preserving updates
- Authorized integration with official verification APIs
- Bias evaluation and mitigation
- Counterfactual explanations for officers

**All future-scope items are clearly labelled as not implemented in the current prototype.**

---

## License

Academic prototype. Not for production use without authorization, legal review, and compliance certification.

---

## Acknowledged Limitations and Ethical Stance

FIDDS is a **competition prototype**. It is not affiliated with any government agency, does not access any real identity database, and makes no claim of regulatory certification. It is designed to **assist** authorized personnel, not to **replace** human judgment. Any deployment affecting real people would require:

- Proper legal authorization
- Calibration on representative data
- Bias and fairness evaluation
- Independent security audit
- Documented oversight and appeal mechanisms

None of those are present in this prototype.
