# Contributing to GRACE

Thanks for your interest. GRACE is a research codebase, but we try to keep it tidy.

## Development setup

```bash
git clone https://github.com/idaun/grace.git
cd grace
uv sync --extra dev --extra overcooked
.venv/bin/pre-commit install
```

## Code style

- Formatter / linter: [ruff](https://github.com/astral-sh/ruff).
  - `ruff format .` to format, `ruff check .` to lint.
- Line length: 100 (configured in `pyproject.toml`).
- Type hints on all public functions where practical. We don't enforce strict mypy.

## Tests

- `pytest -v` from the repo root.
- Aim for at least one test per new public function.
- Smoke tests live in `tests/`; long / network tests should be marked and skippable.

## Branches

Use short prefixes:

- `feat/*` — new feature
- `fix/*` — bug fix
- `exp/*` — experimental / research branch (may be deleted)
- `docs/*` — documentation only

## Commits

- Imperative mood ("Add X" not "Added X").
- Short subject (≤72 chars), blank line, then body if needed.
- Reference issues with `#123` where applicable.

## Pre-commit

Run hooks once after cloning:

```bash
.venv/bin/pre-commit install
```

Hooks run ruff, trailing-whitespace, end-of-file-fixer, YAML check, and a
1MB large-file guard on every commit.

## Things not to commit

- `runs/`, `wandb/`, `outputs/` — experiment artifacts
- `*.parquet`, `*.pt`, `*.ckpt` — large binary artifacts
- `.env`, `*.key` — secrets
- Anything under `unity_env/Library/`, `unity_env/Build/` — Unity-generated

The `.gitignore` covers all of the above; please don't `-f` past it.

## Filing issues

When reporting a bug, include:

1. Python / OS / GPU info.
2. Exact command + Hydra overrides.
3. Stack trace or unexpected output.
4. Run dir if applicable (`runs/<exp_name>_<seed>_<ts>/config.yaml` is helpful).
