# GRACE

**G**eneralized **R**outing **A**gent for **C**ooperative **E**nvironments.

LLM Meta-Policy for Overcooked: learning *when* to call the LLM high-level planner so that overall LLM calls are reduced without losing task performance.

## Status

Scaffolding phase. See [DESIGN.md](DESIGN.md) for the architecture and Phases 0-7 in the plan.

## Quick start

```bash
# 1. Set up Python environment
uv sync
# or: pip install -e ".[dev,overcooked]"

# 2. Run tests
pytest

# 3. (Optional) Start LM Studio with a Qwen model on port 1234

# 4. Smoke-check the LLM client (requires LM Studio)
python scripts/llm_hello.py

# 5. Train PPO baseline (mock LLM)
python scripts/train.py policy=ppo meta=fixed_k100 seed=0
```

## Layout

```
src/        Reusable library (envs, llm, policies, training, eval)
configs/    Hydra configs for experiments
scripts/    Entry points (train.py, eval.py, sweep.py, plot_results.py)
tests/      Unit + smoke tests
unity_env/  Unity ML-Agents project (C#)
docs/       Prompts (versioned) and experiment journal
```

## Phases

- [x] Phase 0 — Bootstrap
- [x] Phase 1 — LLM client (LM Studio + cache + async + mock)
- [x] Phase 2 — Python env wrapper + state→text serializer
- [x] Phase 3 — PPO baseline
- [x] Phase 4 — LLM-augmented policy + heuristic meta-policy
- [x] Phase 5 — Learned meta-policy (GRPO)
- [x] Phase 6 — Unity ML-Agents integration (scaffolding only — Unity Editor required)
- [x] Phase 7 — Experiment + ablation scripts

See [DESIGN.md](DESIGN.md) for goals, hypotheses, and per-phase deliverables.
