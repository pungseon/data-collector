# Data Collector

A Python-based data collection system that gathers public news articles from Thai PBS and video data from YouTube Data API v3. The project focuses on reliable data collection, hybrid discovery, deduplication, data quality validation, and operational monitoring.

## 1. Project Overview

This project implements two independent data collection pipelines:

- **News Collector:** Discovers and collects public news articles from Thai PBS using listing-page and sitemap discovery.
- **YouTube Collector:** Collects video information using the official YouTube Data API v3.

The system stores collected data in JSONL files and provides monitoring tools to evaluate collection performance, data quality, and freshness.

The main design goal is to build a lightweight, file-based data collection system that can run continuously with scheduled jobs and measurable KPIs.

## 2. Key Features

### News Collection
- Collects public news articles from Thai PBS.
- Uses a hybrid discovery strategy combining:
  - News listing page
  - XML sitemap
- Normalizes article URLs using article IDs to handle different URL formats.
- Tracks discovery sources for collected articles.
- Avoids revisiting previously collected article pages.
- Handles HTTP errors and retries temporary failures.
- Applies request throttling to respect the source website.

### YouTube Collection
- Uses the official YouTube Data API v3.
- Searches across five custom keywords:
  - Artificial Intelligence
  - Data Engineering
  - Python Programming
  - Machine Learning
  - Technology Thailand
- Supports pagination using `nextPageToken`.
- Retrieves video statistics through the API.

### Data Quality & Monitoring
- JSONL-based storage.
- Duplicate detection.
- Required-field completeness checks.
- Malformed JSONL record detection.
- News freshness analysis.
- Request success-rate monitoring.
- Collection duration tracking.
- KPI analysis and reporting.
- Optional Telegram notifications.

## 3. System Architecture

```text
                  DATA SOURCES
                       |
          +------------+------------+
          |                         |
     Thai PBS                  YouTube API
          |                         |
   +------+-------+          +------+-------+
   |              |          |              |
Listing Page   XML Sitemap  Keyword Search  Video API
   |              |          |              |
   +------+-------+          +------+-------+
          |                         |
    Hybrid Discovery          Video Collection
          |                         |
    Article Extraction       Statistics Collection
          |                         |
          +------------+------------+
                       |
                 JSONL STORAGE
                       |
          +------------+------------+
          |            |            |
      Deduplication  Data Quality  Run Logs
          |            |            |
          +------------+------------+
                       |
                KPI Monitoring
                       |
              Reports / Telegram
```

## 4. Project Structure

```text
data-collector/
│
├── collectors/
│   ├── news_collector.py
│   └── youtube_collector.py
│
├── monitoring/
│   ├── audit_freshness.py
│   ├── compare_discovery.py
│   ├── data_quality.py
│   ├── discovery_history.py
│   ├── kpi_analyzer.py
│   └── telegram_alert.py
│
├── scheduler/
│   └── jobs.py
│
├── reports/
│   └── kpi_report.json
│
├── data/                 # Generated collection data
├── logs/                 # Runtime logs
│
├── .env.example
├── .gitignore
└── requirements.txt
```

## 5. Technology Stack

| Component | Technology |
|---|---|
| Programming Language | Python |
| HTTP Requests | Requests |
| HTML Parsing | BeautifulSoup |
| XML Parsing | lxml |
| YouTube Data | YouTube Data API v3 |
| Scheduling | APScheduler |
| Data Storage | JSONL |
| Data Analysis | Pandas |
| Notifications | Telegram Bot API |
| Environment Variables | python-dotenv |

## 6. Installation

### Prerequisites
- Python 3.10 or later
- YouTube Data API v3 API key
- Git

### Clone the repository

```bash
git clone https://github.com/pungseon/data-collector.git
cd data-collector
```

### Create a virtual environment

Windows PowerShell:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### Install dependencies

```bash
pip install -r requirements.txt
```

## 7. Configuration

Create a `.env` file in the project root based on `.env.example`.

```env
YOUTUBE_API_KEY=your_api_key_here
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
```

Replace the placeholder values with your own credentials.

**Security:** Never commit `.env` or API credentials to GitHub.

## 8. Running the Project

Start the scheduler from the project root:

```bash
python -m scheduler.jobs
```

The scheduler runs both collectors once at startup and then follows the configured intervals.

| Collector | Frequency |
|---|---|
| News | Every 5 minutes |
| YouTube | Every 1 hour |

The scheduler uses the `Asia/Bangkok` timezone.

Press `Ctrl + C` to stop the scheduler.

## 9. Data Storage

The project uses JSON Lines (JSONL) for file-based storage.

Each record is stored as an independent JSON object on a separate line.

The collection data includes timestamps such as:

- `published_at`: Original publication time.
- `collected_at`: Time when the record was collected.

All timestamps are represented in ISO 8601 format with timezone information.

Runtime data and logs are stored locally and excluded from Git version control.

## 10. Monitoring & KPIs

The monitoring components evaluate the collection pipeline using measurable indicators.

| KPI | Target |
|---|---:|
| News freshness | At least 90% within 15 minutes |
| News freshness p95 | Within 30 minutes |
| YouTube freshness | Within 60 minutes |
| News coverage | At least 95% |
| Request success rate | At least 98% |
| Field completeness | At least 99% |
| Duplicate records | 0 |
| Collection round duration | Less than the configured interval |
| Request rate | No more than 20 requests/minute/domain |

The KPI analyzer produces a report to help identify bottlenecks and areas for improvement.

## 11. Initial Test Results

An initial test was conducted for approximately one hour.

| Metric | Observed Result |
|---|---:|
| Scheduler runs | 57 |
| Scheduler success rate | 100% |
| Average scheduler duration | 1.63 seconds |
| News records | 51 |
| News field completeness | 100% |
| Malformed records | 0 |
| Duplicate records | 0 |
| News request success rate | 100% |
| News coverage | 100% across 46 evaluated rounds |
| News freshness within 15 minutes | 0% |

### Key Findings

The initial test demonstrated that the collection process, deduplication, and data validation worked reliably during the observed period.

However, the news freshness KPI did not meet the target. The measured median publication-to-collection latency was approximately 51 minutes, with a p95 of approximately 213 minutes.

One important limitation is that the initial collection included historical articles. Therefore, the first observation time does not necessarily represent the actual time when an article first became available on the source listing.

The system requires a longer observation period to establish a more representative freshness baseline.

**Note:** This was an initial test of approximately one hour, not a completed 24-hour continuous-run evaluation.

## 12. Design Decisions

### Why use JSONL instead of a database?

JSONL provides simple append-only storage, easy inspection, and compatibility with Python data-processing tools. It also avoids the operational overhead of maintaining a database for this assignment.

### Why use hybrid discovery for news?

A listing page and sitemap expose different sets of article URLs. Combining both sources improves discovery coverage and reduces dependence on a single discovery mechanism.

### Why normalize article URLs?

The same article may appear under different hostnames or URL formats. Normalizing URLs using article IDs helps identify the same article and avoid duplicate collection.

### Why use a five-minute news interval?

News can change frequently, so a short polling interval helps reduce the time between discovery opportunities while remaining within the configured per-domain request limit.

### Why use a one-hour YouTube interval?

YouTube collection uses API quota. A one-hour interval provides periodic updates while limiting the frequency of API calls.

The current keyword and pagination configuration should be reviewed against the project's available daily API quota.

### How are failures handled?

The collectors use retry handling for temporary HTTP failures, while the scheduler records execution status, duration, and error information for monitoring.

## 13. Limitations & Future Improvements

The project can be improved in several areas:

- Complete and validate YouTube comment collection, including handling videos with disabled comments.
- Conduct a full 24-hour continuous-run evaluation.
- Improve news freshness measurement using persistent per-source discovery timestamps.
- Optimize YouTube API quota consumption through keyword rotation and quota-aware scheduling.
- Add automated tests for pagination, retries, parsing, and deduplication.
- Add Docker and Docker Compose support for reproducible deployment.
- Improve monitoring with historical KPI trends and automated alerts.

## 14.Docker Deployment

The project supports Docker Compose for automated data collection.

### Requirements
- Docker Desktop
- Docker Compose
- YouTube Data API Key

### Configuration

Create a `.env` file in the project root and configure the required environment variables. Refer to `.env.example` for the required variable names.

### Build and Run

```bash
docker compose build
docker compose up -d
```

### Monitor Logs

```bash
docker compose logs -f
```

### Stop the Collector

```bash
docker compose down
```

### Persistent Storage

Docker Compose mounts the following directories to the host machine:

- `./data` — collected JSONL data
- `./logs` — execution and monitoring logs
- `./reports` — KPI reports

## YouTube Comments Collection

The YouTube collector supports:
- Search pagination using `nextPageToken`
- Video statistics collection
- Top-level comment collection for selected popular videos
- Handling videos with disabled comments
- Comment collection status tracking

## Scheduling

The scheduler runs:
- News collection every 5 minutes
- YouTube collection every 1 hour

All schedules use the Asia/Bangkok timezone.

## 15. Repository

GitHub: https://github.com/pungseon/data-collector

---

**Author:** Pungseon  
**Project:** Mini Data Collector  
**Focus:** Data Collection · Data Engineering · Monitoring · Data Quality
