# Production image for AWS ECS Fargate (linux/amd64).
# Build:  docker build --platform=linux/amd64 -t cpi-inventory:latest .
# Run:    docker run --rm -p 8050:8050 --env-file .env cpi-inventory:latest

# ---------- builder ----------
FROM --platform=linux/amd64 python:3.12-slim-bookworm AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --prefix=/install -r requirements.txt

# ---------- runtime ----------
FROM --platform=linux/amd64 python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    CPI_ENV=production \
    CPI_SESSION_COOKIE_SECURE=1 \
    CPI_BEHIND_PROXY=1 \
    CPI_HOST=0.0.0.0 \
    CPI_PORT=8050

# libpq + curl (for HEALTHCHECK). tini = proper PID 1 / signal handling.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        curl \
        tini \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system app && useradd --system --gid app --home /app app

COPY --from=builder /install /usr/local
WORKDIR /app
COPY --chown=app:app . .

USER app
EXPOSE 8050

# ALB/ECS target group should probe /api/v1/health on port 8050.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8050/api/v1/health || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
# Workers/threads tuned for Fargate 1 vCPU / 2 GB. Scale horizontally via ECS desired count.
CMD ["gunicorn", \
     "--bind", "0.0.0.0:8050", \
     "--workers", "2", \
     "--threads", "4", \
     "--worker-class", "gthread", \
     "--timeout", "120", \
     "--graceful-timeout", "30", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "wsgi:application"]
