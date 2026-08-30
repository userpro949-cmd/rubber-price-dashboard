"""
Checks the RRISL rubber price page for a new auction date.
If a new date is found, downloads the price image and hands off to ocr_extract.py.

The site publishes prices as a scanned image (not text/HTML), refreshed
roughly weekly at:
https://www.rrisl.gov.lk/price_e.php?last=3
"""
import json
import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "docs" / "data" / "prices.json"
IMAGES_DIR = ROOT / "docs" / "data" / "images"
SOURCE_URL = "https://www.rrisl.gov.lk/price_e.php?last=3"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; rubber-price-bot/1.0)"}


def load_data():
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text())
    return {"entries": []}


def save_data(data):
    DATA_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def fetch_latest():
    resp = requests.get(SOURCE_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    html = resp.text

    # Date of Auction :DD-MM-YYYY
    date_match = re.search(r"Date of Auction\s*:\s*(\d{2}-\d{2}-\d{4})", html)
    # Image path, e.g. content/images/prices/2026-08-25.JPG
    img_match = re.search(
        r'(https?://[^"\'\s]+/content/images/prices/[^"\'\s]+\.JPG)',
        html,
        re.IGNORECASE,
    )

    if not date_match or not img_match:
        print("Could not find auction date or image URL on the page.")
        sys.exit(1)

    return date_match.group(1), img_match.group(1)


def to_iso(date_str):
    d, m, y = date_str.split("-")
    return f"{y}-{m}-{d}"


def main():
    date_str, image_url = fetch_latest()
    iso_date = to_iso(date_str)

    data = load_data()
    known_dates = {e["date"] for e in data["entries"]}

    if iso_date in known_dates:
        print(f"No new auction. Latest on site is still {iso_date}.")
        Path(ROOT / ".new_entry").write_text("false")
        return

    print(f"New auction found: {iso_date}. Downloading image...")
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    img_path = IMAGES_DIR / f"{iso_date}.jpg"

    img_resp = requests.get(image_url, headers=HEADERS, timeout=30)
    img_resp.raise_for_status()
    img_path.write_bytes(img_resp.content)

    data["entries"].append(
        {
            "date": iso_date,
            "source_image": str(img_path.relative_to(ROOT)),
            "source_page": SOURCE_URL,
            "grades": {},
            "raw_ocr_text": "",
            "needs_review": True,
        }
    )
    # Keep entries sorted oldest -> newest
    data["entries"].sort(key=lambda e: e["date"])
    save_data(data)

    Path(ROOT / ".new_entry").write_text(iso_date)
    print(f"Saved new entry for {iso_date}. Image at {img_path}")


if __name__ == "__main__":
    main()
