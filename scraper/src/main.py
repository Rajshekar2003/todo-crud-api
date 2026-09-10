import os
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# --- Politeness settings ---
USER_AGENT = "FlyRankInternshipA9/1.0 (+https://github.com/Rajshekar2003/todo-crud-api)"
TIMEOUT_SECONDS = 10
REQUEST_DELAY_SECONDS = 0.5

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "cache")

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


if __name__ == "__main__":
    discover_all_book_urls()