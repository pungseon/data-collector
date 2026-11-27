
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

LOG_FILE = Path("logs/discovery_history.jsonl")
THAI_TZ = ZoneInfo("Asia/Bangkok")

def record_discovery(sitemap_ids, listing_ids):
    now = datetime.now(THAI_TZ).isoformat()

    all_ids = set(sitemap_ids) | set(listing_ids)

    records = []

    if LOG_FILE.exists():
        with LOG_FILE.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    records.append(json.loads(line))

    previous_ids = {r["article_id"] for r in records}

    new_ids = all_ids - previous_ids

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    with LOG_FILE.open("a", encoding="utf-8") as f:
        for article_id in sorted(new_ids, key=int):
            sources = []

            if article_id in sitemap_ids:
                sources.append("sitemap")

            if article_id in listing_ids:
                sources.append("listing")

            record = {
                "article_id": article_id,
                "discovery_sources": sources,
                "first_seen_at": now
            }

            f.write(
                json.dumps(record, ensure_ascii=False) + "\n"
            )

    print(f"New articles discovered: {len(new_ids)}")
    print(f"History records: {LOG_FILE}")
