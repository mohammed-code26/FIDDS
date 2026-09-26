"""
Improved Synthetic Indian Passport Generator.
Renders bigger, cleaner MRZ with proper spacing so Tesseract reads it reliably.
"""
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from modules.validation.mrz_validator import build_mrz_line2

OUTPUT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def find_mono_font(size):
    """Find a monospace font for the MRZ — critical for clean OCR."""
    candidates = [
        "consola.ttf", "cour.ttf", "lucon.ttf",  # Windows
        "DejaVuSansMono.ttf", "LiberationMono-Regular.ttf",  # Linux/Mac
    ]
    for name in candidates:
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def find_regular_font(size):
    for name in ["arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"]:
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def make_passport_image(output_path: Path) -> None:
    # Bigger canvas = better OCR
    W, H = 1400, 900
    img = Image.new("RGB", (W, H), color=(252, 250, 242))
    draw = ImageDraw.Draw(img)

    f_title = find_regular_font(32)
    f_label = find_regular_font(18)
    f_value = find_regular_font(24)
    f_mrz = find_mono_font(34)   # ← Monospace, large, critical
    f_small = find_regular_font(16)
    f_watermark = find_regular_font(80)

    # --- Header ---
    draw.rectangle([0, 0, W, 80], fill=(20, 40, 90))
    draw.text((40, 22), "REPUBLIC OF INDIA - PASSPORT (DEMO)", font=f_title, fill="white")

    # --- Watermark ---
    draw.text((350, 380), "DEMO DOCUMENT", font=f_watermark, fill=(230, 228, 220))

    # --- Photo placeholder ---
    draw.rectangle([70, 130, 280, 400], outline=(80, 80, 80), width=2)
    draw.text((140, 250), "PHOTO", font=f_label, fill=(120, 120, 120))

    # --- Fields ---
    fields = [
        ("Passport No.", "K2294558"),
        ("Surname", "GUPTA"),
        ("Given Names", "AMIT"),
        ("Nationality", "INDIAN"),
        ("Date of Birth", "08/07/1994"),
        ("Place of Birth", "MUMBAI"),
        ("Sex", "M"),
        ("Date of Issue", "03/02/2024"),
        ("Date of Expiry", "02/02/2034"),
        ("Place of Issue", "MUMBAI"),
    ]

    y = 130
    for label, value in fields:
        draw.text((320, y), label.upper(), font=f_label, fill=(60, 60, 60))
        draw.text((560, y - 2), value, font=f_value, fill=(10, 10, 10))
        y += 52

    # --- MRZ region ---
    # Horizontal separator
    draw.line([(0, 700), (W, 700)], fill=(140, 140, 140), width=2)

    line2 = build_mrz_line2(
        passport_number="K2294558",
        nationality="IND",
        dob_raw="940708",
        sex="M",
        expiry_raw="340202",
    )
    line1 = "P<INDGUPTA<<AMIT" + "<" * (44 - len("P<INDGUPTA<<AMIT"))

    # MRZ drawn character-by-character with spacing (prevents < being read as K)
    def draw_mrz_line(draw, x_start, y, text, font):
        x = x_start
        for ch in text:
            draw.text((x, y), ch, font=font, fill=(5, 5, 5))
            # Measure char width for consistent spacing
            bbox = draw.textbbox((0, 0), ch, font=font)
            char_w = bbox[2] - bbox[0]
            x += max(char_w + 6, 22)  # ensure minimum spacing

    draw_mrz_line(draw, 80, 730, line1, f_mrz)
    draw_mrz_line(draw, 80, 790, line2, f_mrz)

    # Disclaimer at top-right corner (away from MRZ)
    draw.text((40, 850),
              "SYNTHETIC TEST DOCUMENT - NOT A REAL IDENTITY DOCUMENT",
              font=f_small, fill=(200, 30, 30))

    img.save(output_path, "PNG")
    print(f"Saved: {output_path}")
    print(f"MRZ line 1: {line1}")
    print(f"MRZ line 2: {line2}")


if __name__ == "__main__":
    out = OUTPUT_DIR / "synthetic_indian_passport_demo.png"
    make_passport_image(out)
