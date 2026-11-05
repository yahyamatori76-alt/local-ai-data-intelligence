FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        antiword \
        catdoc \
        tesseract-ocr \
        tesseract-ocr-eng \
        tesseract-ocr-ind \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY dashboard ./dashboard
COPY migrations ./migrations
COPY tests ./tests

EXPOSE 8000 8501
