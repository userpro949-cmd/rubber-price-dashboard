"""
Runs OCR on the newest downloaded price image and tries to parse
grade -> price rows out of the raw text.

Image OCR on a scanned auction sheet is not perfectly reliable, so:
- the full raw OCR text is always saved (for manual double-checking)
- parsed rows are saved separately as `grades`
- `needs_review` stays True unless parsing found a sane-looking set of rows,
  so the dashboard can visibly flag any week that needs a human glance
"""
import json
import re
import sys
from pathlib import Path

from PIL import Image
import pytesseract

ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "docs" / "data" / "prices.json"

# A price line generally looks like: "RSS 1    1250.00"  or  "Latex 60%   980"
GRADE_LINE_RE = re.compile(
    r"^([A-Za-z0-9()%.\-\s]{2,25}?)\s+([0-9]{2,3}(?:[.,][0-9]{2})?)\s*$"
)


def parse_grades(raw_text):
    grades = {}
    for line in raw_text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = GRADE_LINE_RE.match(line)
        if m:
            label = m.group(1).strip()
            value = m.group(2).replace(",", ".")
            try:
                grades[label] = float(value)
            except ValueError:
                continue
    return grades


def main():
    new_entry_marker = ROOT / ".new_entry"
    if not new_entry_marker.exists() or new_entry_marker.read_text().strip() == "false":
        print("No new entry to OCR.")
        return

    iso_date = new_entry_marker.read_text().strip()
    data = json.loads(DATA_FILE.read_text())
    entry = next((e for e in data["entries"] if e["date"] == iso_date), None)
    if entry is None:
        print(f"Could not find entry for {iso_date} in {DATA_FILE}")
        sys.exit(1)

    img_path = ROOT / entry["source_image"]
    image = Image.open(img_path)

    raw_text = pytesseract.image_to_string(image)
    grades = parse_grades(raw_text)

    entry["raw_ocr_text"] = raw_text
    entry["grades"] = grades
    # Only mark as not needing review if we found a reasonable number of rows
    entry["needs_review"] = len(grades) < 3

    DATA_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"OCR complete for {iso_date}. Parsed {len(grades)} grade rows.")
    if entry["needs_review"]:
        print("Flagged for manual review (few/no rows parsed cleanly).")


if __name__ == "__main__":
    main()
