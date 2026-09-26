"""Risk engine - combines all module outputs into a single explainable risk score."""
from datetime import datetime


# Weights for each module (must sum to 1.0)
WEIGHTS = {
    "validation": 0.30,
    "tampering": 0.30,
    "face": 0.25,
    "ocr_quality": 0.15,
}

# Risk level thresholds (prototype defaults - configurable)
LOW_MAX = 30
MEDIUM_MAX = 60


def _score_validation(validation):
    """Convert validation rules into a 0-100 risk contribution."""
    if not validation:
        return 20, []
    fails = 0
    warns = 0
    reasons = []
    for rule in validation.get("rules", []):
        if rule["result"] == "FAIL":
            fails += 1
            reasons.append({
                "source": "validation",
                "severity": "critical",
                "text": f"{rule['id']} {rule['name']}: {rule['reason']}",
            })
        elif rule["result"] == "WARN":
            warns += 1
            reasons.append({
                "source": "validation",
                "severity": "warning",
                "text": f"{rule['id']} {rule['name']}: {rule['reason']}",
            })
    score = min(100, fails * 20 + warns * 5)
    return score, reasons


def _score_tampering(tampering):
    """Tampering already produces a 0-100 score."""
    if not tampering:
        return 20, []
    score = tampering.get("score", 0)
    reasons = []
    for det in tampering.get("detectors", []):
        if det["signal"] in ("MEDIUM", "HIGH"):
            severity = "critical" if det["signal"] == "HIGH" else "warning"
            reasons.append({
                "source": "tampering",
                "severity": severity,
                "text": f"{det['id']} {det['name']}: {det['reason']}",
            })
    return score, reasons


def _score_face(face):
    """Convert face verification verdict into a 0-100 risk contribution."""
    if not face:
        return 20, [{"source": "face", "severity": "info", "text": "Face verification not available."}]
    verdict = face.get("verdict", "NOT_ATTEMPTED")
    reasons = []
    if verdict == "MATCH":
        score = 0
        reasons.append({"source": "face", "severity": "info",
                        "text": f"Face MATCH (similarity {face.get('similarity')})."})
    elif verdict == "POSSIBLE MATCH":
        score = 60
        reasons.append({"source": "face", "severity": "warning",
                        "text": f"Face POSSIBLE MATCH (similarity {face.get('similarity')}) - below match threshold."})
    elif verdict == "NO MATCH":
        score = 100
        reasons.append({"source": "face", "severity": "critical",
                        "text": f"Face NO MATCH (similarity {face.get('similarity')})."})
    elif verdict == "UNABLE TO VERIFY":
        score = 30
        reasons.append({"source": "face", "severity": "warning",
                        "text": "Face could not be verified."})
    else:  # NOT_ATTEMPTED
        score = 20
        reasons.append({"source": "face", "severity": "info",
                        "text": "Face verification not attempted (no selfie provided)."})
    return score, reasons


def _score_ocr(ocr_confidence):
    """Low OCR confidence = higher risk."""
    if ocr_confidence is None:
        return 40, [{"source": "ocr", "severity": "warning", "text": "OCR confidence unavailable."}]
    score = max(0, min(100, int(100 - ocr_confidence)))
    reasons = []
    if ocr_confidence < 60:
        reasons.append({"source": "ocr", "severity": "warning",
                        "text": f"Low OCR confidence ({ocr_confidence}%) - extraction reliability reduced."})
    return score, reasons


def compute_risk(ocr_confidence, validation, tampering, face_verification):
    """
    Combine all module outputs into a single risk score.
    Returns: {risk_score, risk_level, recommendation, components, reasons, disclaimer}
    """
    validation_score, validation_reasons = _score_validation(validation)
    tampering_score, tampering_reasons = _score_tampering(tampering)
    face_score, face_reasons = _score_face(face_verification)
    ocr_score, ocr_reasons = _score_ocr(ocr_confidence)

    components = {
        "validation": validation_score,
        "tampering": tampering_score,
        "face": face_score,
        "ocr_quality": ocr_score,
    }

    risk_score = int(round(
        validation_score * WEIGHTS["validation"] +
        tampering_score * WEIGHTS["tampering"] +
        face_score * WEIGHTS["face"] +
        ocr_score * WEIGHTS["ocr_quality"]
    ))

    if risk_score <= LOW_MAX:
        risk_level = "LOW"
        recommendation = "CLEAR FOR FURTHER PROCESSING"
    elif risk_score <= MEDIUM_MAX:
        risk_level = "MEDIUM"
        recommendation = "MANUAL REVIEW RECOMMENDED"
    else:
        risk_level = "HIGH"
        recommendation = "MANUAL REVIEW REQUIRED"

    reasons = validation_reasons + tampering_reasons + face_reasons + ocr_reasons

    return {
        "risk_score": risk_score,
        "risk_level": risk_level,
        "recommendation": recommendation,
        "components": components,
        "reasons": reasons,
        "disclaimer": (
            "This risk indicator is an assistive signal only. It does not determine "
            "that any person or document is fraudulent. Manual review by an authorized "
            "officer is required for any final determination."
        ),
    }
