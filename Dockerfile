# syntax=docker/dockerfile:1.6

FROM python:3.11-slim AS base

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
        git build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Cache deps
COPY pyproject.toml ./
RUN uv venv .venv && \
    . .venv/bin/activate && \
    uv pip install -e ".[dev]"

# Copy source
COPY . .

# Default: run tests
ENV PYTHONPATH=/app
CMD [".venv/bin/pytest", "-v"]
