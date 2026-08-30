"""
One-time backfill: walks the RRISL archive pages (price_e.php?id=1..N),
collects every auction date it can find, downloads each price image,
OCRs it, and adds it to docs/data/prices.json.

Run this once manually via the "Backfill Historical Prices" GitHub Action.
It's safe to re-run — it skips dates already in prices.json.
"""
import json
import re
import time
from pathlib import Path

import requests

from ocr_extract import ocr_image, parse_grades

ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "docs" / "data" / "prices.json"
IMAGES_DIR = ROOT / "docs" / "data" / "images"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; rubber-price-bot/1.0)"}

MAX_PAGE_ID = 130

IMAGE_URL_TEMPLATES = [
    "https://www.rrisl.gov.lk/content/images/prices/{date}.JPG",
    "http://www.rrisl.gov.lk/content/images/prices/{date}.JPG",
    "http://www.rrisl.lk/content/images/prices/{date}.JPG",
    "https://www.rrisl.gov.lk/content/images/prices/{date}.jpg",
    "http://www.rrisl.lk/content/images/prices/{date}.jpg",
]


def to_iso(date_str):
    d, m, y = date_str.split("-")
    return f"{y}-{m}-{d}"


def collect_all_dates(session):
    """Walk every archive page and collect every unique auction date."""
    dates = set()
    for page_id in range(1, MAX_PAGE_ID + 1):
        url = f"https://www.rrisl.gov.lk/price_e.php?id={page_id}"
        try:
            resp = session.get(url, headers=HEADERS, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"  page id={page_id}: request failed ({e}), skipping")
            continue

        found = re.findall(r"(\d{2}-\d{2}-\d{4})", resp.text)
        if not found:
            print(f"  page id={page_id}: no dates found")
            continue

        for d in found:
            dates.add(d)
        print(f"  page id={page_id}: {len(found)} date(s) seen, {len(dates)} unique so far")
        time.sleep(0.3)
    return dates


def download_image(session, iso_date):
    for template in IMAGE_URL_TEMPLATES:
        url = template.format(date=iso_date)
        try:
            resp = session.get(url, headers=HEADERS, timeout=30)
            if resp.status_code == 200 and resp.content:
                return resp.content, url
        except requests.RequestException:
            continue
    return None, None


def main():
    session = requests.Session()

    data = json.loads(DATA_FILE.read_text()) if DATA_FILE.exists() else {"entries": []}
    known_dates = {e["date"] for e in data["entries"]}

    print("Scanning archive pages for auction dates...")
    all_dates = collect_all_dates(session)
    print(f"\nFound {len(all_dates)} unique auction dates on the site.")

    iso_dates = sorted({to_iso(d) for d in all_dates})
    new_dates = [d for d in iso_dates if d not in known_dates]
    print(f"{len(new_dates)} are new (not already in prices.json).\n")

    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    added, failed = 0, []

    for i, iso_date in enumerate(new_dates, 1):
        print(f"[{i}/{len(new_dates)}] {iso_date}...", end=" ")
        content, used_url = download_image(session, iso_date)
        if not content:
            print("image not found on any known host, skipping")
            failed.append(iso_date)
            continue

        img_path = IMAGES_DIR / f"{iso_date}.jpg"
        img_path.write_bytes(content)

        try:
            raw_text = ocr_image(img_path)
            grades = parse_grades(raw_text)
        except Exception as e:
            print(f"OCR failed ({e})")
            failed.append(iso_date)
            continue

        data["entries"].append({
            "date": iso_date,
            "source_image": str(img_path.relative_to(ROOT)),
            "source_page": "https://www.rrisl.gov.lk/price_e.php?last=3",
            "grades": grades,
            "raw_ocr_text": raw_text,
            "needs_review": len(grades) < 5,
        })
        added += 1
        print(f"ok, {len(grades)} grades parsed")

        if added % 20 == 0:
            data["entries"].sort(key=lambda e: e["date"])
            DATA_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))

        time.sleep(0.3)

    data["entries"].sort(key=lambda e: e["date"])
    DATA_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    print(f"\nDone. Added {added} new auctions.")
    if failed:
        print(f"{len(failed)} dates could not be downloaded/OCR'd: {failed[:20]}"
              f"{' ...' if len(failed) > 20 else ''}")


if __name__ == "__main__":
    main()
