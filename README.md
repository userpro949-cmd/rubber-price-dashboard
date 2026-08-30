# Sri Lanka Rubber Auction Price Dashboard

Auto-updating dashboard for RRISL rubber auction prices
(https://www.rrisl.gov.lk/price_e.php?last=3).

**Important limitation:** RRISL publishes prices as a scanned image, not a
table. This pipeline downloads that image and runs OCR (text recognition)
on it. OCR on scanned tables isn't 100% reliable — every week's entry
carries a `needs_review` flag, and the raw OCR text is always saved so you
can sanity-check or hand-correct it. Treat this as "mostly automatic," not
"never look at it."

## What it does
1. `scripts/scrape.py` checks the RRISL page daily for a new auction date.
2. If there's a new one, it downloads that week's price image.
3. `scripts/ocr_extract.py` OCRs the image and tries to parse grade/price rows.
4. Everything is saved to `docs/data/prices.json`.
5. `docs/index.html` is a dashboard (chart + tables) that reads that file.
6. GitHub Actions runs steps 1–4 automatically once a day and commits any
   changes — that's what makes it "auto-update."

## One-time setup (~10 minutes)

1. **Create a GitHub account** at github.com if you don't have one.
2. **Create a new repository** (top right → "New repository"). Name it
   something like `rubber-price-dashboard`. Public repos get free GitHub
   Pages hosting.
3. **Upload these files** to the repo. Easiest way: on the repo page, click
   "Add file" → "Upload files", drag in this entire folder's contents
   (keeping the folder structure — `.github/`, `scripts/`, `docs/`,
   `requirements.txt`). GitHub will let you upload a whole folder via drag
   and drop in the browser.
4. **Enable GitHub Pages**: Repo → Settings → Pages → under "Build and
   deployment", set Source to "Deploy from a branch", branch `main`,
   folder `/docs`. Save. After a minute, GitHub gives you a URL like
   `https://<your-username>.github.io/rubber-price-dashboard/` — that's
   your live dashboard.
5. **Enable Actions**: Repo → Actions tab → you should see "Update Rubber
   Prices" — click "I understand my workflows, go ahead and enable them"
   if prompted.
6. **Run it once manually** to seed the data: Actions tab → "Update Rubber
   Prices" → "Run workflow" → Run workflow. Wait ~1 minute, then refresh
   your dashboard URL.

From then on, it checks once a day on its own (cron schedule in
`.github/workflows/update.yml`) and commits new data whenever a new
auction is published — no server, no cost.

## Checking/fixing a week's data
Open `docs/data/prices.json` in the repo. Each entry has:
- `grades`: parsed grade → price pairs (what the dashboard charts)
- `raw_ocr_text`: the full OCR output, for manual comparison against the
  image at `docs/data/images/<date>.jpg`
- `needs_review`: true if fewer than 3 rows were parsed cleanly

Just edit the JSON directly in the GitHub web editor if a week needs a
manual fix — the dashboard picks it up on next load.

## Changing the schedule
Edit the `cron` line in `.github/workflows/update.yml`
(currently `0 6 * * *` = daily 06:00 UTC). Auctions appear roughly weekly,
so daily checks are enough to catch new ones quickly without wasting runs.
