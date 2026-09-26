"""
ICAO 9303 MRZ check-digit validator.
Pure Python — no dependencies. Implements the official algorithm.
"""
from datetime import datetime


def char_value(c: str) -> int:
    """Digits keep value; A-Z map to 10-35; filler < maps to 0."""
    if c == "<":
        return 0
    if c.isdigit():
        return int(c)
    if c.isalpha():
        return ord(c.upper()) - ord("A") + 10
    return 0


def compute_check_digit(data: str) -> int:
    """ICAO 9303 check digit: weights cycle 7,3,1; result = sum mod 10."""
    weights = [7, 3, 1]
    total = 0
    for i, c in enumerate(data):
        total += char_value(c) * weights[i % 3]
    return total % 10


def verify_check_digit(data: str, expected: str) -> bool:
    """Verify a check digit against computed value."""
    if not expected or expected not in "0123456789":
        return False
    return compute_check_digit(data) == int(expected)


def parse_mrz_line2(line2: str) -> dict:
    """
    Parse TD3 lower MRZ line (44 chars for passports).
    Returns extracted fields + check-digit verification.
    """
    if len(line2) < 44:
        return {"error": f"MRZ line 2 too short ({len(line2)} chars, expected 44)"}

    passport_number = line2[0:9].replace("<", "").strip()
    passport_check = line2[9]
    nationality = line2[10:13]
    dob_raw = line2[13:19]
    dob_check = line2[19]
    sex = line2[20]
    expiry_raw = line2[21:27]
    expiry_check = line2[27]

    # Verify individual check digits
    passport_ok = verify_check_digit(line2[0:9], passport_check)
    dob_ok = verify_check_digit(dob_raw, dob_check)
    expiry_ok = verify_check_digit(expiry_raw, expiry_check)

    
    # Composite check digit: positions 1-10 + 14-20 + 22-42 (per ICAO 9303)
    # → data (38 chars) is verified against position 43 (index 42)
    composite_data = line2[0:10] + line2[13:20] + line2[21:42]
    composite_ok = verify_check_digit(composite_data, line2[42])

    # Final check digit: positions 1-10 + 14-20 + 22-43 (per ICAO 9303)
    # → data (39 chars, includes composite check) is verified against position 44 (index 43)
    final_data = line2[0:10] + line2[13:20] + line2[21:43]
    final_ok = verify_check_digit(final_data, line2[43])

    return {
        "passport_number": passport_number,
        "passport_number_check_digit_valid": passport_ok,
        "nationality": nationality,
        "date_of_birth_raw": dob_raw,
        "date_of_birth_check_digit_valid": dob_ok,
        "sex": sex,
        "date_of_expiry_raw": expiry_raw,
        "date_of_expiry_check_digit_valid": expiry_ok,
        "composite_check_digit_valid": composite_ok,
        "final_check_digit_valid": final_ok,
        "all_check_digits_valid": all([passport_ok, dob_ok, expiry_ok, composite_ok, final_ok]),
    }


def yymmdd_to_date(raw: str, kind: str = "dob") -> str:
    """
    Convert MRZ YYMMDD to ISO date (YYYY-MM-DD).
    kind='dob' assumes past (1900s if 2000s would be future).
    kind='expiry' assumes 2000s century (documents valid in modern era).
    """
    if not raw or len(raw) != 6 or not raw.isdigit():
        return ""
    yy, mm, dd = int(raw[0:2]), int(raw[2:4]), int(raw[4:6])
    today = datetime.now()

    year = 2000 + yy
    if kind == "dob" and year > today.year:
        year = 1900 + yy

    try:
        return datetime(year, mm, dd).strftime("%Y-%m-%d")
    except ValueError:
        return ""


def build_mrz_line2(
    passport_number: str,
    nationality: str,
    dob_raw: str,
    sex: str,
    expiry_raw: str,
    optional: str = "",
) -> str:
    """
    Build a valid TD3 MRZ line 2 with correct check digits.
    Useful for generating synthetic test documents.
    """
    passport_field = passport_number.upper().ljust(9, "<")[:9]
    passport_check = str(compute_check_digit(passport_field))

    dob_field = dob_raw.ljust(6, "0")[:6]
    dob_check = str(compute_check_digit(dob_field))

    expiry_field = expiry_raw.ljust(6, "0")[:6]
    expiry_check = str(compute_check_digit(expiry_field))

    optional_field = optional.upper().ljust(14, "<")[:14]

    # Composite data: positions 1-10, 14-20, 22-42
    composite_data = (
        passport_field + passport_check +         # positions 1-10
        dob_field + dob_check +                    # 14-20
        expiry_field + expiry_check + optional_field  # 22-42
    )
    composite_check = str(compute_check_digit(composite_data))
    final_check = str(compute_check_digit(composite_data + composite_check))

    line2 = (
        passport_field + passport_check +
        nationality.ljust(3, "<")[:3] +
        dob_field + dob_check +
        sex.upper()[:1] +
        expiry_field + expiry_check +
        optional_field +
        composite_check +
        final_check
    )
    return line2


if __name__ == "__main__":
    # Test with a properly-constructed MRZ
    line2 = build_mrz_line2(
        passport_number="K2294558",
        nationality="IND",
        dob_raw="940708",
        sex="M",
        expiry_raw="340202",
    )
    print("Generated MRZ line 2:", line2)
    print("Length:", len(line2))
    print()

    result = parse_mrz_line2(line2)
    for k, v in result.items():
        print(f"{k}: {v}")
    print()
    print("DOB parsed:", yymmdd_to_date(result["date_of_birth_raw"], "dob"))
    print("Expiry parsed:", yymmdd_to_date(result["date_of_expiry_raw"], "expiry"))
