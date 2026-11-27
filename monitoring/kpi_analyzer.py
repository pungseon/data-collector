import json
import math
import statistics

from datetime import datetime, timezone
from pathlib import Path


# ==========================================
# CONFIGURATION
# ==========================================

LOG_FILE = Path("logs/runs.jsonl")
NEWS_RUN_LOG = Path("logs/news_runs.jsonl")

NEWS_DIR = Path("data/news/thaipbs")
YOUTUBE_DIR = Path("data/youtube")

REPORT_DIR = Path("reports")
REPORT_DIR.mkdir(parents=True, exist_ok=True)

NEWS_INTERVAL_SECONDS = 300

REQUIRED_FIELDS = [
    "title",
    "url",
    "published_at",
    "content",
    "image_url",
    "category",
    "collected_at",
]

TARGETS = {
    "freshness_15m": 90,          # At least 90% within 15 minutes
    "freshness_p95": 30,          # p95 no more than 30 minutes
    "request_success": 98,        # At least 98%
    "field_completeness": 99,     # At least 99%
    "news_coverage": 95,          # At least 95%
}


# ==========================================
# LOAD JSONL
# ==========================================

def load_jsonl(path):
    """Load JSONL records and count malformed lines."""
    records = []
    malformed = 0

    if not path.exists():
        return records, malformed

    with path.open("r", encoding="utf-8-sig") as file:
        for line in file:
            if not line.strip():
                continue

            try:
                item = json.loads(line)
                if isinstance(item, dict):
                    records.append(item)
                else:
                    malformed += 1
            except json.JSONDecodeError:
                malformed += 1

    return records, malformed


def load_all_records(directory):
    """Load all JSONL files in a directory."""
    records = []
    malformed = 0

    if not directory.exists():
        return records, malformed

    for path in sorted(directory.glob("*.jsonl")):
        data, errors = load_jsonl(path)
        records.extend(data)
        malformed += errors

    return records, malformed


# ==========================================
# DATETIME AND STATISTICS
# ==========================================

def parse_datetime(value):
    """Parse timezone-aware ISO8601 timestamps."""
    if not value or not isinstance(value, str):
        return None

    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))

        # Do not silently assume a timezone for naive timestamps.
        if result.tzinfo is None:
            return None

        return result

    except (ValueError, TypeError, AttributeError):
        return None


def percentile(values, percent):
    """Calculate an interpolated percentile."""
    if not values:
        return None

    values = sorted(float(value) for value in values)

    if len(values) == 1:
        return round(values[0], 2)

    index = (len(values) - 1) * percent / 100
    lower = math.floor(index)
    upper = math.ceil(index)

    if lower == upper:
        return round(values[lower], 2)

    result = (
        values[lower] * (upper - index)
        + values[upper] * (index - lower)
    )

    return round(result, 2)


def calculate_percentage(numerator, denominator):
    if denominator == 0:
        return 0.0

    return round(numerator / denominator * 100, 2)


def summarize_values(values):
    """Return count, median, p95, min and max for numeric values."""
    clean_values = [
        float(value)
        for value in values
        if isinstance(value, (int, float)) and math.isfinite(value)
    ]

    if not clean_values:
        return {
            "count": 0,
            "median": None,
            "p95": None,
            "min": None,
            "max": None,
        }

    return {
        "count": len(clean_values),
        "median": round(statistics.median(clean_values), 2),
        "p95": percentile(clean_values, 95),
        "min": round(min(clean_values), 2),
        "max": round(max(clean_values), 2),
    }


# ==========================================
# EXECUTION METRICS
# ==========================================

def analyze_execution():
    runs, malformed = load_jsonl(LOG_FILE)

    successful = sum(
        1 for run in runs
        if run.get("status") == "success"
    )

    failed = len(runs) - successful

    durations = [
        float(run["duration_seconds"])
        for run in runs
        if isinstance(run.get("duration_seconds"), (int, float))
        and math.isfinite(run["duration_seconds"])
        and run["duration_seconds"] >= 0
    ]

    return {
        "total_runs": len(runs),
        "successful": successful,
        "failed": failed,
        "success_rate": calculate_percentage(successful, len(runs)),
        "average_duration": (
            round(statistics.mean(durations), 2) if durations else None
        ),
        "p95_duration": percentile(durations, 95),
        "malformed_logs": malformed,
    }


# ==========================================
# NEWS DATA QUALITY
# ==========================================

def analyze_news_quality(news):
    total = len(news)
    total_fields = total * len(REQUIRED_FIELDS)

    missing = sum(
        1
        for record in news
        for field in REQUIRED_FIELDS
        if record.get(field) is None or record.get(field) == ""
    )

    completeness = calculate_percentage(
        total_fields - missing,
        total_fields,
    )

    urls = [
        record.get("url")
        for record in news
        if record.get("url")
    ]

    duplicates = len(urls) - len(set(urls))

    return {
        "total_records": total,
        "field_completeness": completeness,
        "missing_field_values": missing,
        "duplicates": duplicates,
    }


# ==========================================
# NEWS FRESHNESS
# ==========================================

def analyze_freshness(news):
    historical = []
    newly_discovered = []
    invalid_timestamps = 0

    for record in news:
        published = parse_datetime(record.get("published_at"))
        collected = parse_datetime(record.get("collected_at"))

        if published is None or collected is None:
            invalid_timestamps += 1
            continue

        latency = (collected - published).total_seconds() / 60

        if latency < 0:
            invalid_timestamps += 1
            continue

        if record.get("discovery_type") == "newly_discovered":
            newly_discovered.append(latency)
        else:
            historical.append(latency)

    def summarize_freshness(values):
        within_15 = sum(value <= 15 for value in values)

        return {
            "count": len(values),
            "median": (
                round(statistics.median(values), 2) if values else None
            ),
            "p95": percentile(values, 95),
            "within_15_min_count": within_15,
            "within_15_min_percent": calculate_percentage(
                within_15, len(values)
            ),
        }

    return {
        "newly_discovered": summarize_freshness(newly_discovered),
        "historical": summarize_freshness(historical),
        "invalid_timestamps": invalid_timestamps,
    }


# ==========================================
# NEWS RUN LOG METRICS
# ==========================================

def load_news_runs():
    runs, malformed = load_jsonl(NEWS_RUN_LOG)
    return runs, malformed


def analyze_requests(news_runs, malformed):
    total = sum(
        int(run.get("requests_total", 0) or 0)
        for run in news_runs
    )

    successful = sum(
        int(run.get("requests_success", 0) or 0)
        for run in news_runs
    )

    failed = sum(
        int(run.get("requests_failed", 0) or 0)
        for run in news_runs
    )

    return {
        "total_runs": len(news_runs),
        "total_requests": total,
        "successful_requests": successful,
        "failed_requests": failed,
        "success_rate": calculate_percentage(successful, total),
        "malformed_logs": malformed,
    }


def analyze_news_duration(news_runs, malformed):
    durations = [
        float(run["duration_seconds"])
        for run in news_runs
        if isinstance(run.get("duration_seconds"), (int, float))
        and math.isfinite(run["duration_seconds"])
        and run["duration_seconds"] >= 0
    ]

    within_interval = sum(
        duration < NEWS_INTERVAL_SECONDS
        for duration in durations
    )

    return {
        "total_rounds": len(durations),
        "average_seconds": (
            round(statistics.mean(durations), 2) if durations else None
        ),
        "p95_seconds": percentile(durations, 95),
        "within_interval": within_interval,
        "within_interval_percent": calculate_percentage(
            within_interval, len(durations)
        ),
        "interval_seconds": NEWS_INTERVAL_SECONDS,
        "malformed_logs": malformed,
    }


# ==========================================
# NEWS COVERAGE
# ==========================================


def analyze_news_coverage(news_runs):
    """
    Coverage is based only on runs that contain coverage metrics.
    It measures URLs exposed on the Thai PBS listing page.
    """

    coverage_values = []
    covered_total = 0
    discovered_total = 0

    for run in news_runs:
        coverage = run.get("coverage_percent")
        discovered = run.get("discovered_links")
        covered = run.get("covered_articles")

        # Only include runs that actually recorded coverage metrics.
        if (
            coverage is None
            and not (
                isinstance(discovered, (int, float))
                and isinstance(covered, (int, float))
                and discovered > 0
            )
        ):
            continue

        if isinstance(coverage, (int, float)):
            coverage_values.append(float(coverage))
        elif discovered > 0:
            coverage_values.append(
                float(covered) / float(discovered) * 100
            )

        if isinstance(discovered, (int, float)):
            discovered_total += int(discovered)

        if isinstance(covered, (int, float)):
            covered_total += int(covered)

    if not coverage_values:
        return {
            "total_rounds": 0,
            "average_coverage": None,
            "coverage_pass_rate": None,
            "rounds_meeting_target": 0,
            "target_percent": TARGETS["news_coverage"],
            "covered_urls_sum": 0,
            "discovered_urls_sum": 0
        }

    passed = sum(
        value >= TARGETS["news_coverage"]
        for value in coverage_values
    )

    return {
        "total_rounds": len(coverage_values),
        "average_coverage": round(
            statistics.mean(coverage_values), 2
        ),
        "coverage_pass_rate": calculate_percentage(
            passed, len(coverage_values)
        ),
        "rounds_meeting_target": passed,
        "target_percent": TARGETS["news_coverage"],
        "covered_urls_sum": covered_total,
        "discovered_urls_sum": discovered_total
    }



# ==========================================
# DISCOVERY LATENCY
# ==========================================

def analyze_discovery_latency(news):
    """
    Calculate publication-to-first-observed-detection latency from article
    records, using first_seen_at - published_at.

    first_seen_at is the time our collector observed the article on the
    listing page; it is not necessarily the exact time the site first
    published the article to that listing.
    """
    values = []
    invalid = 0

    for record in news:
        if record.get("discovery_type") != "newly_discovered":
            continue

        published = parse_datetime(record.get("published_at"))
        first_seen = parse_datetime(record.get("first_seen_at"))

        if published is None or first_seen is None:
            invalid += 1
            continue

        latency = (first_seen - published).total_seconds() / 60

        if latency < 0:
            invalid += 1
            continue

        values.append(latency)

    return {
        "measured_articles": len(values),
        "median_minutes": (
            round(statistics.median(values), 2) if values else None
        ),
        "p95_minutes": percentile(values, 95),
        "within_15_min_count": sum(value <= 15 for value in values),
        "within_15_min_percent": calculate_percentage(
            sum(value <= 15 for value in values), len(values)
        ),
        "invalid_records": invalid,
        "definition": "first_seen_at - published_at",
    }


def analyze_publication_latency(news):
    """
    Calculate publication-to-collection latency from article records,
    using collected_at - published_at.
    """
    values = []
    invalid = 0

    for record in news:
        if record.get("discovery_type") != "newly_discovered":
            continue

        published = parse_datetime(record.get("published_at"))
        collected = parse_datetime(record.get("collected_at"))

        if published is None or collected is None:
            invalid += 1
            continue

        latency = (collected - published).total_seconds() / 60

        if latency < 0:
            invalid += 1
            continue

        values.append(latency)

    return {
        "measured_articles": len(values),
        "median_minutes": (
            round(statistics.median(values), 2) if values else None
        ),
        "p95_minutes": percentile(values, 95),
        "within_15_min_count": sum(value <= 15 for value in values),
        "within_15_min_percent": calculate_percentage(
            sum(value <= 15 for value in values), len(values)
        ),
        "invalid_records": invalid,
        "definition": "collected_at - published_at",
    }


# ==========================================
# YOUTUBE DATA SUMMARY
# ==========================================

def analyze_youtube():
    records, malformed = load_all_records(YOUTUBE_DIR)

    return {
        "total_records": len(records),
        "malformed_records": malformed,
    }


# ==========================================
# KPI EVALUATION
# ==========================================

def evaluate_kpis(quality, freshness, requests, duration, coverage):
    new = freshness["newly_discovered"]

    return {
        "freshness_within_15_min": (
            new["within_15_min_percent"] >= TARGETS["freshness_15m"]
            if new["count"] > 0 else None
        ),

        "freshness_p95": (
            new["p95"] <= TARGETS["freshness_p95"]
            if new["p95"] is not None else None
        ),

        "news_coverage": (
            coverage["average_coverage"] >= TARGETS["news_coverage"]
            if coverage["average_coverage"] is not None else None
        ),

        "request_success_rate": (
            requests["success_rate"] >= TARGETS["request_success"]
            if requests["total_requests"] > 0 else None
        ),

        "field_completeness": (
            quality["field_completeness"] >= TARGETS["field_completeness"]
            if quality["total_records"] > 0 else None
        ),

        "zero_duplicates": quality["duplicates"] == 0,

        "round_duration": (
            duration["p95_seconds"] < NEWS_INTERVAL_SECONDS
            if duration["p95_seconds"] is not None else None
        ),
    }


# ==========================================
# PRINT REPORT
# ==========================================

def print_section(title):
    print(f"\n[{title}]")
    print("-" * 50)


def print_report(report):
    print("\n" + "=" * 60)
    print("                 DATA COLLECTION KPI REPORT")
    print("=" * 60)

    execution = report["execution"]
    quality = report["news_quality"]
    freshness = report["news_freshness"]
    requests = report["news_requests"]
    duration = report["news_duration"]
    coverage = report["news_coverage"]
    discovery = report["discovery_latency"]
    youtube = report["youtube"]

    print_section("SCHEDULER EXECUTION")
    print("Total runs:", execution["total_runs"])
    print("Successful:", execution["successful"])
    print("Failed:", execution["failed"])
    print("Success rate:", execution["success_rate"], "%")
    print("Average duration:", execution["average_duration"], "seconds")
    print("p95 duration:", execution["p95_duration"], "seconds")
    print("Malformed scheduler logs:", execution["malformed_logs"])

    print_section("NEWS DATA QUALITY")
    print("Total records:", quality["total_records"])
    print("Field completeness:", quality["field_completeness"], "%")
    print("Missing fields:", quality["missing_field_values"])
    print("Duplicates:", quality["duplicates"])
    print("Malformed records:", report["news_malformed"])

    print_section("NEWS FRESHNESS - NEWLY DISCOVERED")
    new = freshness["newly_discovered"]
    print("Records:", new["count"])
    print("Median:", new["median"], "minutes")
    print("p95:", new["p95"], "minutes")
    print("Within 15 minutes:", new["within_15_min_percent"], "%")

    print_section("HISTORICAL NEWS FRESHNESS")
    old = freshness["historical"]
    print("Records:", old["count"])
    print("Median:", old["median"], "minutes")
    print("p95:", old["p95"], "minutes")

    print_section("NEWS REQUEST METRICS")
    print("Total requests:", requests["total_requests"])
    print("Successful:", requests["successful_requests"])
    print("Failed:", requests["failed_requests"])
    print("Success rate:", requests["success_rate"], "%")
    print("Malformed request logs:", requests["malformed_logs"])

    print_section("NEWS ROUND DURATION")
    print("Total rounds:", duration["total_rounds"])
    print("Average:", duration["average_seconds"], "seconds")
    print("p95:", duration["p95_seconds"], "seconds")
    print("Within interval:", duration["within_interval_percent"], "%")
    print("Configured interval:", duration["interval_seconds"], "seconds")

    print_section("NEWS COVERAGE")
    print("Total rounds with coverage:", coverage["total_rounds"])
    print("Average coverage:", coverage["average_coverage"], "%")
    print(
        "Rounds meeting target:",
        coverage["rounds_meeting_target"],
        "/",
        coverage["total_rounds"],
    )
    print("Coverage pass rate:", coverage["coverage_pass_rate"], "%")
    print(
        "Covered/discovered URL totals:",
        coverage["covered_urls_sum"],
        "/",
        coverage["discovered_urls_sum"],
    )
    print(
        "Definition: coverage of URLs exposed on the Thai PBS listing page."
    )

    print_section("NEWS DISCOVERY LATENCY")
    print("Measured new articles:", discovery["measured_articles"])
    print("Median:", discovery["median_minutes"], "minutes")
    print("p95:", discovery["p95_minutes"], "minutes")
    print("Within 15 minutes:", discovery["within_15_min_percent"], "%")
    print("Invalid records:", discovery["invalid_records"])
    print("Definition:", discovery["definition"])
    print(
        "Note: first_seen_at is when our collector observed the article",
    )
    print("on the listing page, not necessarily when it first appeared there.")

    publication = report["publication_latency"]
    print_section("NEWS PUBLICATION-TO-COLLECTION LATENCY")
    print("Measured new articles:", publication["measured_articles"])
    print("Median:", publication["median_minutes"], "minutes")
    print("p95:", publication["p95_minutes"], "minutes")
    print("Within 15 minutes:", publication["within_15_min_percent"], "%")
    print("Invalid records:", publication["invalid_records"])

    print_section("YOUTUBE")
    print("Total records:", youtube["total_records"])
    print("Malformed:", youtube["malformed_records"])

    print_section("KPI EVALUATION")
    for name, result in report["kpi_checks"].items():
        if result is True:
            status = "PASS"
        elif result is False:
            status = "FAIL"
        else:
            status = "NOT ENOUGH DATA"

        print(f"{name:30}: {status}")

    print("\n" + "=" * 60)


# ==========================================
# MAIN
# ==========================================

def main():
    execution = analyze_execution()

    news, news_malformed = load_all_records(NEWS_DIR)

    quality = analyze_news_quality(news)
    freshness = analyze_freshness(news)

    news_runs, news_run_malformed = load_news_runs()

    requests = analyze_requests(news_runs, news_run_malformed)
    duration = analyze_news_duration(news_runs, news_run_malformed)
    coverage = analyze_news_coverage(news_runs)
    discovery_latency = analyze_discovery_latency(news)
    publication_latency = analyze_publication_latency(news)

    youtube = analyze_youtube()

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "execution": execution,
        "news_quality": quality,
        "news_freshness": freshness,
        "news_requests": requests,
        "news_duration": duration,
        "news_coverage": coverage,
        "discovery_latency": discovery_latency,
        "publication_latency": publication_latency,
        "news_malformed": news_malformed,
        "youtube": youtube,
    }

    report["kpi_checks"] = evaluate_kpis(
        quality,
        freshness,
        requests,
        duration,
        coverage,
    )

    print_report(report)

    output = REPORT_DIR / "kpi_report.json"

    with output.open("w", encoding="utf-8") as file:
        json.dump(
            report,
            file,
            ensure_ascii=False,
            indent=4,
        )

    print("\nReport saved:", output)


if __name__ == "__main__":
    main()
