import os
import re
import sys
import time
import json
from datetime import datetime, timezone
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from pydantic import BaseModel, ValidationError, HttpUrl

# --- Politeness settings ---
USER_AGENT = "FlyRankInternshipA9/1.0 (+https://github.com/Rajshekar2003/todo-crud-api)"
TIMEOUT_SECONDS = 10
REQUEST_DELAY_SECONDS = 0.5
RETRY_WAIT_SECONDS = 2
NO_RETRY_STATUS_CODES = {404, 403}

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "cache")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")

BASE_CATALOGUE_URL = "https://books.toscrape.com/catalogue/page-1.html"
MAX_CATALOGUE_PAGES = 3


class FetchError(Exception):
    """Raised when a page could not be fetched, after retries where appropriate."""
    def __init__(self, url: str, reason: str):
        self.url = url
        self.reason = reason
        super().__init__(f"{url}: {reason}")


# --- run-wide counters used by the final report ---
run_stats = {
    "pages_fetched": 0,      # real network fetches
    "cache_hits": 0,         # served from local cache
    "failed_pages": [],      # list of {"url": ..., "reason": ...}
}


def fetch_page(url: str, cache_filename: str) -> str:
    """Fetch a page politely, using a local cache to avoid repeat requests
    to the real site while developing.

    Retries once on a timeout or server error (5xx). Does NOT retry a 404
    (page does not exist) or a 403 (site said no).

    Raises FetchError if the page could not be fetched.
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(CACHE_DIR, cache_filename)

    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            html = f.read()
        print(f"CACHE HIT: {url} ({len(html)} bytes)")
        run_stats["cache_hits"] += 1
        return html

    headers = {"User-Agent": USER_AGENT}
    attempts = 0
    max_attempts = 2  # one try + one retry

    while attempts < max_attempts:
        attempts += 1
        try:
            response = requests.get(url, headers=headers, timeout=TIMEOUT_SECONDS)
        except requests.exceptions.Timeout:
            if attempts < max_attempts:
                print(f"TIMEOUT (retrying): {url}")
                time.sleep(RETRY_WAIT_SECONDS)
                continue
            raise FetchError(url, "timed out after retry")
        except requests.exceptions.RequestException as e:
            raise FetchError(url, f"request failed: {e}")

        if response.status_code == 200:
            response.encoding = "utf-8"
            html = response.text
            with open(cache_path, "w", encoding="utf-8") as f:
                f.write(html)
            print(f"FETCH: {url} ({len(html)} bytes)")
            run_stats["pages_fetched"] += 1
            time.sleep(REQUEST_DELAY_SECONDS)
            return html

        if response.status_code in NO_RETRY_STATUS_CODES:
            raise FetchError(url, f"status {response.status_code} - not retrying")

        if response.status_code >= 500 and attempts < max_attempts:
            print(f"SERVER ERROR {response.status_code} (retrying): {url}")
            time.sleep(RETRY_WAIT_SECONDS)
            continue

        raise FetchError(url, f"status {response.status_code}")

    raise FetchError(url, "exhausted retries")


def extract_book_links(html: str, page_url: str) -> list[str]:
    """Parse a catalogue page and return the absolute URL of every book on it."""
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for article in soup.select("article.product_pod"):
        a_tag = article.select_one("h3 a")
        if a_tag and a_tag.get("href"):
            absolute_url = urljoin(page_url, a_tag["href"])
            links.append(absolute_url)
    return links


def find_next_page_url(html: str, page_url: str) -> str | None:
    """Return the absolute URL of the catalogue's own 'next' link, or None if there isn't one."""
    soup = BeautifulSoup(html, "html.parser")
    next_link = soup.select_one("li.next a")
    if next_link and next_link.get("href"):
        return urljoin(page_url, next_link["href"])
    return None


def discover_all_book_urls() -> list[str]:
    """Walk the catalogue pages (following the site's own 'next' links), stopping
    after MAX_CATALOGUE_PAGES pages, and collect every unique book URL."""
    all_links: list[str] = []
    page_count = 0
    current_url = BASE_CATALOGUE_URL

    while current_url and page_count < MAX_CATALOGUE_PAGES:
        page_count += 1
        cache_filename = f"catalogue-page-{page_count}.html"
        html = fetch_page(current_url, cache_filename)

        page_links = extract_book_links(html, current_url)
        all_links.extend(page_links)

        current_url = find_next_page_url(html, current_url)

    unique_links = list(dict.fromkeys(all_links))  # de-dupe, keep order

    print(f"catalogue_pages={page_count}")
    print(f"discovered={len(all_links)}")
    print(f"unique_urls={len(unique_links)}")

    return unique_links


# --- Stage 3: extract raw book records ---

def _cache_filename_for_book(book_url: str) -> str:
    """Turn a book URL into a safe, unique local cache filename."""
    slug = book_url.rstrip("/").split("/")[-2]
    return f"book-{slug}.html"


def extract_raw_record(html: str, book_url: str, source_page: str) -> dict:
    """Parse a single book detail page and return its 8 raw fields."""
    soup = BeautifulSoup(html, "html.parser")

    product_main = soup.select_one("div.product_main")
    title = product_main.select_one("h1").get_text(strip=True) if product_main else None

    price_tag = soup.select_one("p.price_color")
    price_text = price_tag.get_text(strip=True) if price_tag else None

    availability_tag = soup.select_one("p.availability")
    availability_text = availability_tag.get_text(strip=True) if availability_tag else None

    rating_tag = soup.select_one("p.star-rating")
    rating_text = None
    if rating_tag:
        classes = rating_tag.get("class", [])
        rating_words = [c for c in classes if c != "star-rating"]
        rating_text = rating_words[0] if rating_words else None

    description_heading = soup.select_one("#product_description")
    description = None
    if description_heading:
        description_paragraph = description_heading.find_next_sibling("p")
        if description_paragraph:
            description = description_paragraph.get_text(strip=True)

    return {
        "title": title,
        "product_url": book_url,
        "price_text": price_text,
        "availability_text": availability_text,
        "rating_text": rating_text,
        "description": description,
        "source_page": source_page,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def extract_all_raw_records(book_urls: list[str], source_page: str) -> list[dict]:
    """Fetch and extract the raw record for every book URL. A single broken
    page is logged and skipped - it does not stop the run."""
    records = []
    for book_url in book_urls:
        cache_filename = _cache_filename_for_book(book_url)
        try:
            html = fetch_page(book_url, cache_filename)
            record = extract_raw_record(html, book_url, source_page)
            records.append(record)
        except FetchError as e:
            print(f"SKIPPING (failed): {e.url} - {e.reason}")
            run_stats["failed_pages"].append({"url": e.url, "reason": e.reason})

    print(f"detail_pages={len(records)}")
    return records


# --- Stage 4: clean, validate, store ---

class Book(BaseModel):
    """The clean, checked shape of one book record."""
    title: str
    product_url: HttpUrl
    price_gbp: float
    price_text: str
    availability_text: str
    rating_text: str
    description: str | None
    source_page: HttpUrl
    fetched_at: str


def normalize_price(price_text: str | None) -> float | None:
    """Turn '£51.77' into 51.77. Returns None if it can't be parsed."""
    if not price_text:
        return None
    match = re.search(r"[\d.]+", price_text)
    if not match:
        return None
    try:
        return float(match.group())
    except ValueError:
        return None


def normalize_record(raw: dict) -> dict:
    """Add the clean price_gbp field alongside the original raw fields."""
    normalized = dict(raw)
    normalized["price_gbp"] = normalize_price(raw.get("price_text"))
    return normalized


def validate_records(raw_records: list[dict]) -> tuple[list[dict], list[dict]]:
    """Normalize and validate every record against the Book schema.
    Returns (valid_records, invalid_records_with_reason).
    De-duplicates by product_url so a rerun never produces more than one
    record per book.
    """
    valid_by_url: dict[str, dict] = {}
    invalid: list[dict] = []

    for raw in raw_records:
        normalized = normalize_record(raw)
        try:
            book = Book(**normalized)
        except ValidationError as e:
            invalid.append({
                "record": raw,
                "reason": str(e),
            })
            continue

        canonical_url = str(book.product_url)
        valid_by_url[canonical_url] = json.loads(book.model_dump_json())

    return list(valid_by_url.values()), invalid


def store_records(valid_records: list[dict], invalid_records: list[dict]) -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    books_path = os.path.join(OUTPUT_DIR, "books.json")
    with open(books_path, "w", encoding="utf-8") as f:
        json.dump(valid_records, f, indent=2, ensure_ascii=False)

    errors_path = os.path.join(OUTPUT_DIR, "errors.json")
    with open(errors_path, "w", encoding="utf-8") as f:
        json.dump(invalid_records, f, indent=2, ensure_ascii=False)

    print(f"valid_records={len(valid_records)}")
    print(f"invalid_records={len(invalid_records)}")


# --- Stage 5: run report ---

def write_run_report(start_time: datetime, valid_records: list[dict], invalid_records: list[dict]) -> None:
    end_time = datetime.now(timezone.utc)
    duration_seconds = (end_time - start_time).total_seconds()

    report = {
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "duration_seconds": round(duration_seconds, 2),
        "pages_fetched": run_stats["pages_fetched"],
        "cache_hits": run_stats["cache_hits"],
        "valid_records": len(valid_records),
        "invalid_records": len(invalid_records),
        "failed_pages": run_stats["failed_pages"],
        "failed_page_count": len(run_stats["failed_pages"]),
    }

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    report_path = os.path.join(OUTPUT_DIR, "run-report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"failed_pages={len(run_stats['failed_pages'])}")
    print(f"duration_seconds={report['duration_seconds']}")


if __name__ == "__main__":
    start_time = datetime.now(timezone.utc)

    book_urls = discover_all_book_urls()

    # TEST HOOK: run with `python scraper/src/main.py --test-failure` to add
    # one deliberately broken URL and prove the run survives it.
    if "--test-failure" in sys.argv:
        book_urls.append("https://books.toscrape.com/catalogue/this-book-does-not-exist_9999/index.html")
        print("TEST MODE: injected one fake book URL on purpose")

    raw_records = extract_all_raw_records(book_urls, source_page=BASE_CATALOGUE_URL)
    valid_records, invalid_records = validate_records(raw_records)
    store_records(valid_records, invalid_records)
