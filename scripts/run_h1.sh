#!/usr/bin/env bash
# DESIGN H1: meta-policy comparison.
#
# Trains every meta-policy variant on the same env / LLM / step budget,
# across a small seed sweep, and writes a manifest of run dirs to
# ``runs/h1_manifest.json``. Knobs are exposed via env vars so the
# script can be re-used for smoke tests without editing it::
#
#     SEEDS=0,1,2 ENV=cramped_room LLM=qwen3.6_35b STEPS=1000000 \
#         bash scripts/run_h1.sh
#
# By default it follows the DESIGN ablation: 3 seeds x 5 metas = 15 runs.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

SEEDS=${SEEDS:-0,1,2}
ENV=${ENV:-cramped_room}
LLM=${LLM:-qwen3.6_35b}
STEPS=${STEPS:-1000000}
PARALLEL=${PARALLEL:-1}
MANIFEST=${MANIFEST:-runs/h1_manifest.json}

PYTHONPATH="$REPO_ROOT" python scripts/sweep.py --run \
    --parallel "$PARALLEL" \
    --manifest "$MANIFEST" \
    --retry-failed \
    meta=fixed_k10,fixed_k100,never,entropy,learned \
    seed="$SEEDS" \
    env="$ENV" \
    policy=llm_augmented \
    llm="$LLM" \
    experiment.total_steps="$STEPS"
