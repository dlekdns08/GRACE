# Reproducibility

This guide covers reproducing the three hypotheses (H1, H2, H3) from
[DESIGN.md](../DESIGN.md) §5.

## Prerequisites

- Python 3.11.
- ~50 GB disk for runs and checkpoints.
- LM Studio running with a Qwen3.6 model on `http://localhost:1234` (~25 GB GPU/RAM).
- Apple Silicon Mac Studio (recommended) or NVIDIA GPU.
- Wallclock time: ~30 hours for H1, +6 h for H2, +18 h for H3.

## Setup

```bash
git clone https://github.com/idaun/grace.git
cd grace
uv sync --extra dev --extra overcooked

# Start LM Studio, load a Qwen3.6 (~35B) model, then enable the local server
# on port 1234.  The mock client is used by tests; real runs need LM Studio.
.venv/bin/python scripts/llm_hello.py   # smoke-checks the server
```

## H1 — Meta-policy comparison (cramped_room)

Compare {`never`, `fixed_k50`, `fixed_k100`, `entropy`, `learned`} on `cramped_room`
across 3 seeds.

```bash
bash scripts/run_h1.sh
python scripts/plot_results.py "runs/*_cramped_room_*" --out figures/ --statistics
```

**Expected:** a Pareto plot (`figures/pareto.png`) where the learned meta-policy
dominates fixed-K and entropy baselines: same task return at fewer LLM calls per
episode. Statistical significance (paired bootstrap) reported alongside.

## H2 — Layout transfer

Train on `cramped_room`, evaluate zero-shot on `asymmetric_advantages` and
`coordination_ring`.

```bash
bash scripts/run_h2.sh
python scripts/plot_results.py "runs/*_cramped_room_*" --out figures/
```

**Expected:** the learned meta-policy retains its Pareto advantage on held-out
layouts, demonstrating that "when to call" generalises beyond a single layout.

## H3 — Model ablation

Hold the meta-policy fixed; vary the LLM backbone (Qwen3.6 8B / 14B / 35B).

```bash
bash scripts/run_h3.sh
python scripts/plot_results.py "runs/learned_*" --out figures/
```

**Expected:** stronger LLMs receive fewer (but more useful) calls; weaker LLMs are
called more but plateau lower — the meta-policy adapts its call frequency to
backbone quality.

## Logging

Every run writes to `runs/<exp_name>_<seed>_<ts>/`:

| File | Contents |
|---|---|
| `config.yaml` | Resolved Hydra config (full provenance). |
| `policy.pt`, `policy_step{N}.pt` | Final + periodic checkpoints. |
| `transitions.parquet` | Per-step transitions (obs / action / reward / done). |
| `episodes.parquet` | Per-episode aggregates (return, length, n_llm_calls). |
| `llm_calls.parquet` | Per-call latency, tokens, cache hits. |
| `eval_results.parquet` | Post-training eval (Phase 8+). |

W&B integration is controlled by `logging.wandb_mode` in the Hydra config:

- `online` — live dashboards.
- `offline` — sync later with `wandb sync runs/<dir>/wandb`.
- `disabled` — local-only (default).

## Determinism

`src/utils/seeding.py` seeds Python, NumPy, and PyTorch from `seed`.  Note that
LM Studio's `seed` parameter is sometimes ignored by the inference server depending
on the backend; we rely on the prompt cache (`src/llm/cache.py`) to ensure the same
prompt yields the same response across re-runs.

For the strictest reproducibility:

1. Pin LM Studio + model checksum.
2. Keep `runs/<dir>/llm_calls.parquet` from the original run; re-run with
   `llm.cache_path=runs/<dir>/llm_cache.json` to force cache hits.
3. Use the locked `pyproject.toml` and `.python-version`.

## Hardware notes

- The PPO + GRPO trainers run comfortably on a single M2 Pro / A6000.
- LLM inference dominates wallclock; expect ~0.5–1.5 s per call at Qwen3.6-35B
  and ~0.1–0.3 s at 8B on the same hardware.
- Phase 10 (`src/llm/latency.py`) records per-call latency histograms — inspect
  them before launching long sweeps.
