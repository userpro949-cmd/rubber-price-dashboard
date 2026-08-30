"""
Runs OCR on downloaded price images and parses grade -> average-price rows
out of the raw text.

The RRISL sheet is a table like:

  RUBBER AUCTION PRICES - SALE OF 25.08.2026
                          RANGE (Rs.)              AVERAGE (Rs.)
  LATEX CREPE   1X        Unq    -    Unq          Unq
  LATEX CREPE   1         1,150.00  - Flat         1,150.00
  LATEX CREPE   2         1,000.00  - 1,100.00     1,050.00
  ...
  SC.CR         1X(BR)    915.00    - 920.00       918.00
  ...
  RIBBED SMOKED SHEET  1  Unq       - Unq          Unq

There's also a faint tree-shaped watermark behind the text, which hurts
OCR accuracy. We upscale + threshold the image before running tesseract
to cut through that.

Image OCR on a scanned table is still not perfectly reliable, so:
- the full raw OCR text is always saved (for manual double-checking)
- we take the AVERAGE (Rs.) column (rightmost number) per grade as "the
  price" for charting purposes
- rows where the average is "Unq" / "Flat" / "Nom" (no trade / no quote
  that week) are simply skipped for that week, not treated as errors
- `needs_review` is set if we parsed a suspiciously small number of rows
"""
import json
import re
import sys
from pathlib import Path

from PIL import Image, ImageOps
import pytesseract

ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "docs" / "data" / "prices.json"

LABEL_RE = re.compile(
    r"^(LATEX\s*CREPE|SC\.?\s*CR\.?|FLAT\s*BARK|SKIM\s*CREPE|RIBBED\s*SMOKED\s*SHEET)",
    re.IGNORECASE,
)
VARIANT_RE = re.compile(r"^[0-9]{1,2}[A-Za-z()]*$")
NUMBER_RE = re.compile(r"^[\d,]+(\.\d+)?$")


def is_variant_token(tok: str) -> bool:
    """A grade-number token like '1', '2', '1X', '3X(BR)' — short, and
    never carrying a comma/decimal the way a formatted price does."""
    return bool(VARIANT_RE.match(tok)) and "." not in tok and "," not in tok


def preprocess(image: Image.Image) -> Image.Image:
    """Upscale + grayscale + threshold to cut through the background
    watermark and sharpen thin table text for OCR."""
    image = image.convert("L")
    w, h = image.size
    image = image.resize((w * 2, h * 2), Image.LANCZOS)
    image = image.point(lambda p: 255 if p > 170 else 0)
    image = ImageOps.autocontrast(image)
    return image


def parse_grades(raw_text):
    grades = {}
    for line in raw_text.splitlines():
        line = line.strip()
        if not line:
            continue
        if "kgs" in line.lower() or "lots" in line.lower():
            # bottom-of-sheet volume/lot-count summary rows, not price rows
            continue
        m = LABEL_RE.match(line)
        if not m:
            continue

        base_label = re.sub(r"\s+", " ", m.group(1)).upper().strip()
        rest = line[m.end():].strip()
        tokens = rest.split()

        variant = ""
        idx = 0
        if tokens and is_variant_token(tokens[0]):
            variant = tokens[0]
            idx = 1

        value_tokens = [t for t in tokens[idx:] if t not in ("-", "\u2013", "\u2014")]
        if not value_tokens:
            continue

        last = value_tokens[-1].replace(",", "")
        if not NUMBER_RE.match(last):
            continue
        try:
            price = float(last)
        except ValueError:
            continue

        label = f"{base_label} {variant}".strip()
        grades[label] = price
    return grades


def ocr_image(img_path: Path):
    image = Image.open(img_path)
    image = preprocess(image)
    return pytesseract.image_to_string(image, config="--psm 6")


def main():
    if not DATA_FILE.exists():
        print(f"No data file at {DATA_FILE}")
        sys.exit(1)

    data = json.loads(DATA_FILE.read_text())
    changed = False

    for entry in data["entries"]:
        img_path = ROOT / entry["source_image"]
        if not img_path.exists():
            print(f"Skipping {entry['date']} - image not found at {img_path}")
            continue

        raw_text = ocr_image(img_path)
        grades = parse_grades(raw_text)

        entry["raw_ocr_text"] = raw_text
        entry["grades"] = grades
        entry["needs_review"] = len(grades) < 5
        changed = True

        print(f"{entry['date']}: parsed {len(grades)} priced grade rows"
              f"{' (flagged for review)' if entry['needs_review'] else ''}")

    if changed:
        DATA_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        print("Saved updated prices.json")
    else:
        print("Nothing to OCR.")


if __name__ == "__main__":
    main()
