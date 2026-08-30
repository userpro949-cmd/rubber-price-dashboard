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
OCR accuracy. Sheets from different years also use slightly different
fonts/scan quality, so raw OCR output for the same grade varies
("LATEX CREPE 1X" vs "LATEXCREPE 1X" vs "LATEX CREPE 41x" etc).

To keep the data usable across ~8 years of scans:
- the full raw OCR text is always saved (for manual double-checking)
- every parsed row label is snapped to one of a fixed, known set of real
  grade names (CANONICAL_GRADES) via fuzzy matching; anything that
  doesn't resemble a real grade closely enough is dropped rather than
  creating a new noisy "grade"
- parsed prices are sanity-bounded (real per-kg rubber prices are in the
  hundreds/low thousands of Rs, not tens of thousands) to reject cases
  where a volume figure like "68,475 kgs" gets misread as a price
- rows where the average is "Unq" / "Flat" / "Nom" (no trade / no quote
  that week) are simply skipped for that week, not treated as errors
- `needs_review` is set if we parsed a suspiciously small number of rows
"""
import difflib
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

CANONICAL_GRADES = [
    "LATEX CREPE 1X", "LATEX CREPE 1", "LATEX CREPE 2",
    "LATEX CREPE 3", "LATEX CREPE 4",
    "SC.CR 1X(BR)", "SC.CR 2X(BR)", "SC.CR 3X(BR)", "SC.CR 4X(BR)",
    "FLAT BARK", "SKIM CREPE",
    "RIBBED SMOKED SHEET 1", "RIBBED SMOKED SHEET 2",
    "RIBBED SMOKED SHEET 3", "RIBBED SMOKED SHEET 4",
    "RIBBED SMOKED SHEET 5",
]

MIN_PLAUSIBLE_PRICE = 50
MAX_PLAUSIBLE_PRICE = 3000

MATCH_THRESHOLD = 0.72


def _normalize_for_match(label: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", label.upper())


_CANONICAL_NORMALIZED = {g: _normalize_for_match(g) for g in CANONICAL_GRADES}


def canonicalize_label(raw_label: str):
    norm = _normalize_for_match(raw_label)
    if not norm:
        return None
    best_grade, best_ratio = None, 0.0
    for grade, grade_norm in _CANONICAL_NORMALIZED.items():
        ratio = difflib.SequenceMatcher(None, norm, grade_norm).ratio()
        if ratio > best_ratio:
            best_grade, best_ratio = grade, ratio
    if best_ratio >= MATCH_THRESHOLD:
        return best_grade
    return None


def is_variant_token(tok: str) -> bool:
    return bool(VARIANT_RE.match(tok)) and "." not in tok and "," not in tok


def preprocess(image: Image.Image) -> Image.Image:
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

        base_norm = _normalize_for_match(base_label)
        if not variant and base_norm not in ("FLATBARK", "SKIMCREPE"):
            continue

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

        if not (MIN_PLAUSIBLE_PRICE <= price <= MAX_PLAUSIBLE_PRICE):
            continue

        raw_label = f"{base_label} {variant}".strip()
        canonical = canonicalize_label(raw_label)
        if canonical is None:
            continue

        grades[canonical] = price
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
