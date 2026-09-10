import os
import re
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

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "cache")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")

BASE_CATALOGUE_URL = "https://books.toscrape.com/catalogue/page-1.html"
MAX_CATALOGUE_PAGES = 3


def fetch_page(url: str, cache_filename: str) -> str:
    """Fetch a page politely, using a local cache to avoid repeat requests
    to the real site while developing.

    Returns the HTML content as a string.
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(CACHE_DIR, cache_filename)

    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            html = f.read()
        print(f"CACHE HIT: {url} ({len(html)} bytes)")
        return html

    headers = {"User-Agent": USER_AGENT}
    response = requests.get(url, headers=headers, timeout=TIMEOUT_SECONDS)

    if response.status_code != 200:
        raise RuntimeError(f"Failed to fetch {url}: status {response.status_code}")

    response.encoding = "utf-8"  # the site doesn't always declare charset; force correct decoding
    html = response.text
    with open(cache_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"FETCH: {url} ({len(html)} bytes)")

    time.sleep(REQUEST_DELAY_SECONDS)
    return html


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
        # classes look like ["star-rating", "Three"] - the rating word is the extra class
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
    """Fetch and extract the raw record for every book URL."""
    records = []
    for book_url in book_urls:
        cache_filename = _cache_filename_for_book(book_url)
        html = fetch_page(book_url, cache_filename)
        record = extract_raw_record(html, book_url, source_page)
        records.append(record)

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
    De-duplicates by product_url (the canonical identity) so a rerun
    never produces more than one record per book.
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


if __name__ == "__main__":
    book_urls = discover_all_book_urls()
    raw_records = extract_all_raw_records(book_urls, source_page=BASE_CATALOGUE_URL)
    valid_records, invalid_records = validate_records(raw_records)
    store_records(valid_records, invalid_records)