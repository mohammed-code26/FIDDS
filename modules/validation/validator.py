"""Validation rules engine. Each rule returns {id, name, result, reason, severity}."""
from datetime import datetime, timedelta
import re

from modules.ocr.passport_parser import INDIAN_PASSPORT_REGEX, VALID_NATIONALITIES


def _parse_date(s: str):
    if not s:
        return None
    s = s.strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _rule(id_, name, result, reason, severity="info"):
    return {"id": id_, "name": name, "result": result, "reason": reason, "severity": severity}


def run_validation(fields: dict, passport_validation: dict = None) -> dict:
    rules = []
    today = datetime.now()

    # --- R001: Passport number format (self-contained regex) ---
    pn = fields.get("passport_number")
    if not pn:
        rules.append(_rule("R001", "Passport number format", "FAIL",
                           "Passport number was not extracted.", "critical"))
    elif INDIAN_PASSPORT_REGEX.match(pn.upper()):
        rules.append(_rule("R001", "Passport number format", "PASS",
                           f"'{pn}' matches Indian passport format.", "info"))
    else:
        rules.append(_rule("R001", "Passport number format", "FAIL",
                           f"'{pn}' does not match the expected pattern.", "critical"))

    # --- R002: Nationality code ---
    nat = fields.get("nationality")
    if not nat:
        rules.append(_rule("R002", "Nationality code", "WARN",
                           "Nationality not extracted.", "warning"))
    elif nat in VALID_NATIONALITIES:
        rules.append(_rule("R002", "Nationality code", "PASS",
                           f"'{nat}' is a recognized ISO-3166 alpha-3 code.", "info"))
    else:
        rules.append(_rule("R002", "Nationality code", "WARN",
                           f"'{nat}' is not in the known nationality set.", "warning"))

    # --- R003: Required fields present ---
    required = ["passport_number", "date_of_birth", "date_of_expiry", "nationality"]
    missing = [f for f in required if not fields.get(f)]
    if missing:
        rules.append(_rule("R003", "Required fields present", "FAIL",
                           f"Missing required fields: {', '.join(missing)}.", "critical"))
    else:
        rules.append(_rule("R003", "Required fields present", "PASS",
                           "All required fields were extracted.", "info"))

    # --- R004: DOB in past ---
    dob = _parse_date(fields.get("date_of_birth"))
    if not dob:
        rules.append(_rule("R004", "DOB is in the past", "WARN",
                           "Could not parse date of birth.", "warning"))
    elif dob <= today:
        rules.append(_rule("R004", "DOB is in the past", "PASS",
                           f"DOB {dob.strftime('%d/%m/%Y')} is before today.", "info"))
    else:
        rules.append(_rule("R004", "DOB is in the past", "FAIL",
                           f"DOB {dob.strftime('%d/%m/%Y')} is in the future.", "critical"))

    # --- R005: DOB plausible (< 120 yrs) ---
    if dob:
        age = (today - dob).days / 365.25
        if 0 <= age <= 120:
            rules.append(_rule("R005", "DOB plausible", "PASS",
                               f"Age approximately {int(age)} years.", "info"))
        else:
            rules.append(_rule("R005", "DOB plausible", "WARN",
                               f"Computed age {int(age)} years is outside 0-120.", "warning"))
    else:
        rules.append(_rule("R005", "DOB plausible", "WARN",
                           "Cannot evaluate without a valid DOB.", "warning"))

    # --- R006: Expiry in future ---
    exp = _parse_date(fields.get("date_of_expiry"))
    if not exp:
        rules.append(_rule("R006", "Expiry in future", "WARN",
                           "Could not parse expiry date.", "warning"))
    elif exp >= today:
        rules.append(_rule("R006", "Expiry in future", "PASS",
                           f"Document is valid until {exp.strftime('%d/%m/%Y')}.", "info"))
    else:
        rules.append(_rule("R006", "Expiry in future", "FAIL",
                           f"Document expired on {exp.strftime('%d/%m/%Y')}.", "critical"))

    # --- R007: Expiry after DOB + 1 yr ---
    if dob and exp:
        if exp > dob + timedelta(days=365):
            rules.append(_rule("R007", "Expiry after DOB", "PASS",
                               "Expiry is logically after date of birth.", "info"))
        else:
            rules.append(_rule("R007", "Expiry after DOB", "FAIL",
                               "Expiry is not logically after DOB.", "critical"))

    # --- R008: MRZ passport number check digit ---
    parsed_mrz = fields.get("mrz_parsed") or {}
    if parsed_mrz.get("passport_number_check_digit_valid") is True:
        rules.append(_rule("R008", "MRZ number checksum", "PASS",
                           "Passport number check digit verified.", "info"))
    elif parsed_mrz.get("passport_number_check_digit_valid") is False:
        rules.append(_rule("R008", "MRZ number checksum", "FAIL",
                           "Passport number check digit did not match.", "critical"))
    else:
        rules.append(_rule("R008", "MRZ number checksum", "WARN",
                           "MRZ passport number checksum unavailable.", "warning"))

    # --- R009: MRZ alignment succeeded ---
    if fields.get("mrz_alignment_ok") is True:
        rules.append(_rule("R009", "MRZ alignment", "PASS",
                           "MRZ line 2 aligned to expected TD3 structure.", "info"))
    elif fields.get("mrz_alignment_ok") is False:
        rules.append(_rule("R009", "MRZ alignment", "WARN",
                           f"MRZ alignment failed ({fields.get('mrz_alignment_reason', 'unknown')}).",
                           "warning"))
    else:
        rules.append(_rule("R009", "MRZ alignment", "WARN",
                           "No MRZ line 2 was available for alignment.", "warning"))

    # --- R010: Provenance trust ---
    dob_src = fields.get("dob_source")
    exp_src = fields.get("expiry_source")
    verified_sources = {"mrz_anchored", "mrz_positional", "reocr_verified"}
    if dob_src in verified_sources and exp_src in verified_sources:
        rules.append(_rule("R010", "Field provenance", "PASS",
                           "Both dates verified from MRZ or checksum-validated re-OCR.", "info"))
    elif dob_src or exp_src:
        rules.append(_rule("R010", "Field provenance", "WARN",
                           f"Dates sourced from fallback (dob: {dob_src}, expiry: {exp_src}).",
                           "warning"))
    else:
        rules.append(_rule("R010", "Field provenance", "WARN",
                           "No provenance info for date fields.", "warning"))

    fails = sum(1 for r in rules if r["result"] == "FAIL")
    warns = sum(1 for r in rules if r["result"] == "WARN")
    passes = sum(1 for r in rules if r["result"] == "PASS")

    overall = "FAIL" if fails > 0 else ("WARN" if warns > 0 else "PASS")

    return {
        "overall": overall,
        "rules": rules,
        "summary": {"pass": passes, "warn": warns, "fail": fails},
    }


if __name__ == "__main__":
    sample_fields = {
        "passport_number": "K2294558",
        "date_of_birth": "08/07/1994",
        "date_of_expiry": "02/02/2034",
        "nationality": "IND",
        "mrz_parsed": {"passport_number_check_digit_valid": True},
        "mrz_alignment_ok": False,
        "mrz_alignment_reason": "field_length_mismatch",
        "dob_source": "viz",
        "expiry_source": "viz",
    }
    result = run_validation(sample_fields)
    print(f"Overall: {result['overall']}")
    print(f"Summary: {result['summary']}")
    for r in result["rules"]:
        print(f"  [{r['result']}] {r['id']} {r['name']}: {r['reason']}")