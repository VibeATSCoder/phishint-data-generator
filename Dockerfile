# ── Backend: FastAPI phishing data generator ──────────────────────────────────
FROM python:3.11-slim

# System deps for lxml, Pillow, stegano, plus util-linux (for `runuser` in entrypoint)
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential \
      libxml2-dev \
      libxslt-dev \
      libjpeg-dev \
      libpng-dev \
      zlib1g-dev \
      util-linux \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Chromium + system deps for Playwright (used for per-technique screenshots).
# This adds ~350 MB to the image; needed for the bulk pipeline + /generate screenshots.
RUN playwright install --with-deps chromium

COPY app/ ./app/

# Job storage directory (bind-mounted to ./data on host via docker-compose.yml).
RUN mkdir -p /data && chown -R 1000:1000 /data

# Non-root user for safety. The entrypoint runs as root just long enough to
# chown the bind-mounted /data, then drops to this user via `runuser`.
RUN useradd -m -u 1000 phishgen && chown -R phishgen /app
RUN mkdir -p /home/phishgen/.cache && \
    cp -r /root/.cache/ms-playwright /home/phishgen/.cache/ms-playwright && \
    chown -R phishgen:phishgen /home/phishgen/.cache
ENV PLAYWRIGHT_BROWSERS_PATH=/home/phishgen/.cache/ms-playwright

# Entrypoint fixes /data permissions then execs the CMD as the phishgen user.
# `sed` strips CRLF in case the file was checked out on Windows.
COPY entrypoint.sh /entrypoint.sh
RUN sed -i 's/\r$//' /entrypoint.sh && chmod +x /entrypoint.sh

EXPOSE 8009

ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8009"]
