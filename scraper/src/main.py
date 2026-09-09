import os
import time
import requests

# --- Politeness settings ---
USER_AGENT = "FlyRankInternshipA9/1.0 (+https://github.com/Rajshekar2003/todo-crud-api)"
TIMEOUT_SECONDS = 10
REQUEST_DELAY_SECONDS = 0.5

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "cache")


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


if __name__ == "__main__":
    BASE_URL = "https://books.toscrape.com/catalogue/page-1.html"
    fetch_page(BASE_URL, "catalogue-page-1.html")