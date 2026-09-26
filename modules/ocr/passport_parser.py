"""Indian Passport parser — anchored MRZ, ROI-based re-OCR, checksum-validated recovery, VIZ fallback."""
import re
import cv2
import numpy as np
import pytesseract

from config.config import settings
from modules.validation.mrz_validator import (
    parse_mrz_line2, yymmdd_to_date, compute_check_digit,
)

pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD

INDIAN_PASSPORT_REGEX = re.compile(r"^[A-PR-WY][1-9]\d\s?\d{4}[1-9]$")

VALID_NATIONALITIES = {
    "IND", "USA", "GBR", "CAN", "AUS", "DEU", "FRA", "JPN", "CHN",
    "PAK", "BGD", "NPL", "LKA", "ARE", "SAU", "SGP", "MYS", "THA",
    "RUS", "BRA", "ZAF", "ESP", "ITA", "NLD", "CHE", "SWE", "NOR",
}


def validate_indian_passport_number(number: str) -> dict:
    cleaned = number.replace(" ", "").upper()
    valid = bool(INDIAN_PASSPORT_REGEX.match(number.upper()))
    return {
        "value": number,
        "cleaned": cleaned,
        "format_valid": valid,
        "reason": "Matches Indian passport format" if valid else "Does not match Indian passport format",
    }


def _recover_dob_with_check(digits: str, expected_check: str):
    if not digits or not expected_check or not expected_check.isdigit():
        return None
    for start in range(0, len(digits) - 6 + 1):
        window = digits[start:start + 6]
        if str(compute_check_digit(window)) == expected_check:
            return window
    return None


def reocr_digits_from_roi(roi, line_index: int, x0_frac: float, x1_frac: float, scale: int = 4) -> str:
    if roi is None:
        return ""
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY) if roi.ndim == 3 else roi
    h, w = gray.shape[:2]
    band_h = h // 2
    y0, y1 = line_index * band_h, (line_index + 1) * band_h
    x0, x1 = int(w * x0_frac), int(w * x1_frac)
    line = gray[y0:y1, x0:x1]
    if line.size == 0:
        return ""
    line = cv2.resize(line, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    _, thresh = cv2.threshold(line, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    config = "--psm 7 -c tessedit_char_whitelist=0123456789"
    return re.sub(r"\D", "", pytesseract.image_to_string(thresh, config=config))


def parse_mrz_line2_anchored(raw: str) -> dict:
    raw = raw.strip()
    if len(raw) < 20:
        return {"ok": False, "reason": "too_short", "len": len(raw)}

    m = re.search(r"[A-Z]{3}", raw[9:16])
    if not m or m.group() not in VALID_NATIONALITIES:
        return {"ok": False, "reason": "nationality_anchor_not_found", "raw": raw}

    anchor_end = 9 + m.end()
    nationality = m.group()
    remainder = raw[anchor_end:]

    field = re.match(r"(\d{6})(\d)([MF<])(\d{6})(\d)", remainder)
    if not field:
        return {
            "ok": False,
            "reason": "field_length_mismatch",
            "nationality": nationality,
            "remainder_raw": remainder,
            "remainder_len": len(remainder),
        }

    dob, dob_chk, sex, exp, exp_chk = field.groups()
    return {
        "ok": True,
        "nationality": nationality,
        "dob": dob, "dob_check": dob_chk,
        "sex": sex,
        "expiry": exp, "expiry_check": exp_chk,
    }


def extract_viz_fields(raw_text: str) -> dict:
    text_upper = raw_text.upper()
    text_compact = re.sub(r"\s+", " ", text_upper)
    date_re = r"(\d{2}[/.-]\d{2}[/.-]\d{4})"

    def find_after(label_pattern):
        m = re.search(label_pattern + r"[^0-9]{0,40}?" + date_re, text_compact)
        return m.group(1) if m else None

    dob_viz = find_after(r"DATE\s*OF\s*BIRTH|BIRTH\s*DATE|DOB")
    issue_viz = find_after(r"DATE\s*OF\s*ISSUE|ISSUE\s*DATE")
    expiry_viz = find_after(r"DATE\s*OF\s*EXPIRY|EXPIRY\s*DATE|EXPIRATION")

    if not (dob_viz or issue_viz or expiry_viz):
        dates = re.findall(date_re, raw_text)
        dob_viz = dates[0] if len(dates) > 0 else None
        issue_viz = dates[1] if len(dates) > 1 else None
        expiry_viz = dates[2] if len(dates) > 2 else None

    return {
        "dob_viz": dob_viz,
        "issue_viz": issue_viz,
        "expiry_viz": expiry_viz,
    }


def extract_fields(raw_text: str, mrz_dict: dict = None) -> dict:
    result = {
        "passport_number": None,
        "surname": None,
        "given_names": None,
        "date_of_birth": None,
        "date_of_expiry": None,
        "nationality": None,
        "mrz_line1": None, "mrz_line2": None,
        "mrz_parsed": None,
        "mrz_valid": None, "mrz_score": None, "mrz_source": None,
        "mrz_alignment_ok": None, "mrz_alignment_reason": None,
        "viz_fields": None,
        "dob_source": None,
        "expiry_source": None,
    }

    viz = extract_viz_fields(raw_text)
    result["viz_fields"] = viz

    mrz_line1 = mrz_line2 = None
    if mrz_dict and mrz_dict.get("text"):
        lines = mrz_dict["text"].split("\n")
        if len(lines) >= 1:
            mrz_line1 = lines[0]
            result["mrz_line1"] = mrz_line1
            result["mrz_valid"] = mrz_dict.get("valid")
            result["mrz_score"] = mrz_dict.get("score")
            result["mrz_source"] = mrz_dict.get("source")
        if len(lines) >= 2:
            mrz_line2 = lines[1]
            result["mrz_line2"] = mrz_line2

    anchored = None
    if mrz_line2:
        anchored = parse_mrz_line2_anchored(mrz_line2)
        result["mrz_alignment_ok"] = anchored.get("ok")
        result["mrz_alignment_reason"] = anchored.get("reason")

    if anchored and anchored.get("ok"):
        result["passport_number"] = mrz_line2[0:9].replace("<", "").strip() or None
        result["nationality"] = anchored["nationality"]
        result["date_of_birth"] = yymmdd_to_date(anchored["dob"], "dob")
        result["date_of_expiry"] = yymmdd_to_date(anchored["expiry"], "expiry")
        result["dob_source"] = "mrz_anchored"
        result["expiry_source"] = "mrz_anchored"
    elif mrz_line2:
        parsed = parse_mrz_line2(mrz_line2)
        if "error" not in parsed:
            result["mrz_parsed"] = parsed
            result["passport_number"] = parsed.get("passport_number") or None
            result["nationality"] = parsed.get("nationality") or None
            if anchored and not anchored.get("ok"):
                result["date_of_birth"] = None
                result["date_of_expiry"] = None
            else:
                result["date_of_birth"] = yymmdd_to_date(parsed.get("date_of_birth_raw", ""), "dob") or None
                result["date_of_expiry"] = yymmdd_to_date(parsed.get("date_of_expiry_raw", ""), "expiry") or None
                if result["date_of_birth"]:
                    result["dob_source"] = "mrz_positional"
                if result["date_of_expiry"]:
                    result["expiry_source"] = "mrz_positional"

    if mrz_line1 and mrz_line1.startswith("P<"):
        name_part = mrz_line1[5:]
        if "<<" in name_part:
            parts = name_part.split("<<")
            result["surname"] = parts[0].replace("<", " ").strip() or None
            result["given_names"] = parts[1].replace("<", " ").strip() or None

    roi = mrz_dict.get("roi") if mrz_dict else None

    if anchored and not anchored.get("ok") and roi is not None:
        expected_dob_check = None
        expected_exp_check = None
        rem = anchored.get("remainder_raw", "")
        d = re.findall(r"\d", rem)
        if len(d) >= 15:
            expected_dob_check = d[6]
            expected_exp_check = d[13]

        dob_digits = reocr_digits_from_roi(roi, line_index=1, x0_frac=0.30, x1_frac=0.48)
        if dob_digits and expected_dob_check:
            verified = _recover_dob_with_check(dob_digits, expected_dob_check)
            if verified:
                result["date_of_birth"] = yymmdd_to_date(verified, "dob")
                result["dob_source"] = "reocr_verified"
            else:
                result["dob_source"] = result.get("dob_source") or "reocr_failed_check"
        elif dob_digits:
            if len(dob_digits) >= 6:
                result["date_of_birth"] = result["date_of_birth"] or yymmdd_to_date(dob_digits[:6], "dob")
                result["dob_source"] = "reocr_unverified"

        exp_digits = reocr_digits_from_roi(roi, line_index=1, x0_frac=0.50, x1_frac=0.68)
        if exp_digits and expected_exp_check:
            verified = _recover_dob_with_check(exp_digits, expected_exp_check)
            if verified:
                result["date_of_expiry"] = yymmdd_to_date(verified, "expiry")
                result["expiry_source"] = "reocr_verified"
            else:
                result["expiry_source"] = result.get("expiry_source") or "reocr_failed_check"
        elif exp_digits:
            if len(exp_digits) >= 6:
                result["date_of_expiry"] = result["date_of_expiry"] or yymmdd_to_date(exp_digits[:6], "expiry")
                result["expiry_source"] = "reocr_unverified"

    if anchored and not anchored.get("ok"):
        if viz["dob_viz"]:
            result["date_of_birth"] = viz["dob_viz"]
            result["dob_source"] = "viz"
        if viz["expiry_viz"]:
            result["date_of_expiry"] = viz["expiry_viz"]
            result["expiry_source"] = "viz"
    else:
        if not result["date_of_birth"] and viz["dob_viz"]:
            result["date_of_birth"] = viz["dob_viz"]
            result["dob_source"] = "viz"
        if not result["date_of_expiry"] and viz["expiry_viz"]:
            result["date_of_expiry"] = viz["expiry_viz"]
            result["expiry_source"] = "viz"

    if not result["passport_number"]:
        m = re.search(r"\b([A-PR-WY][1-9]\d\s?\d{4}[1-9])\b", raw_text, re.IGNORECASE)
        if m:
            result["passport_number"] = m.group(1)

    return result


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python -m modules.ocr.passport_parser <image>")
        sys.exit(1)
    with open(sys.argv[1], "rb") as f:
        data = f.read()
    from modules.ocr.ocr_engine import extract_text, extract_mrz_region
    text = extract_text(data)["text"]
    mrz = extract_mrz_region(data)
    fields = extract_fields(text, mrz)
    for k, v in fields.items():
        print(f"{k}: {v}")