import os
import json
import time
import requests

from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("YOUTUBE_API_KEY")

BASE_URL = "https://www.googleapis.com/youtube/v3"

KEYWORDS = [
    "Artificial Intelligence",
    "Data Engineering",
    "Python Programming",
    "Machine Learning",
    "Technology Thailand"
]

OUTPUT_DIR = Path("data/youtube")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def search_videos(keyword, max_pages=2):
    if not API_KEY:
        raise ValueError("Missing YOUTUBE_API_KEY in .env")

    results = []
    next_page_token = None

    for page in range(max_pages):

        params = {
            "part": "snippet",
            "q": keyword,
            "type": "video",
            "maxResults": 50,
            "order": "date",
            "key": API_KEY
        }

        if next_page_token:
            params["pageToken"] = next_page_token

        response = requests.get(
            f"{BASE_URL}/search",
            params=params,
            timeout=30
        )

        response.raise_for_status()
        data = response.json()

        collected_at = now_iso()

        for item in data.get("items", []):
            video = {
                "video_id": item["id"]["videoId"],
                "keyword": keyword,
                "title": item["snippet"]["title"],
                "channel_title": item["snippet"]["channelTitle"],
                "published_at": item["snippet"]["publishedAt"],
                "collected_at": collected_at
            }

            results.append(video)

        next_page_token = data.get("nextPageToken")

        if not next_page_token:
            break

    return results

def get_video_statistics(video_ids):
    if not video_ids:
        return []

    results = []

    # YouTube API accepts up to 50 IDs per request
    for i in range(0, len(video_ids), 50):

        batch = video_ids[i:i + 50]

        params = {
            "part": "statistics,contentDetails,snippet",
            "id": ",".join(batch),
            "key": API_KEY
        }

        response = requests.get(
            f"{BASE_URL}/videos",
            params=params,
            timeout=30
        )

        response.raise_for_status()
        data = response.json()

        collected_at = now_iso()

        for item in data.get("items", []):
            stats = item.get("statistics", {})
            details = item.get("contentDetails", {})

            record = {
                "video_id": item["id"],
                "title": item["snippet"]["title"],
                "published_at": item["snippet"]["publishedAt"],
                "collected_at": collected_at,
                "views": int(stats.get("viewCount", 0)),
                "likes": int(stats.get("likeCount", 0)),
                "comment_count": int(stats.get("commentCount", 0)),
                "duration": details.get("duration")
            }

            results.append(record)

    return results



def get_video_comments(video_ids, max_comments=100):
    if not API_KEY:
        raise ValueError("Missing YOUTUBE_API_KEY in .env")

    results = []
    video_status = []

    for video_id in video_ids:
        next_page_token = None
        collected_count = 0
        status = "success"
        error_message = None

        while collected_count < max_comments:
            params = {
                "part": "snippet",
                "videoId": video_id,
                "maxResults": min(100, max_comments - collected_count),
                "order": "relevance",
                "textFormat": "plainText",
                "key": API_KEY
            }

            if next_page_token:
                params["pageToken"] = next_page_token

            try:
                response = requests.get(
                    f"{BASE_URL}/commentThreads",
                    params=params,
                    timeout=30
                )

                if response.status_code == 403:
                    error_data = response.json()
                    error_reason = (
                        error_data.get("error", {})
                        .get("errors", [{}])[0]
                        .get("reason", "")
                    )

                    if error_reason == "commentsDisabled":
                        status = "comments_disabled"
                        break

                response.raise_for_status()
                data = response.json()

                for item in data.get("items", []):
                    comment = item["snippet"]["topLevelComment"]
                    snippet = comment["snippet"]

                    results.append({
                        "video_id": video_id,
                        "comment_id": comment["id"],
                        "author": snippet.get("authorDisplayName"),
                        "text": snippet.get("textDisplay"),
                        "like_count": snippet.get("likeCount", 0),
                        "published_at": snippet.get("publishedAt"),
                        "collected_at": now_iso()
                    })

                    collected_count += 1

                next_page_token = data.get("nextPageToken")

                if not next_page_token:
                    break

            except requests.RequestException as error:
                status = "failed"
                error_message = str(error)
                break

        if status == "success" and collected_count == 0:
            status = "no_comments"

        video_status.append({
            "video_id": video_id,
            "status": status,
            "comments_collected": collected_count,
            "error": error_message,
            "collected_at": now_iso()
        })

        print(
            f"Video {video_id} | {status} | "
            f"Comments: {collected_count}"
        )

    return results, video_status



def save_jsonl(records):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    output_file = OUTPUT_DIR / f"search_{timestamp}.jsonl"

    with output_file.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"Saved {len(records)} records to {output_file}")



def main():
    all_videos = []

    hour_index = datetime.now(timezone.utc).hour % len(KEYWORDS)
    selected_keywords = [KEYWORDS[hour_index]]

    for keyword in selected_keywords:
        print(f"Searching: {keyword}")

        try:
            videos = search_videos(keyword, max_pages=2)
            all_videos.extend(videos)

            print(f"Found {len(videos)} videos")

        except requests.RequestException as error:
            print(f"Request failed: {error}")

        time.sleep(1)

    unique_videos = {
        video["video_id"]: video
        for video in all_videos
    }

    videos = list(unique_videos.values())

    save_jsonl(videos)

    print("Fetching video statistics...")

    try:
        video_ids = [v["video_id"] for v in videos]

        statistics = get_video_statistics(video_ids)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = OUTPUT_DIR / f"statistics_{timestamp}.jsonl"

        with output_file.open("w", encoding="utf-8") as file:
            for record in statistics:
                file.write(
                    json.dumps(record, ensure_ascii=False) + "\n"
                )

        print(f"Statistics collected: {len(statistics)}")
        print(f"Saved to {output_file}")

        print("Fetching comments from popular videos...")

        # Select up to 20 videos with the highest view counts
        popular_videos = sorted(
            statistics,
            key=lambda video: video.get("views", 0),
            reverse=True
        )[:20]

        popular_video_ids = [
            video["video_id"] for video in popular_videos
        ]

        comments, video_status = get_video_comments(
            popular_video_ids,
            max_comments=100
        )

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        comments_file = OUTPUT_DIR / f"comments_{timestamp}.jsonl"

        with comments_file.open("w", encoding="utf-8") as file:
            for comment in comments:
                file.write(
                    json.dumps(comment, ensure_ascii=False) + "\n"
                )

        print(f"Videos selected for comments: {len(popular_video_ids)}")
        print(f"Comments collected: {len(comments)}")
        status_file = OUTPUT_DIR / f"comment_status_{timestamp}.jsonl"

        with status_file.open("w", encoding="utf-8") as file:
            for record in video_status:
                file.write(
                    json.dumps(record, ensure_ascii=False) + "\n"
                )

        from collections import Counter

        status_summary = Counter(
            item["status"] for item in video_status
        )

        print("Comment status summary:", dict(status_summary))
        print(f"Saved status to {status_file}")

    except requests.RequestException as error:
        print(f"Statistics request failed: {error}")


if __name__ == "__main__":
    main()
