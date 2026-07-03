# Production image for the AI Web-Design Lead Finder.
# Uses uv for fast, reproducible installs and ships Playwright's Chromium.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_SYSTEM_PYTHON=1 \
    PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers

# System deps for Playwright/Chromium.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl ca-certificates \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
    libgbm1 libpango-1.0-0 libcairo2 libasound2 fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Install uv.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Install Python deps first (better layer caching).
COPY pyproject.toml README.md ./
RUN uv pip install --system -e .

# Install the Chromium browser used by the crawler.
RUN python -m playwright install chromium

COPY . .

EXPOSE 8000 8501

# Default: run DB migrations then serve the API.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
