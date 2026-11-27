import logging
import os

import requests
from dotenv import load_dotenv


load_dotenv()

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org"


def send_telegram_message(message):
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        logger.warning(
            "Telegram alert skipped: TELEGRAM_BOT_TOKEN or "
            "TELEGRAM_CHAT_ID is not configured."
        )
        return False

    url = f"{TELEGRAM_API_BASE}/bot{bot_token}/sendMessage"

    try:
        response = requests.post(
            url,
            json={
                "chat_id": chat_id,
                "text": message,
                "disable_web_page_preview": True,
            },
            timeout=15,
        )

        response.raise_for_status()
        result = response.json()

        if not result.get("ok"):
            logger.error("Telegram API returned an unsuccessful response.")
            return False

        logger.info("Telegram alert sent successfully.")
        return True

    except requests.RequestException as exc:
        logger.error("Unable to send Telegram alert: %s", exc)
        return False
    except ValueError:
        logger.error("Telegram API returned invalid JSON.")
        return False


def notify_news_run(run_record):
    status = run_record.get("status", "unknown")
    new_articles = int(run_record.get("new_articles", 0) or 0)
    saved_articles = int(run_record.get("saved_articles", 0) or 0)
    requests_total = int(run_record.get("requests_total", 0) or 0)
    requests_failed = int(run_record.get("requests_failed", 0) or 0)
    duration = run_record.get("duration_seconds", "N/A")
    coverage = run_record.get("coverage_percent")

    if status != "success" or requests_failed > 0:
        message = (
            "🚨 THAI PBS NEWS COLLECTOR ALERT\n\n"
            f"Status: {status}\n"
            f"New articles detected: {new_articles}\n"
            f"Articles saved: {saved_articles}\n"
            f"Requests: {requests_total}\n"
            f"Failed requests: {requests_failed}\n"
            f"Duration: {duration} seconds\n"
            f"Error: {run_record.get('error') or 'Not specified'}"
        )
        return send_telegram_message(message)
    if saved_articles > 0:
        coverage_text = (
            f"{coverage}%"
            if isinstance(coverage, (int, float))
            else "Not available"
        )

        message = (
            "📰 NEW THAI PBS ARTICLES COLLECTED\n\n"
            f"New articles detected: {new_articles}\n"
            f"Articles saved: {saved_articles}\n"
            f"Discovered listing URLs: "
            f"{run_record.get('discovered_links', 'N/A')}\n"
            f"Listing coverage: {coverage_text}\n"
            f"Request success rate: "
            f"{run_record.get('request_success_rate', 'N/A')}%\n"
            f"Duration: {duration} seconds"
        )
        return send_telegram_message(message)
    return None
