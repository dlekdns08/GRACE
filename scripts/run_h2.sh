#!/usr/bin/env bash
# DESIGN H2: zero-shot transfer to held-out layouts.
#
# Iterates over every "learned_<train_layout>_*" run directory produced
# by ``run_h1.sh`` and evaluates each on the test layouts. Outputs are
# written next to each run as ``transfer_results.parquet``.
#
#     TEST_LAYOUTS='[asymmetric_advantages]' N_EPISODES=10 \
#         bash scripts/run_h2.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

TEST_LAYOUTS=${TEST_LAYOUTS:-[asymmetric_advantages]}
N_EPISODES=${N_EPISODES:-10}
RUN_GLOB=${RUN_GLOB:-runs/learned_cramped_room_*/}

shopt -s nullglob
matched=0
for run_dir in $RUN_GLOB; do
    if [ ! -d "$run_dir" ]; then
        continue
    fi
    if [ ! -f "$run_dir/policy.pt" ]; then
        echo "Skipping $run_dir (no policy.pt)" 1>&2
        continue
    fi
    matched=$((matched + 1))
    echo "[$matched] Evaluating transfer for $run_dir"
    PYTHONPATH="$REPO_ROOT" python scripts/eval_transfer.py \
        +train_run="$run_dir" \
        +test_layouts="$TEST_LAYOUTS" \
        +n_episodes="$N_EPISODES"
done

if [ "$matched" -eq 0 ]; then
    echo "No run dirs matched $RUN_GLOB; have you run run_h1.sh first?" 1>&2
    exit 1
fi
echo "Done: evaluated $matched run(s)."
