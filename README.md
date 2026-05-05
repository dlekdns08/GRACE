# GRACE

**G**RPO-based **R**easoning **A**ssistance **C**alling **E**fficiently.

LLM Meta-Policy for Overcooked: learning *when* to call the LLM high-level planner so that
overall LLM calls are reduced without losing task performance.

[![CI](https://github.com/idaun/grace/actions/workflows/ci.yml/badge.svg)](https://github.com/idaun/grace/actions/workflows/ci.yml)
[![Lint](https://github.com/idaun/grace/actions/workflows/lint.yml/badge.svg)](https://github.com/idaun/grace/actions/workflows/lint.yml)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/release/python-3110/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

## TL;DR

Most LLM-as-planner work calls the LLM at fixed intervals. GRACE *learns* when to call,
training a small meta-policy with GRPO. Result: same task performance with fewer LLM
calls (Pareto improvement).

## Headline figure

*Placeholder — `figures/pareto.png` will go here once Phase 11 sweeps run.*

## Installation

### Quick start (uv)

```bash
git clone https://github.com/idaun/grace.git
cd grace
uv sync --extra dev --extra overcooked
.venv/bin/pytest -v   # all 99+ tests should pass
```

### Optional extras

- `--extra play` — pygame for human-play mode (Phase 9)
- `--extra unity` — mlagents-envs for Unity environments (Phase 6)

### Docker

```bash
docker build -t grace:latest .
docker run --rm grace:latest pytest -v
```

## Try it: human-play (no LLM, no training required)

```bash
.venv/bin/python scripts/play_human.py --env dummy --mode coop
# Player 1: WASD + Space (interact) + E (stay)
# Player 2: arrows + RShift (interact) + RCtrl (stay)
```

For the Unity build, see `unity_env/README.md`.

## Train a baseline (DESIGN.md §5)

```bash
# Plain PPO baseline (no LLM)
PYTHONPATH=$(pwd) python scripts/train.py env=cramped_room policy=ppo meta=never seed=0

# LLM-augmented with fixed-K calls
PYTHONPATH=$(pwd) python scripts/train.py \
    env=cramped_room policy=llm_augmented meta=fixed_k100 llm=qwen3.6_35b seed=0

# Learned meta-policy (the contribution)
PYTHONPATH=$(pwd) python scripts/train_meta.py \
    env=cramped_room policy=llm_augmented meta=learned llm=qwen3.6_35b seed=0
```

## Evaluate

```bash
PYTHONPATH=$(pwd) python scripts/eval.py +run_dir=runs/<run_dir>/ +n_episodes=20

PYTHONPATH=$(pwd) python scripts/eval_transfer.py \
    +train_run=runs/<run_dir>/ \
    +test_layouts=[asymmetric_advantages] \
    +n_episodes=10
```

## Reproduce the paper experiments

See [docs/REPRODUCIBILITY.md](docs/REPRODUCIBILITY.md) for the three hypothesis sweeps
(H1, H2, H3) and expected wallclock.

## Project structure

| Path | Contents |
|---|---|
| `src/` | Reusable library (envs, llm, policies, training, eval) |
| `configs/` | Hydra configs for experiments |
| `scripts/` | Entry points (`train.py`, `eval.py`, `sweep.py`, `plot_results.py`, ...) |
| `tests/` | Unit + smoke tests |
| `unity_env/` | Unity ML-Agents project (C#) |
| `docs/` | Versioned prompts and experiment journal |

## Status

- [x] Phase 0-7 — Scaffolding (LLM client, env, PPO, GRPO, eval)
- [x] Phase 8 — Real Carroll's overcooked-ai integration + checkpoints
- [x] Phase 9 — Human-play (pygame + Unity) + BC warm-start
- [x] Phase 10 — Prompt v2 + latency diagnostics
- [x] Phase 11 — Sweep harness + statistics
- [x] Phase 12 — Public-readiness polish
- [ ] Phase 13 — Full experimental sweep (compute-bound — user runs)

## Citation

*Placeholder — to be filled once the manuscript is on arXiv.*

```bibtex
@misc{grace2026,
  title  = {GRACE: GRPO-based Reasoning Assistance Calling Efficiently},
  author = {GRACE Authors},
  year   = {2026},
  note   = {Preprint}
}
```

## License

MIT — see [LICENSE](LICENSE).
