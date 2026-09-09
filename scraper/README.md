# Polite Scraper

A small scraping pipeline that fetches book data from a public practice sandbox, cleans it, validates it, and reports on every run - built for FlyRank's Backend Track internship, Week 5 Assignment A9.

## Target classification

- **Site:** [Books to Scrape](https://books.toscrape.com) - a public sandbox site built specifically for practicing web scraping. The site's own homepage states: "This is a demo website for web scraping purposes. Prices and ratings here were randomly assigned and have no real meaning."
- **Scope:** only the first 3 catalogue pages, and the ~60 individual book pages linked from them.
- **robots.txt result:** requested `https://books.toscrape.com/robots.txt` - returned `404 Not Found`. No robots file exists. A missing file is not itself permission, but combined with the site explicitly describing itself as a scraping sandbox, this target is appropriate to scrape.
- **Data collected:** book title, product URL, price, availability, star rating, and description - all publicly displayed on the page, nothing behind a login or paywall.
- **Why this is appropriate here:** the site was built and is publicly offered for exactly this purpose; no terms are being bypassed, no login or paywall exists, and only the small, clearly public dataset needed for this assignment is collected.

I will not reuse this code on another site without checking its rules and terms first.
