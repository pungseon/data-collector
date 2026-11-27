
import json
import math
from pathlib import Path
from datetime import datetime
from statistics import median

DATA_DIR = Path("data/news/thaipbs")


def parse_time(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return None
        return dt
    except (ValueError, TypeError):
        return None


def percentile(values, p):
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(p * len(ordered)) - 1)
    return ordered[index]


def main():
    discovery_latencies = []
    collection_latencies = []
    invalid = 0
    total = 0

    for path in DATA_DIR.glob("*.jsonl"):
        with path.open("r", encoding="utf-8") as file:
            for line in file:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    invalid += 1
                    continue

                if record.get("discovery_type") != "newly_discovered":
                    continue

                total += 1
                published = parse_time(record.get("published_at"))
                first_seen = parse_time(record.get("first_seen_at"))
                collected = parse_time(record.get("collected_at"))

                if not all([published, first_seen, collected]):
                    invalid += 1
                    continue

                discovery = (first_seen - published).total_seconds() / 60
                collection = (collected - published).total_seconds() / 60

                if discovery < 0 or collection < 0:
                    invalid += 1
                    continue

                discovery_latencies.append(discovery)
                collection_latencies.append(collection)

    print("\n========== FRESHNESS AUDIT ==========")
    print(f"Newly discovered records: {total}")
    print(f"Valid records: {len(discovery_latencies)}")
    print(f"Invalid records: {invalid}")

    for label, values in [
        ("Discovery latency (first_seen - published)", discovery_latencies),
        ("Collection latency (collected - published)", collection_latencies),
    ]:
        print(f"\n{label}")
        if not values:
            print("No valid measurements")
            continue

        print(f"Median: {median(values):.2f} minutes")
        print(f"P95: {percentile(values, 0.95):.2f} minutes")
        within_15 = sum(v <= 15 for v in values) / len(values) * 100
        print(f"Within 15 minutes: {within_15:.2f}%")

    print("\n====================================")


if __name__ == "__main__":
    main()
