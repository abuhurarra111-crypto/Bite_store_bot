# 🚀 Bite Store Bot — Railway Dockerfile
FROM python:3.12-slim

WORKDIR /app

# System deps (lightweight)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY . .

# Railway Volume mount point (DB_PATH=/var/data/shop.db)
RUN mkdir -p /var/data

# Bot runs in polling mode (no web server)
CMD ["python", "bot.py"]
