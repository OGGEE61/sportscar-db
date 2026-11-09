# Image for one scraper run on the VPS. Built by deploy/scrapers/update.sh; run by run.sh.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# .dockerignore keeps secrets (.env, cookies), databases and local tooling out of the image
COPY . .

# Non-root; the cookies file on the host is owned by this uid (see README.md)
RUN useradd --uid 10001 --no-create-home scraper
USER scraper
