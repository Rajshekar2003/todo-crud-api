# Polite Scraper

A small scraping pipeline that fetches book data from a public practice sandbox, cleans it, validates it, and reports on every run - built for FlyRank's Backend Track internship, Week 5 Assignment A9.

## Target classification

- **Site:** [Books to Scrape](https://books.toscrape.com) - a public sandbox site built specifically for practicing web scraping. The site's own homepage states: "This is a demo website for web scraping purposes. Prices and ratings here were randomly assigned and have no real meaning."
- **Scope:** only the first 3 catalogue pages, and the ~60 individual book pages linked from them.
- **robots.txt result:** requested `https://books.toscrape.com/robots.txt` - returned `404 Not Found`. No robots file exists. A missing file is not itself permission, but combined with the site explicitly describing itself as a scraping sandbox, this target is appropriate to scrape.
- **Data collected:** book title, product URL, price, availability, star rating, and description - all publicly displayed on the page, nothing behind a login or paywall.
- **Why this is appropriate here:** the site was built and is publicly offered for exactly this purpose; no terms are being bypassed, no login or paywall exists, and only the small, clearly public dataset needed for this assignment is collected.

I will not reuse this code on another site without checking its rules and terms first.

## Lane and setup

- **Language:** Python 3.10+
- **Libraries:** `requests` (HTTP), `beautifulsoup4` (HTML parsing), `pydantic` (schema validation)

Install dependencies (from the repo root, with your virtual environment active):

```bash
pip install requests beautifulsoup4 pydantic
```

## Run command

```bash
python scraper/src/main.py
```

To deliberately test the failure-handling in Stage 5 (adds one fake book URL on purpose, never hits the real site with it):

```bash
python scraper/src/main.py --test-failure
```

Both commands can be run repeatedly - the local `cache/` folder means only the first run makes real network requests; every run after that reads from disk.

## What it produces

- `output/books.json` - the 60 clean, validated book records
- `output/errors.json` - any records that failed schema validation, with the reason
- `output/run-report.json` - honest numbers about the run itself

## Record schema

Each record in `books.json` has this shape:

| Field | Type | Notes |
|---|---|---|
| `title` | string | book title |
| `product_url` | URL | the book's canonical page - its stable identity |
| `price_gbp` | number | cleaned price, e.g. `51.77` |
| `price_text` | string | original price text as shown on the page, e.g. `"£51.77"` |
| `availability_text` | string | original stock text, e.g. `"In stock (22 available)"` |
| `rating_text` | string | star rating word, e.g. `"Three"` |
| `description` | string or null | book description; `null` when the page has none - never invented |
| `source_page` | URL | which catalogue page this book was discovered on |
| `fetched_at` | string | ISO timestamp of when this page was fetched |

## Politeness rules followed

- **User-agent:** every request identifies itself as `FlyRankInternshipA9/1.0` with a link back to this repo.
- **Timeout:** every request gives up after 10 seconds rather than hanging forever.
- **Delay:** at least 0.5 seconds between real requests to the site. Cached pages need no delay - they never leave the computer.
- **Cache:** every fetched page is saved locally under `cache/` (git-ignored) so repeated development runs never re-hit the real site.
- **Retries:** a timeout or server error (5xx) is retried once after a short wait. A `404` or `403` is never retried - the page either doesn't exist or the site said no.
- **Status check:** only a `200` response is treated as real data; anything else is a failed fetch, not HTML to parse.

## Sample run report

A real `output/run-report.json` from a completed run:

```json
{
  "start_time": "2026-09-10T07:20:43.277691+00:00",
  "end_time": "2026-09-10T07:20:44.490581+00:00",
  "duration_seconds": 1.21,
  "pages_fetched": 0,
  "cache_hits": 63,
  "valid_records": 60,
  "invalid_records": 0,
  "failed_pages": [
    {
      "url": "https://books.toscrape.com/catalogue/this-book-does-not-exist_9999/index.html",
      "reason": "request failed: could not resolve host"
    }
  ],
  "failed_page_count": 1
}
```
(This particular run used `--test-failure`, which is why one page is listed as failed - the run still finished with all 60 real records intact.)

## Why this needed no browser

All the data collected here - title, price, availability, rating, description - is present directly in the HTML the server sends back on a plain request. Nothing on these pages is loaded afterward by JavaScript. A browser (like Playwright) would only add startup cost, memory use, and complexity for data that a simple HTTP request already receives in full.

## Ethics note

This scraper only touches a site explicitly built and offered for scraping practice. In general: use an official API when one exists rather than scraping; never bypass logins, paywalls, or explicit blocks; collect only the data actually needed for the task; and always check a site's own stated rules and terms before reusing this kind of code elsewhere.

## Known limitation

The scraper currently assumes the site's HTML structure (CSS classes like `product_pod`, `price_color`, etc.) stays stable. If Books to Scrape ever changes its page layout, the selectors in `extract_raw_record` and `extract_book_links` would need to be updated.