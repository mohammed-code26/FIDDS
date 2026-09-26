"""API routes: health, upload, analyze, debug-ocr."""
from fastapi import APIRouter, UploadFile, File, HTTPException
from datetime import datetime
from typing import Optional
import uuid

from config.config import settings
from modules.ocr.ocr_engine import extract_text, extract_mrz_region
from modules.ocr.passport_parser import extract_fields, validate_indian_passport_number
from modules.validation.validator import run_validation
from modules.tampering.forensic_analysis import run_tampering_analysis
from modules.face.face_verification import verify_faces
from modules.risk.risk_engine import compute_risk

router = APIRouter(prefix="/api", tags=["fidds"])


@router.get("/health")
async def health():
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "timestamp": datetime.utcnow().isoformat(),
    }


def _validate_upload(file):
    filename = file.filename or ""
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type {ext}.")
    return ext


@router.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    ext = _validate_upload(file)
    contents = await file.read()
    size_mb = len(contents) / (1024 * 1024)
    if size_mb > settings.MAX_UPLOAD_MB:
        raise HTTPException(status_code=413, detail=f"File too large ({size_mb:.2f} MB).")
    session_id = str(uuid.uuid4())
    with open(settings.UPLOAD_DIR / f"{session_id}{ext}", "wb") as f:
        f.write(contents)
    return {
        "status": "received",
        "session_id": session_id,
        "original_filename": file.filename,
        "stored_as": f"{session_id}{ext}",
        "size_mb": round(size_mb, 3),
        "message": "Document received.",
    }


@router.post("/analyze")
async def analyze_document(
    file: UploadFile = File(...),
    selfie: Optional[UploadFile] = File(None),
):
    ext = _validate_upload(file)
    contents = await file.read()
    size_mb = len(contents) / (1024 * 1024)
    if size_mb > settings.MAX_UPLOAD_MB:
        raise HTTPException(status_code=413, detail=f"Document too large: {size_mb:.2f} MB")

    session_id = str(uuid.uuid4())
    with open(settings.UPLOAD_DIR / f"{session_id}{ext}", "wb") as f:
        f.write(contents)

    # --- OCR ---
    try:
        ocr_result = extract_text(contents)
    except Exception as e:
        return {
            "status": "unable_to_verify",
            "session_id": session_id,
            "message": "OCR failed. Manual review required.",
            "error": str(e),
        }

    mrz_dict = extract_mrz_region(contents)
    fields = extract_fields(ocr_result["text"], mrz_dict)

    passport_validation = None
    if fields.get("passport_number"):
        passport_validation = validate_indian_passport_number(fields["passport_number"])

    validation = run_validation(fields, passport_validation)

    # --- Tampering ---
    try:
        tampering = run_tampering_analysis(contents)
    except Exception as e:
        tampering = {
            "overall": "UNAVAILABLE", "score": 0,
            "detectors": [], "metadata": {}, "error": str(e),
        }

    # --- Face verification (optional) ---
    if selfie is not None:
        try:
            selfie_bytes = await selfie.read()
            selfie_mb = len(selfie_bytes) / (1024 * 1024)
            if selfie_mb > settings.MAX_UPLOAD_MB:
                face_result = {
                    "verdict": "UNABLE TO VERIFY",
                    "similarity": None,
                    "reasons": [f"Selfie too large ({selfie_mb:.2f} MB)."],
                }
            else:
                face_result = verify_faces(contents, selfie_bytes)
        except Exception as e:
            face_result = {
                "verdict": "UNABLE TO VERIFY",
                "similarity": None,
                "reasons": [f"Face verification failed: {e}"],
            }
    else:
        face_result = {
            "verdict": "NOT_ATTEMPTED",
            "similarity": None,
            "reasons": ["No selfie was provided for face verification."],
        }

    # --- Risk engine ---
    risk = compute_risk(
        ocr_confidence=ocr_result["confidence"],
        validation=validation,
        tampering=tampering,
        face_verification=face_result,
    )

    return {
        "status": "analyzed",
        "session_id": session_id,
        "ocr_confidence": ocr_result["confidence"],
        "mrz_source": mrz_dict.get("source"),
        "mrz_valid": mrz_dict.get("valid"),
        "mrz_score": mrz_dict.get("score"),
        "fields": fields,
        "passport_number_validation": passport_validation,
        "validation": validation,
        "tampering": tampering,
        "face_verification": face_result,
        "risk": risk,
        "message": "Full pipeline complete.",
    }


@router.post("/debug-ocr")
async def debug_ocr(file: UploadFile = File(...)):
    contents = await file.read()
    ocr_result = extract_text(contents)
    mrz_raw = extract_mrz_region(contents)
    return {
        "full_text_length": len(ocr_result["text"]),
        "full_confidence": ocr_result["confidence"],
        "full_text_preview": ocr_result["text"][:2000],
        "mrz_dict": {
            "text": mrz_raw.get("text"),
            "source": mrz_raw.get("source"),
            "valid": mrz_raw.get("valid"),
            "score": mrz_raw.get("score"),
            "roi_present": mrz_raw.get("roi") is not None,
        },
    }
