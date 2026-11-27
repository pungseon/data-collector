import json
import time
import logging
import requests
import math

from monitoring.telegram_alert import notify_news_run
from statistics import median
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse
from email.utils import parsedate_to_datetime
from bs4 import BeautifulSoup

BASE_URL = "https://www.thaipbs.th"
NEWS_URL = f"{BASE_URL}/news/today"
SITEMAP_URL = "https://www.thaipbs.or.th/sitemap/sitemap_news.xml"
OUTPUT_DIR = Path("data/news/thaipbs")
LOG_DIR = Path("logs")

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

RUN_LOG = LOG_DIR / "news_runs.jsonl"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36"
    )
}

# Maximum 20 requests per minute per domain.
MIN_REQUEST_INTERVAL = 3.1
MAX_RETRIES = 3

last_request_time = 0.0

request_stats = {
    "total": 0,
    "success": 0,
    "failed": 0
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def calculate_latency_minutes(start_time, end_time):
    try:
        start = datetime.fromisoformat(
            start_time.replace("Z", "+00:00")
        )
        end = datetime.fromisoformat(
            end_time.replace("Z", "+00:00")
        )

        latency = (end - start).total_seconds() / 60

        return round(latency, 2) if latency >= 0 else None

    except (ValueError, TypeError, AttributeError):
        return None


def calculate_latency_summary(values):
    values = sorted(v for v in values if v is not None)

    if not values:
        return {
            "count": 0,
            "median_minutes": None,
            "p95_minutes": None
        }

    p95_index = max(0, math.ceil(0.95 * len(values)) - 1)

    return {
        "count": len(values),
        "median_minutes": round(median(values), 2),
        "p95_minutes": round(values[p95_index], 2)
    }


def wait_for_rate_limit():
    global last_request_time

    elapsed = time.monotonic() - last_request_time
    wait_seconds = MIN_REQUEST_INTERVAL - elapsed

    if wait_seconds > 0:
        time.sleep(wait_seconds)

    last_request_time = time.monotonic()


def fetch_page(url, parser="html.parser"):

    global request_stats

    for attempt in range(MAX_RETRIES + 1):
        wait_for_rate_limit()
        request_stats["total"] += 1

        try:
            response = requests.get(
                url,
                headers=HEADERS,
                timeout=30
            )

            if response.status_code == 429 or response.status_code >= 500:
                if attempt < MAX_RETRIES:
                    retry_after = response.headers.get("Retry-After")

                    try:
                        delay = float(retry_after)
                    except (TypeError, ValueError):
                        try:
                            retry_date = parsedate_to_datetime(retry_after)
                            delay = max(
                                0,
                                (retry_date - datetime.now(
                                    retry_date.tzinfo
                                )).total_seconds()
                            )
                        except (TypeError, ValueError, OverflowError):
                            delay = 2 ** attempt

                    delay = min(max(delay, 1), 60)

                    logging.warning(
                        "HTTP %s | Retry %s/%s after %s seconds: %s",
                        response.status_code,
                        attempt + 1,
                        MAX_RETRIES,
                        delay,
                        url
                    )

                    time.sleep(delay)
                    continue

            response.raise_for_status()

            request_stats["success"] += 1

            response.encoding = "utf-8"

            return BeautifulSoup(
                response.content,
                parser,
                from_encoding="utf-8" if parser == "html.parser" else None
            )

        except requests.RequestException:
            logging.exception("Failed to collect article: %s", url)
            if attempt < MAX_RETRIES:
                delay = 2 ** attempt

                logging.warning(
                    "Request error | Retry %s/%s after %s seconds: %s",
                    attempt + 1,
                    MAX_RETRIES,
                    delay,
                    url
                )

                time.sleep(delay)
            else:
                request_stats["failed"] += 1
                raise

    raise requests.RequestException(f"Failed to fetch {url}")


def get_meta(soup, *names):
    for name in names:
        tag = (
            soup.find("meta", attrs={"property": name})
            or soup.find("meta", attrs={"name": name})
        )

        if tag and tag.get("content"):
            return tag["content"].strip()

    return None

def normalize_article_url(url):
    import re

    match = re.search(r"/news/content/(\d+)", url)

    if not match:
        return None

    article_id = match.group(1)

    return f"{BASE_URL}/news/content/{article_id}"

def extract_article_links(soup):
    import re

    links = {}

    for anchor in soup.find_all("a", href=True):
        href = urljoin(BASE_URL, anchor["href"])
        parsed = urlparse(href)

        if parsed.netloc not in {
            "www.thaipbs.th",
            "thaipbs.th"
        }:
            continue

        if not re.fullmatch(
            r"/news/content/\d+/?",
            parsed.path
        ):
            continue

        title = anchor.get_text(" ", strip=True)

        if not title:
            image = anchor.find("img")
            if image:
                title = image.get("alt", "").strip()

        if not title:
            continue

        clean_url = (
            f"https://www.thaipbs.th"
            f"{parsed.path.rstrip('/')}"
        )

        links[clean_url] = title

    return links

def extract_sitemap_links(soup):
    links = {}

    for loc in soup.find_all("loc"):
        raw_url = loc.get_text(strip=True)

        if "/news/content/" not in raw_url:
            continue

        normalized_url = normalize_article_url(raw_url)

        if normalized_url:
            links[normalized_url] = None

    return links

def extract_jsonld(soup):
    for script in soup.find_all(
        "script",
        type="application/ld+json"
    ):
        try:
            data = json.loads(
                script.string or script.get_text()
            )

            objects = data if isinstance(data, list) else [data]

            index = 0

            while index < len(objects):
                obj = objects[index]
                index += 1

                if not isinstance(obj, dict):
                    continue

                if "@graph" in obj:
                    graph = obj["@graph"]

                    if isinstance(graph, list):
                        objects.extend(graph)

                    continue

                article_type = obj.get("@type", [])

                if isinstance(article_type, str):
                    article_type = [article_type]

                if any(
                    item in ("NewsArticle", "Article")
                    for item in article_type
                ):
                    return obj

        except (json.JSONDecodeError, TypeError):
            continue

    return {}


def load_existing_urls():
    existing = set()

    for file_path in OUTPUT_DIR.glob("*.jsonl"):
        try:
            with file_path.open(
                "r",
                encoding="utf-8"
            ) as file:

                for line in file:
                    try:
                        record = json.loads(line)

                        if record.get("url"):
                            normalized_url = normalize_article_url(record["url"])
                            if normalized_url:
                                existing.add(normalized_url)

                    except json.JSONDecodeError:
                        continue

        except OSError:
            logging.exception(
                "Cannot read %s",
                file_path
            )

    return existing


def extract_article(url, listing_title, first_seen_at,discovery_sources=None):
    soup = fetch_page(url)
    article_data = extract_jsonld(soup)

    title = (
        article_data.get("headline")
        or get_meta(soup, "og:title", "twitter:title")
        or listing_title
    )

    published_at = (
        article_data.get("datePublished")
        or get_meta(soup, "article:published_time")
    )

    image = article_data.get("image")

    if isinstance(image, dict):
        image = image.get("url")

    elif isinstance(image, list):
        image = image[0] if image else None

        if isinstance(image, dict):
            image = image.get("url")

    image = image or get_meta(soup, "og:image")

    category = article_data.get("articleSection")

    if isinstance(category, list):
        category = ", ".join(
            str(item) for item in category
        )

    if not category:
        category = get_meta(
            soup,
            "article:section",
            "news_keywords"
        )

    body = article_data.get("articleBody")

    if not body:
        container = (
            soup.find("article")
            or soup.find("main")
        )

        if container:
            paragraphs = container.find_all("p")

            body = "\n".join(
                paragraph.get_text(" ", strip=True)
                for paragraph in paragraphs
                if paragraph.get_text(strip=True)
            )

    return {
        "source": "Thai PBS",
        "title": title,
        "url": url,
        "published_at": published_at,
        "content": body or "",
        "image_url": image,
        "category": category,
        "first_seen_at": first_seen_at,
        "collected_at": now_iso(),
        "discovery_type": "newly_discovered",
        "discovery_sources": discovery_sources or []
    }


def save_jsonl(records):
    if not records:
        logging.info("No new articles to save")
        return

    filename = datetime.now(
        timezone.utc
    ).strftime("%Y%m%d_%H%M%S_%f")

    output_file = OUTPUT_DIR / f"news_{filename}.jsonl"

    with output_file.open(
        "w",
        encoding="utf-8"
    ) as file:

        for record in records:
            file.write(
                json.dumps(
                    record,
                    ensure_ascii=False
                ) + "\n"
            )

    logging.info(
        "Saved %s articles to %s",
        len(records),
        output_file
    )


def save_run_log(record):
    with RUN_LOG.open(
        "a",
        encoding="utf-8"
    ) as file:
        file.write(
            json.dumps(
                record,
                ensure_ascii=False
            ) + "\n"
        )


def main():
    global request_stats

    request_stats = {
        "total": 0,
        "success": 0,
        "failed": 0
    }

    start_time = time.time()
    run_started_at = now_iso()

    logging.info("Starting Thai PBS News Collector")

    discovered = 0
    new_count = 0
    saved_count = 0
    status = "success"
    error = None
    covered_count = 0
    coverage_percent = 0.0

    discovery_latency_summary = {
        "count": 0,
        "median_minutes": None,
        "p95_minutes": None
    }

    publication_latency_summary = {
        "count": 0,
        "median_minutes": None,
        "p95_minutes": None
    }
    try:
        listing_soup = fetch_page(NEWS_URL)
        listing_links = extract_article_links(listing_soup)

        sitemap_soup = fetch_page(SITEMAP_URL, parser="xml")
        sitemap_links = extract_sitemap_links(sitemap_soup)

        article_links = dict(sitemap_links)
        discovery_sources = {}

        for url in sitemap_links:
            discovery_sources[url] = ["sitemap"]

        for url, title in listing_links.items():
            normalized_url = normalize_article_url(url)

            if not normalized_url:
                continue

            article_links[normalized_url] = title

            if "listing" not in discovery_sources.setdefault(
                normalized_url, []
            ):
                discovery_sources[normalized_url].append("listing")

        first_seen_at = now_iso()
        discovered = len(listing_links)

        logging.info(
            "Discovery | Listing: %s | Sitemap: %s | Combined: %s",
            len(listing_links),
            len(sitemap_links),
            len(article_links)
        )

        logging.info(
            "Discovered %s article links",
            discovered
        )

        existing_urls = load_existing_urls()
        new_records = []

        publication_latencies = []
        discovery_latencies = []

        for url, listing_title in article_links.items():

            if url in existing_urls:
                continue

            try:
                record = extract_article(
                    url,
                    listing_title,
                    first_seen_at,
                    discovery_sources.get(url, [])
                )

                new_records.append(record)
                new_count += 1

                publication_latency = calculate_latency_minutes(
                    record.get("published_at"),
                    record.get("collected_at")
                )

                discovery_latency = calculate_latency_minutes(
                    record.get("published_at"),
                    record.get("first_seen_at")
                )

                if publication_latency is not None:
                    publication_latencies.append(publication_latency)

                if discovery_latency is not None:
                    discovery_latencies.append(discovery_latency)

                logging.info(
                    "Collected: %s",
                    record["title"]
                )

            except requests.RequestException:
                logging.exception("Failed to collect article: %s", url)
                if attempt < MAX_RETRIES:
                    delay = 2 ** attempt

                    logging.warning(
                        "Request error | Retry %s/%s after %s seconds: %s",
                        attempt + 1,
                        MAX_RETRIES,
                        delay,
                        url
                    )

                    time.sleep(delay)
                else:
                    request_stats["failed"] += 1
                    raise

            except Exception:
                logging.exception("Parsing failed: %s", url)

        save_jsonl(new_records)
        saved_count = len(new_records)

        known_urls = set(article_links.keys()) & existing_urls

        saved_urls = {
            record["url"]
            for record in new_records
            if record.get("url")
        }
        covered_urls = known_urls | saved_urls

        covered_count = len(covered_urls)

        coverage_percent = (
            round(covered_count / discovered * 100, 2)
            if discovered > 0 else 0
        )

        discovery_latency_summary = calculate_latency_summary(
            discovery_latencies
        )

        publication_latency_summary = calculate_latency_summary(
            publication_latencies
        )

    except Exception as exc:
        status = "failed"
        error = str(exc)

        logging.exception("News collector failed")

    duration = round(
        time.time() - start_time,
        2
    )

    request_success_rate = (
        request_stats["success"] / request_stats["total"] * 100
        if request_stats["total"] > 0
        else 0
    )

    run_record = {
        "source": "news",
        "started_at": run_started_at,
        "finished_at": now_iso(),
        "status": status,
        "duration_seconds": duration,
        "discovered_links": discovered,
        "new_articles": new_count,
        "saved_articles": saved_count,
        "requests_total": request_stats["total"],
        "requests_success": request_stats["success"],
        "requests_failed": request_stats["failed"],
        "request_success_rate": round(
            request_success_rate,
            2
        ),
        "error": error,
        "covered_articles": covered_count,
        "coverage_percent": coverage_percent,

        "discovery_latency": discovery_latency_summary,
        "publication_latency": publication_latency_summary
    }

    save_run_log(run_record)
    try:
        notify_news_run(run_record)
    except Exception:
        logging.exception("Telegram notification failed")


    logging.info(
        "Completed | Discovered: %s | New: %s | Saved: %s | "
        "Requests: %s | Request success: %.2f%% | Duration: %.2fs",
        discovered,
        new_count,
        saved_count,
        request_stats["total"],
        request_success_rate,
        duration
    )


if __name__ == "__main__":
    main()
