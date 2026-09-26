import warnings
warnings.filterwarnings('ignore', category=FutureWarning, module='passporteye')

"""OCR Engine — PassportEye with Tesseract fallback, ROI passthrough."""
import cv2
import numpy as np
import pytesseract
import os
import tempfile

from config.config import settings

pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD

MRZ_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<")


def preprocess_image(image_bytes: bytes) -> np.ndarray:
    arr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Could not decode image.")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.fastNlMeansDenoising(gray, h=10)
    return cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY,
        blockSize=31, C=10,
    )


def extract_text(image_bytes: bytes, lang: str = "eng") -> dict:
    processed = preprocess_image(image_bytes)
    data = pytesseract.image_to_data(
        processed, lang=lang, output_type=pytesseract.Output.DICT,
    )
    lines, confs = [], []
    for i, t in enumerate(data["text"]):
        t = t.strip()
        c = int(data["conf"][i])
        if t and c > 0:
            lines.append(t)
            confs.append(c)
    return {
        "text": "\n".join(lines),
        "confidence": round(sum(confs) / len(confs), 1) if confs else 0.0,
        "line_count": len(lines),
    }


def _clean_mrz(s: str) -> str:
    return "".join(c for c in s.upper() if c in MRZ_CHARS)


def _normalize_line1(s: str) -> str:
    s = _clean_mrz(s)
    if not s.startswith("P<"):
        s = "P<" + s[2:] if len(s) >= 2 else s
    s = list(s.ljust(44, "<")[:44])
    d2l = {"0": "O", "1": "I", "2": "Z", "5": "S", "8": "B"}
    for i in range(2, 5):
        if s[i].isdigit() and s[i] in d2l:
            s[i] = d2l[s[i]]
    for i in range(5, 44):
        if s[i] in "0123456789KXk":
            s[i] = "<"
    return "".join(s)


def _normalize_line2(s: str) -> str:
    s = _clean_mrz(s)
    s = list(s.ljust(44, "<")[:44])
    l2d = {"O": "0", "I": "1", "L": "1", "Z": "2", "S": "5", "B": "8",
           "G": "6", "Q": "0", "D": "0", "T": "7"}
    d2l = {"0": "O", "1": "I", "2": "Z", "5": "S", "8": "B", "6": "G"}
    if s[9].isalpha() and s[9] in l2d: s[9] = l2d[s[9]]
    for i in range(10, 13):
        if s[i].isdigit() and s[i] in d2l: s[i] = d2l[s[i]]
        elif s[i] in "KXR": s[i] = "<"
    for i in range(13, 19):
        if s[i].isalpha() and s[i] in l2d: s[i] = l2d[s[i]]
        elif s[i] in "<KXR": s[i] = "0"
    if s[19].isalpha() and s[19] in l2d: s[19] = l2d[s[19]]
    elif s[19] in "<KXR": s[19] = "0"
    if s[20] not in "MF<": s[20] = "<"
    for i in range(21, 27):
        if s[i].isalpha() and s[i] in l2d: s[i] = l2d[s[i]]
        elif s[i] in "<KXR": s[i] = "0"
    if s[27].isalpha() and s[27] in l2d: s[27] = l2d[s[27]]
    elif s[27] in "<KXR": s[27] = "0"
    for i in range(28, 42):
        if s[i] in "KXR": s[i] = "<"
    if s[42].isalpha() and s[42] in l2d: s[42] = l2d[s[42]]
    elif s[42] in "<KXR": s[42] = "0"
    if s[43].isalpha() and s[43] in l2d: s[43] = l2d[s[43]]
    elif s[43] in "<KXR": s[43] = "0"
    return "".join(s)


def _extract_via_passporteye(image_bytes: bytes) -> dict:
    try:
        from passporteye import read_mrz
    except ImportError:
        return {}

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    try:
        tmp.write(image_bytes)
        tmp.close()
        mrz = read_mrz(tmp.name, save_roi=True)
    except Exception:
        return {}
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass

    if mrz is None:
        return {}

    raw = (getattr(mrz, "mrz_string", None) or "").replace("\n", "").replace(" ", "").strip()
    if len(raw) < 44:
        return {}

    score = float(getattr(mrz, "valid_score", 0) or 0)
    line1 = raw[0:44]
    line2 = raw[44:88] if len(raw) >= 88 else ""

    roi = None
    try:
        if getattr(mrz, "aux", None) and mrz.aux.get("roi") is not None:
            roi = mrz.aux["roi"]
            from PIL import Image
            Image.fromarray(roi).save("uploads/_debug_mrz_crop.png")
    except Exception:
        roi = None

    return {
        "text": line1 + ("\n" + line2 if line2 else ""),
        "valid": score >= 90,
        "score": score,
        "source": "passporteye",
        "roi": roi,
        "field_checks": {
            "number": bool(getattr(mrz, "valid_number", False)),
            "date_of_birth": bool(getattr(mrz, "valid_date_of_birth", False)),
            "expiration_date": bool(getattr(mrz, "valid_expiration_date", False)),
            "composite": bool(getattr(mrz, "valid_composite", False)),
        },
    }


def _extract_via_tesseract(image_bytes: bytes) -> dict:
    arr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return {}

    h, w = img.shape[:2]
    band = img[int(h * 0.68):, :]
    band = cv2.resize(band, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    cv2.imwrite("uploads/_debug_mrz_crop.png", band)

    gray = cv2.cvtColor(band, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    config = "--psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<"
    text = pytesseract.image_to_string(thresh, config=config)

    candidates = [_clean_mrz(l) for l in text.splitlines() if len(_clean_mrz(l)) >= 30]

    line1, line2 = None, None
    for i, c in enumerate(candidates):
        if c.startswith("P<") and line1 is None:
            line1 = _normalize_line1(c)
            for j in range(i + 1, len(candidates)):
                n2 = _normalize_line2(candidates[j])
                if all(n2[k].isalpha() or n2[k] == "<" for k in range(10, 13)):
                    line2 = n2
                    break
            break

    if not (line1 and line2):
        return {}

    return {
        "text": line1 + "\n" + line2,
        "valid": False,
        "score": 0.0,
        "source": "tesseract-fallback",
        "roi": band,
        "field_checks": {
            "number": None, "date_of_birth": None,
            "expiration_date": None, "composite": None,
        },
    }


def extract_mrz_region(image_bytes: bytes) -> dict:
    result = _extract_via_passporteye(image_bytes)
    if result and result.get("text"):
        return result

    result = _extract_via_tesseract(image_bytes)
    if result and result.get("text"):
        return result

    return {
        "text": "",
        "valid": False,
        "score": 0.0,
        "source": "none",
        "roi": None,
        "field_checks": {
            "number": None, "date_of_birth": None,
            "expiration_date": None, "composite": None,
        },
    }