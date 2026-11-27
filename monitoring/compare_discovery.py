
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import re

SITEMAP_URL = "https://www.thaipbs.or.th/sitemap/sitemap_news.xml"
LISTING_URL = "https://www.thaipbs.th/news/today"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; DataCollector/1.0)"
}

def extract_article_ids(urls):
    ids = set()

    for url in urls:
        match = re.search(r"/news/content/(\d+)", url)
        if match:
            ids.add(match.group(1))

    return ids

def get_sitemap_urls():
    response = requests.get(
        SITEMAP_URL, headers=HEADERS, timeout=20
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.content, "xml")

    return [
        loc.get_text(strip=True)
        for loc in soup.find_all("loc")
        if "/news/content/" in loc.get_text()
    ]

def get_listing_urls():
    response = requests.get(
        LISTING_URL, headers=HEADERS, timeout=20
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    urls = set()

    for a in soup.find_all("a", href=True):
        href = a["href"]

        if "/news/content/" in href:
            if href.startswith("/"):
                href = "https://www.thaipbs.th" + href

            urls.add(href)

    return urls

sitemap_urls = get_sitemap_urls()
listing_urls = get_listing_urls()

sitemap_ids = extract_article_ids(sitemap_urls)
listing_ids = extract_article_ids(listing_urls)

both = sitemap_ids & listing_ids
sitemap_only = sitemap_ids - listing_ids
listing_only = listing_ids - sitemap_ids

print("\n========== DISCOVERY COMPARISON ==========")
print(f"Sitemap URLs: {len(sitemap_ids)}")
print(f"Listing URLs: {len(listing_ids)}")
print(f"Found in both: {len(both)}")
print(f"Only in Sitemap: {len(sitemap_only)}")
print(f"Only in Listing: {len(listing_only)}")

print("\n--- Sitemap only (Article IDs) ---")
print(sorted(sitemap_only, key=int))

print("\n--- Listing only (Article IDs) ---")
print(sorted(listing_only, key=int))

print("\n--- Found in both (Article IDs) ---")
print(sorted(both, key=int))
