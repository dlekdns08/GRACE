#!/usr/bin/env bash
# DESIGN H3: model ablation.
#
# Trains the *learned* meta-policy against each LLM backend listed in
# ``configs/llm/`` and across a small seed sweep, holding env / policy
# fixed. The hypothesis: stronger LLMs let the meta-policy reduce call
# frequency without losing performance.
#
#     SEEDS=0,1,2 ENV=cramped_room STEPS=1000000 bash scripts/run_h3.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

SEEDS=${SEEDS:-0,1,2}
ENV=${ENV:-cramped_room}
STEPS=${STEPS:-1000000}
PARALLEL=${PARALLEL:-1}
MANIFEST=${MANIFEST:-runs/h3_manifest.json}

PYTHONPATH="$REPO_ROOT" python scripts/sweep.py --run \
    --parallel "$PARALLEL" \
    --manifest "$MANIFEST" \
    --retry-failed \
    llm=qwen3.6_35b,qwen3_thinking,qwen3_8b \
    meta=learned \
    seed="$SEEDS" \
    env="$ENV" \
    policy=llm_augmented \
    experiment.total_steps="$STEPS"
