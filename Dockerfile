FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY collectors ./collectors
COPY monitoring ./monitoring
COPY scheduler ./scheduler

RUN mkdir -p data logs reports

CMD ["python", "-m", "scheduler.jobs"]
