import json
from pathlib import Path

DATA_DIR = Path("data/news/thaipbs")

REQUIRED_FIELDS = [
    "title",
    "url",
    "published_at",
    "content",
    "image_url",
    "category",
    "collected_at"
]


def check_quality():
    records = []
    malformed = 0

    for path in DATA_DIR.glob("*.jsonl"):
        with path.open("r", encoding="utf-8") as file:
            for line in file:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    malformed += 1

    total = len(records)

    if total == 0:
        print("No records found")
        return

    missing_count = 0
    missing_by_field = {field: 0 for field in REQUIRED_FIELDS}
    urls = []

    for record in records:
        for field in REQUIRED_FIELDS:
            if record.get(field) is None or record.get(field) == "":
                missing_count += 1
                missing_by_field[field] += 1

        if record.get("url"):
            urls.append(record["url"])

    duplicate_count = len(urls) - len(set(urls))

    total_fields = total * len(REQUIRED_FIELDS)
    completeness = (
        (total_fields - missing_count) / total_fields * 100
    )

    print("\n===== DATA QUALITY REPORT =====")
    print("Total records:", total)
    print("Field completeness:", round(completeness, 2), "%")
    print("Duplicate records:", duplicate_count)
    print("Malformed records:", malformed)

    print("\nMissing fields:")

    for field, count in missing_by_field.items():
        print(f"{field}: {count}")

    print("================================")


def inspect_missing_records():
    print("\n===== MISSING RECORD INSPECTION =====")

    for path in DATA_DIR.glob("*.jsonl"):
        with path.open("r", encoding="utf-8") as file:
            for line in file:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue

                missing = [
                    field for field in REQUIRED_FIELDS
                    if not record.get(field)
                ]

                if missing:
                    print("\nTitle:", record.get("title"))
                    print("URL:", record.get("url"))
                    print("Missing:", missing)

if __name__ == "__main__":
    check_quality()
    inspect_missing_records()
