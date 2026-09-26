"""Generate HIGH-risk synthetic passport."""
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

OUTPUT = Path(__file__).resolve().parent / "synthetic_passport_HIGH_RISK.png"


def font(size, mono=False):
    names = ["consola.ttf", "cour.ttf", "DejaVuSansMono.ttf"] if mono else ["arial.ttf", "DejaVuSans.ttf"]
    for n in names:
        try:
            return ImageFont.truetype(n, size)
        except Exception:
            continue
    return ImageFont.load_default()


def make():
    W, H = 1400, 900
    img = Image.new("RGB", (W, H), (252, 250, 242))
    d = ImageDraw.Draw(img)

    f_title = font(32)
    f_label = font(18)
    f_value = font(24)
    f_mrz = font(34, mono=True)
    f_small = font(16)

    d.rectangle([0, 0, W, 80], fill=(20, 40, 90))
    d.text((40, 22), "REPUBLIC OF INDIA - PASSPORT (HIGH RISK DEMO)", font=f_title, fill="white")

    d.rectangle([70, 130, 280, 400], fill=(40, 40, 40))
    d.text((140, 250), "PHOTO", font=f_label, fill=(200, 200, 200))

    fields = [
        ("Passport No.", "K0294558"),
        ("Surname", "GUPTA"),
        ("Given Names", "AMIT"),
        ("Nationality", "INDIAN"),
        ("Date of Birth", "01/01/2030"),
        ("Place of Birth", "MUMBAI"),
        ("Sex", "M"),
        ("Date of Issue", "03/02/2024"),
        ("Date of Expiry", "02/02/2034"),
        ("Place of Issue", "MUMBAI"),
    ]
    y = 130
    for label, value in fields:
        d.text((320, y), label.upper(), font=f_label, fill=(60, 60, 60))
        d.text((560, y - 2), value, font=f_value, fill=(10, 10, 10))
        y += 52

    d.line([(0, 700), (W, 700)], fill=(140, 140, 140), width=2)
    l1 = "P<INDGUPTA<<AMIT" + "<" * (44 - len("P<INDGUPTA<<AMIT"))
    l2 = "K0294558<7IND3001012M3402029<<<<<<<<<<<<<<0"
    d.text((60, 730), l1, font=f_mrz, fill=(5, 5, 5))
    d.text((60, 790), l2, font=f_mrz, fill=(5, 5, 5))

    d.rectangle([560, 386, 780, 412], fill=(255, 255, 255))
    d.text((562, 390), "01/01/2030", font=f_value, fill=(10, 10, 10))

    d.rectangle([850, 200, 1150, 300], outline=(200, 30, 30), width=4)
    d.text((880, 235), "APPROVED", font=f_title, fill=(200, 30, 30))

    d.rectangle([320, 180, 500, 210], fill=(255, 255, 255))
    d.text((322, 184), "GUPTA", font=f_value, fill=(10, 10, 10))

    d.text((40, 850), "SYNTHETIC TEST DOCUMENT - HIGH RISK DEMO", font=f_small, fill=(200, 30, 30))

    img = img.rotate(2.5, expand=True, fillcolor=(252, 250, 242))

    img.save(OUTPUT, "PNG")
    print("Saved:", OUTPUT)


if __name__ == "__main__":
    make()
