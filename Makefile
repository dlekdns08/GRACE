.PHONY: help install test lint format clean dev

PYTHON := .venv/bin/python
PYTEST := .venv/bin/pytest

help:
	@echo "Common targets:"
	@echo "  install    Install dev + overcooked + play extras via uv"
	@echo "  test       Run pytest"
	@echo "  lint       Run ruff check"
	@echo "  format     Run ruff format"
	@echo "  clean      Remove build artifacts and caches"
	@echo "  dev        Install pre-commit hooks (after install)"

install:
	uv venv .venv
	uv pip install -e ".[dev,overcooked,play]"

test:
	PYTHONPATH=$(PWD) $(PYTEST) -v

lint:
	$(PYTHON) -m ruff check .

format:
	$(PYTHON) -m ruff format .

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache __pycache__ */__pycache__ */*/__pycache__
	rm -rf build dist *.egg-info

dev: install
	$(PYTHON) -m pre_commit install
