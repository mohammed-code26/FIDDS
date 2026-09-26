# FIDDS
## Fraudulent Identity & Document Detecting System
### Technical Approach

**Presenter:** [Your Name]
**Stack:** Python 3.11 - FastAPI - Tesseract - OpenCV - dlib

---

## 1. System Architecture

Frontend (Bootstrap 5) -> HTTP/JSON -> FastAPI Backend

Inside the backend, five independent modules run in sequence:

- OCR + MRZ extraction
- Validation rules engine
- Tampering / forensic analysis
- Face verification
- Risk engine

Each module returns a dict: status, score, findings, reasons.
The API orchestrates. Modules do not call each other.
The risk engine consumes only module dicts - never the raw image.

---

## 2. Module 1 - OCR + MRZ Extraction

Inputs: image bytes (JPG / PNG / PDF)

Pipeline:
1. Preprocessing - grayscale, fastNlMeans denoise, adaptive Gaussian threshold
2. Full-image OCR - Tesseract with image_to_data for per-line confidence
3. MRZ extraction (dual path)
   - Path A - PassportEye (purpose-built MRZ detector)
   - Path B - Tesseract fallback (bottom 30% crop, 2x upscale, Otsu, PSM 6 with MRZ charset)
4. Field parsing - regex + MRZ structure to passport_number, surname, given_names, dob, expiry, nationality

Field provenance labels:
- mrz_anchored - cleanly parsed from MRZ
- reocr_verified - recovered from ROI, checksum-validated
- viz - extracted from printed text via label anchoring
- reocr_unverified - recovered but not validated

---

## 3. MRZ Validation (ICAO 9303)

Check-digit algorithm:
- weights = [7, 3, 1] cycling
- value(c) = digit or A=10..Z=35 or filler = 0
- check = (sum(value(c[i]) * weights[i mod 3])) mod 10

Verification layers:
- Line 1: document type P<, issuing country, name in SURNAME<<GIVEN<NAMES form
- Line 2: 44 chars - passport number, nationality, DOB, sex, expiry, composite check

Anchor-based parser validates nationality against ISO-3166 alpha-3 closed set, then requires strict shape: 6 digits + 1 check + M/F/< + 6 digits + 1 check. On failure, reports field_length_mismatch instead of silently producing wrong values.

Recovery: crop DOB block (x=0.30-0.48) and expiry block (x=0.50-0.68) from ROI, 4x upscale, PSM 7 digits-only, validate against check digit.

---

## 4. Module 2 - Validation Rules Engine

Ten independent rules:

| ID | Rule | Category |
|----|------|----------|
| R001 | Passport number format | Format |
| R002 | Nationality ISO-3166 | Format |
| R003 | Required fields present | Completeness |
| R004 | DOB in the past | Date logic |
| R005 | DOB plausible (0-120 yrs) | Date logic |
| R006 | Expiry in the future | Date logic |
| R007 | Expiry after DOB | Consistency |
| R008 | MRZ number check digit | Checksum |
| R009 | MRZ alignment succeeded | Integrity |
| R010 | Field provenance trust | Trust |

Output per rule: id, name, result (PASS/WARN/FAIL), reason, severity.

Aggregation: any FAIL means FAIL; any WARN means WARN; else PASS.

---

## 5. Module 3 - Tampering / Forensic Analysis

T1 - Error Level Analysis (weight 0.35)
Re-encode at quality 90, diff vs original, amplify 15x.
Signal = fraction of pixels with error above mean + 2 sigma.

T2 - Metadata Inspection (weight 0.15)
Read EXIF via PIL getexif().
Flags: editor software, timestamp inconsistency.
Never a verdict - signal only.

T3 - JPEG Grid Consistency (weight 0.25)
Measure 8x8 block-boundary edge energy vs off-boundary energy.
Ratio above 1.4 suggests recompression or splice.

T4 - Noise Variance (weight 0.25)
Laplacian high-pass, 32x32 patch variance.
Fraction of patches with variance above 3x median.

Aggregate score = 0.35*T1 + 0.15*T2 + 0.25*T3 + 0.25*T4
Level: LOW below 30, MEDIUM below 60, HIGH at or above 60.

---

## 6. Module 4 - Face Verification

Model: dlib 128-D face embeddings via face_recognition library.

Pipeline:
1. Detect faces on full document image
2. If none, crop left 40% x top 85% (passport photo region) and retry
3. Detect face on selfie
4. Reject 0 or more than 1 face - unable to verify
5. Extract 128-D embeddings
6. Similarity = 1 - face_distance

Verdict logic:
- similarity at or above 0.55 - MATCH
- similarity at or above 0.45 - POSSIBLE MATCH
- similarity below 0.45 - NO MATCH

Documented limitations: not a liveness detector; sensitive to lighting, angle, aging; thresholds are prototype defaults.

---

## 7. Risk Engine - Weighted Fusion

risk_score = 0.30 * validation_score
           + 0.30 * tampering_score
           + 0.25 * face_score
           + 0.15 * ocr_quality_score

Component scoring:
- Validation: min(100, fails*20 + warns*5)
- Tampering: direct 0-100 from detector fusion
- Face: MATCH=0, POSSIBLE=60, NO MATCH=100, UNABLE=30, NOT_ATTEMPTED=20
- OCR quality: 100 - confidence

Risk levels:
- 0 to 30: LOW - CLEAR FOR FURTHER PROCESSING
- 31 to 60: MEDIUM - MANUAL REVIEW RECOMMENDED
- 61 to 100: HIGH - MANUAL REVIEW REQUIRED

All weights configurable in modules/risk/risk_engine.py.

---

## 8. Explainability Layer

Each score decomposes into attributed reasons. Example:

- validation, warning - R009 MRZ alignment failed.
- tampering, warning - T1 ELA shows localized high-error regions.
- face, warning - Face could not be verified.
- ocr, info - Low OCR confidence (58%).

Not a black box. Every decision traceable to a source signal.

---

## 9. API Design

Endpoints:
- GET /api/health - liveness check
- POST /api/upload - basic upload
- POST /api/analyze - full pipeline
- POST /api/debug-ocr - raw OCR debug
- GET /docs - Swagger UI
- GET /redoc - ReDoc

/api/analyze request: multipart form, file (required) and selfie (optional).
Response includes: fields, validation, tampering, face_verification, risk.

---

## 10. Security and Privacy Controls

Input handling:
- Extension whitelist: .jpg, .jpeg, .png, .pdf
- Size limit: 10 MB
- Randomized UUID filenames
- Streaming upload handling

Data handling:
- Temporary storage with UUID names
- Biometric embeddings computed in-memory, never persisted
- Audit records store session metadata, not raw images

Disclosures:
- Prototype notice on every page
- No government certification claimed
- No access to real identity databases

---

## 11. Technology Stack

| Layer | Component | Version |
|-------|-----------|---------|
| Language | Python | 3.11.9 |
| Web framework | FastAPI | 0.115.x |
| ASGI server | Uvicorn | 0.32.x |
| OCR | Tesseract | 5.5.3 |
| OCR binding | pytesseract | 0.3.13 |
| MRZ | PassportEye | 4.x |
| Image processing | OpenCV | 4.10.x |
| Image I/O | Pillow | 11.x |
| Face detection | dlib | 19.24.1 |
| Face library | face_recognition | 1.3.0 |
| Numeric | NumPy | 1.26.x |
| Config | pydantic-settings | 2.6.x |
| Templating | Jinja2 | 3.1.4 |
| Frontend | Bootstrap | 5.3.3 |

Deployment characteristics: CPU-only, roughly 1.5 GB peak RAM, 8 to 12 seconds per document on an i5-6300U.

---

## 12. Testing and Validation

Unit tests (planned):
- Passport number regex against valid and invalid samples
- Date logic edge cases
- MRZ check-digit against ICAO reference vectors
- Tampering detector on clean vs tampered images
- Risk engine weighting math

Integration tests:
- End-to-end /api/analyze on demo scenarios
- Graceful failure on corrupted, oversized, unsupported inputs

Honest metrics disclosure:
- No ground-truth passport dataset used
- Synthetic documents with known-correct MRZ
- All check-digit tests verified against ICAO 9303

---

## 13. Limitations (Stated Honestly)

- No access to real identity database
- No verification against issuing authority
- No liveness or spoof detection
- No GPU-accelerated models
- MRZ OCR depends on image quality and font
- ELA false positives on scanned or recompressed images
- Face verification sensitive to lighting, angle, aging
- Synthetic training data - not calibrated on production distribution

Design response: uncertainty reported as UNABLE TO VERIFY; recommendations always defer to human review.

---

## 14. Future Technical Work

Short term:
- pytest suite
- SQLite audit persistence
- Docker containerization
- Structured logging with session IDs

Medium term:
- ML tampering detection (EfficientNet fine-tune)
- Multilingual OCR
- NFC / ePassport chip reading
- Presentation attack detection (liveness)

Long term:
- Multimodal fusion model with learned weights
- Quantized on-device inference
- Federated learning
- Authorized verification API integration

All items labelled not implemented in prototype.

---

## 15. Conclusion

Built:
- Five independent analysis modules in a FastAPI pipeline
- ICAO 9303 MRZ validation with check-digit verification
- Four-detector tampering analysis with weighted fusion
- 128-D face embedding verification
- Explainable risk engine with attributed reasons
- Auto-generated API documentation

Characteristics:
- CPU-only inference
- Modular, testable, replaceable
- Honest failure modes
- Production-shaped architecture

One-line summary:
A multi-layer, explainable, CPU-deployable document screening pipeline that combines OCR, formal validation, image forensics, and biometric verification into a single auditable risk score.
