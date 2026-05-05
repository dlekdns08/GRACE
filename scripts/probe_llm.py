"""Standalone diagnostic: ping the LLM, parse, measure latency, check overlap.

Run this once after starting LM Studio (or with ``--mock`` for an
offline smoke test) to verify the prompt/parser/cache/async stack works
end-to-end before kicking off training.

Usage::

    python scripts/probe_llm.py \\
        --base-url http://localhost:1234/v1 \\
        --model qwen3.6-35b-a3b --n 10

    python scripts/probe_llm.py --mock --n 50

What it does
------------

1. Builds an :class:`LLMClient` (LM Studio or :class:`MockLLMClient`).
2. Drives a fresh :class:`DummyOvercookedEnv` for a few random steps to
   produce realistic state-text snapshots.
3. Builds a :class:`LLMRequest` per snapshot via :func:`build_request`
   (prompt v2 by default).
4. Calls each request synchronously, parses the response with
   :func:`parse_subgoal_with_validation`, and accumulates parse / validity
   stats and a :class:`LatencyStats` summary.
5. Repeats step 4 over an :class:`AsyncLLMClient` to measure
   foreground/background overlap with :func:`measure_async_overlap`.
6. Writes a JSON summary to ``runs/probe_<ts>/llm_probe.json``.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

# Make ``src.*`` importable when this script is invoked directly.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import numpy as np  # noqa: E402

from src.envs.dummy_env import DummyOvercookedEnv  # noqa: E402
from src.llm.async_client import AsyncLLMClient  # noqa: E402
from src.llm.client import LLMClient, LLMRequest, LMStudioClient  # noqa: E402
from src.llm.latency import LatencyStats, measure_async_overlap, summarize  # noqa: E402
from src.llm.mock import MockLLMClient  # noqa: E402
from src.llm.parsers import parse_subgoal_with_validation  # noqa: E402
from src.llm.prompts import PROMPT_VERSION, SUBGOAL_ENUM, build_request  # noqa: E402


def _build_mock_responses() -> list[str]:
    """Return a deterministic cycle of plausible (mostly valid) responses.

    Mixes valid JSON, fenced JSON, and a malformed fragment so the parse
    + validity stats look realistic in a smoke run.
    """
    return [
        '{"agent_0": "go_to_onion", "agent_1": "go_to_onion"}',
        '{"agent_0": "deliver_onion_to_pot", "agent_1": "pickup_dish"}',
        '```json\n{"agent_0": "idle", "agent_1": "pickup_soup"}\n```',
        '{"agent_0": "pickup_onion", "agent_1": "wait_for_cook"}',
        '{"agent_0": "fetch onion", "agent_1": "go_to_onion"}',  # invalid
    ]


def _generate_requests(n: int) -> list[LLMRequest]:
    """Drive the dummy env for a few random actions to produce N prompts.

    Uses a fixed seed so the probe output is reproducible. Resets the env
    every few steps so we hit a variety of states (empty pot, filling
    pot, ready pot, etc.).
    """
    env = DummyOvercookedEnv()
    rng = np.random.default_rng(0)
    obs = env.reset(seed=0)
    requests: list[LLMRequest] = []
    agent_ids = env.agent_ids

    while len(requests) < n:
        # Use the rendered state-text directly (already deterministic).
        requests.append(
            build_request(
                state_text=obs.text,
                agent_ids=agent_ids,
                temperature=0.0,
                seed=len(requests),
            )
        )
        if len(requests) >= n:
            break

        actions = {aid: int(rng.integers(0, env.action_space_size)) for aid in agent_ids}
        step = env.step(actions)
        obs = step.obs
        if step.terminated or step.truncated:
            obs = env.reset(seed=len(requests))

    return requests


def _build_client(args: argparse.Namespace) -> LLMClient:
    if args.mock:
        return MockLLMClient(_build_mock_responses())
    return LMStudioClient(
        base_url=args.base_url,
        model=args.model,
        timeout=args.timeout,
    )


def _stats_to_dict(stats: LatencyStats) -> dict[str, float | int]:
    return asdict(stats)


def _run_sync_pass(
    client: LLMClient,
    requests: list[LLMRequest],
    agent_ids: list[str],
) -> dict[str, object]:
    """Call requests sequentially and gather parse + latency stats."""
    responses = []
    parse_ok = 0
    valid_ok = 0
    completion_lens: list[int] = []

    for req in requests:
        resp = client.call(req)
        responses.append(resp)
        completion_lens.append(len(resp.text))

        parsed = parse_subgoal_with_validation(
            resp.text,
            agent_ids=agent_ids,
            valid_subgoals=SUBGOAL_ENUM,
        )
        if parsed is not None:
            parse_ok += 1
            valid_ok += 1  # parse_subgoal_with_validation already gates validity
        else:
            # Distinguish parse-fail from validity-fail when possible.
            from src.llm.parsers import parse_subgoal

            if parse_subgoal(resp.text) is not None:
                parse_ok += 1

    n = len(requests)
    summary = summarize(responses)
    avg_completion_len = sum(completion_lens) / len(completion_lens) if completion_lens else 0.0
    return {
        "n": n,
        "parse_success_rate": parse_ok / n if n else 0.0,
        "validity_rate": valid_ok / n if n else 0.0,
        "avg_completion_len": avg_completion_len,
        "latency": _stats_to_dict(summary),
    }


def _run_async_pass(
    client: LLMClient,
    requests: list[LLMRequest],
    work_per_step_ms: float,
) -> dict[str, float]:
    async_client = AsyncLLMClient(client, max_workers=4)
    try:
        return measure_async_overlap(
            async_client,
            requests,
            work_per_step_ms=work_per_step_ms,
        )
    finally:
        async_client.shutdown(wait=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe the LLM stack end-to-end.")
    parser.add_argument(
        "--base-url",
        default="http://localhost:1234/v1",
        help="LM Studio base URL (ignored when --mock is set).",
    )
    parser.add_argument(
        "--model",
        default="qwen3.6-35b-a3b",
        help="Model name (ignored when --mock is set).",
    )
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--n", type=int, default=10, help="Number of probe requests.")
    parser.add_argument(
        "--work-per-step-ms",
        type=float,
        default=50.0,
        help="Simulated foreground work per step for async overlap measurement.",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use MockLLMClient (offline smoke).",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help="Override output directory; defaults to runs/probe_<ts>/.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.n <= 0:
        print(f"ERROR: --n must be positive (got {args.n})", file=sys.stderr)
        return 2

    ts = time.strftime("%Y%m%d-%H%M%S")
    out_dir = Path(args.out_dir) if args.out_dir else Path("runs") / f"probe_{ts}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "llm_probe.json"

    print(
        f"[probe] mode={'mock' if args.mock else 'lmstudio'} "
        f"n={args.n} prompt_version={PROMPT_VERSION}"
    )
    if not args.mock:
        print(f"[probe] base_url={args.base_url} model={args.model}")

    requests = _generate_requests(args.n)
    agent_ids = ["agent_0", "agent_1"]

    sync_client = _build_client(args)
    print(f"[probe] running sync pass over {len(requests)} requests ...")
    try:
        sync_result = _run_sync_pass(sync_client, requests, agent_ids)
    except Exception as exc:  # noqa: BLE001 - CLI smoke test
        print(f"ERROR during sync pass: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    async_client_inner = _build_client(args)
    print(f"[probe] running async-overlap pass (work_per_step_ms={args.work_per_step_ms}) ...")
    try:
        async_result = _run_async_pass(
            async_client_inner, requests, work_per_step_ms=args.work_per_step_ms
        )
    except Exception as exc:  # noqa: BLE001 - CLI smoke test
        print(f"ERROR during async pass: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    summary: dict[str, object] = {
        "prompt_version": PROMPT_VERSION,
        "mode": "mock" if args.mock else "lmstudio",
        "n": args.n,
        "work_per_step_ms": args.work_per_step_ms,
        "model": None if args.mock else args.model,
        "base_url": None if args.mock else args.base_url,
        "sync": sync_result,
        "async": async_result,
        "ts": ts,
    }
    out_path.write_text(json.dumps(summary, indent=2))

    sync_lat = sync_result["latency"]
    print("--- summary ---")
    print(f"  prompt_version       : {PROMPT_VERSION}")
    print(f"  parse_success_rate   : {sync_result['parse_success_rate']:.3f}")
    print(f"  validity_rate        : {sync_result['validity_rate']:.3f}")
    print(f"  avg_completion_len   : {sync_result['avg_completion_len']:.1f}")
    print(f"  sync mean_ms / p95   : {sync_lat['mean_ms']:.2f} / {sync_lat['p95_ms']:.2f}")
    print(f"  async wall_time_ms   : {async_result['wall_time_ms']:.2f}")
    print(f"  async lost_overlap   : {async_result['lost_overlap_frac']:.3f}")
    print(f"[probe] wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
