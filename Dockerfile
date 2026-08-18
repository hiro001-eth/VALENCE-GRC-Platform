# Multi-stage production Dockerfile for VALENCE GRC Dashboard Backend
FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir ".[postgres,redis]"

FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for WeasyPrint (PDF generation)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libharfbuzz0b \
    libpangoft2-1.0-0 \
    libffi-dev \
    libjpeg-dev \
    libopenjp2-7-dev \
    shared-mime-info \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY pyproject.toml README.md alembic.ini ./
COPY alembic ./alembic
COPY src ./src
COPY rules ./rules
COPY frontend ./frontend
RUN pip install --no-cache-dir --no-deps -e .

# SECURITY: Run as non-root user
RUN groupadd -r valence && useradd -r -g valence -d /app -s /sbin/nologin valence \
    && mkdir -p /app/output /app/data \
    && chown -R valence:valence /app

EXPOSE 8000

ENV PYTHONUNBUFFERED=1

USER valence

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["valence-api"]
