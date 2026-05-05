# syntax=docker/dockerfile:1.6

FROM python:3.11-slim AS base

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
        git build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Cache deps. Editable installs need README.md (referenced by pyproject.toml)
# and a stub `src/` so hatchling can resolve the package layout. The full
# tree is copied in the next step and overwrites these stubs.
COPY pyproject.toml README.md ./
RUN mkdir -p src && touch src/__init__.py
RUN uv venv .venv && \
    . .venv/bin/activate && \
    uv pip install -e ".[dev]"

# Copy source
COPY . .

# Default: run tests
ENV PYTHONPATH=/app
CMD [".venv/bin/pytest", "-v"]
