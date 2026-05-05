"""Latency measurement and async-overlap diagnostics for LLM clients.

The RL loop budget is dominated by LLM latency. To verify (a) the
distribution of LLM latencies is what we expect and (b) the async client
actually unblocks the foreground (DESIGN section 4.4), this module
provides three small helpers:

* :func:`summarize` -- aggregate stats over a list of :class:`LLMResponse`.
* :func:`measure_sync` -- run requests sequentially via the sync API.
* :func:`measure_async_overlap` -- submit requests via
  :class:`AsyncLLMClient` while doing simulated foreground work and
  measure how often the foreground actually had to block on a future.

No I/O happens at import time; each function takes a client + requests
and returns plain dataclasses / dicts so callers can serialise easily.
"""

from __future__ import annotations

import math
import time
from concurrent.futures import Future
from dataclasses import dataclass

from .async_client import AsyncLLMClient
from .client import LLMClient, LLMRequest, LLMResponse


@dataclass(slots=True)
class LatencyStats:
    """Aggregate latency / throughput stats over a batch of responses."""

    n: int
    mean_ms: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    max_ms: float
    cached_frac: float
    tokens_per_sec_in: float
    tokens_per_sec_out: float


def _percentile(sorted_values: list[float], q: float) -> float:
    """Linear-interp percentile on an already-sorted list.

    Returns ``0.0`` for an empty list so callers do not need to special-case.
    """
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    # q is in [0, 100].
    rank = (q / 100.0) * (len(sorted_values) - 1)
    lo = int(math.floor(rank))
    hi = int(math.ceil(rank))
    if lo == hi:
        return float(sorted_values[lo])
    frac = rank - lo
    return float(sorted_values[lo] * (1.0 - frac) + sorted_values[hi] * frac)


def summarize(records: list[LLMResponse]) -> LatencyStats:
    """Aggregate :class:`LLMResponse` records into a :class:`LatencyStats`.

    An empty input returns an all-zero stats object so callers can chain
    this with empty-batch protection at a single site.
    """
    n = len(records)
    if n == 0:
        return LatencyStats(
            n=0,
            mean_ms=0.0,
            p50_ms=0.0,
            p95_ms=0.0,
            p99_ms=0.0,
            max_ms=0.0,
            cached_frac=0.0,
            tokens_per_sec_in=0.0,
            tokens_per_sec_out=0.0,
        )

    latencies = sorted(float(r.latency_ms) for r in records)
    total_ms = sum(latencies)
    total_s = total_ms / 1000.0
    mean_ms = total_ms / n

    cached_count = sum(1 for r in records if r.cached)
    prompt_tokens = sum(int(r.prompt_tokens) for r in records)
    completion_tokens = sum(int(r.completion_tokens) for r in records)

    if total_s > 0:
        tokens_per_sec_in = prompt_tokens / total_s
        tokens_per_sec_out = completion_tokens / total_s
    else:
        tokens_per_sec_in = 0.0
        tokens_per_sec_out = 0.0

    return LatencyStats(
        n=n,
        mean_ms=mean_ms,
        p50_ms=_percentile(latencies, 50.0),
        p95_ms=_percentile(latencies, 95.0),
        p99_ms=_percentile(latencies, 99.0),
        max_ms=float(latencies[-1]),
        cached_frac=cached_count / n,
        tokens_per_sec_in=tokens_per_sec_in,
        tokens_per_sec_out=tokens_per_sec_out,
    )


def measure_sync(client: LLMClient, requests: list[LLMRequest]) -> LatencyStats:
    """Run ``requests`` sequentially via ``client.call`` and summarise."""
    records: list[LLMResponse] = []
    for req in requests:
        records.append(client.call(req))
    return summarize(records)


def measure_async_overlap(
    async_client: AsyncLLMClient,
    requests: list[LLMRequest],
    work_per_step_ms: float = 50.0,
) -> dict[str, float]:
    """Quantify the foreground/background overlap of an :class:`AsyncLLMClient`.

    For each request:

    1. Submit the request -- this returns immediately with a future.
    2. Sleep ``work_per_step_ms`` to simulate the RL step's foreground work.
    3. At "decision time", check ``future.done()``. If the future is not
       yet ready, the foreground has to block via ``future.result()`` and
       that wait is timed and accumulated into ``foreground_blocked_ms``.

    Returns
    -------
    dict
        ``wall_time_ms``        total wall clock for the whole loop
        ``foreground_blocked_ms`` aggregate ms the foreground actually waited
        ``lost_overlap_frac``   foreground_blocked_ms / wall_time_ms (clipped to [0, 1])
        ``n_requests``          number of requests successfully completed
    """
    work_s = max(work_per_step_ms, 0.0) / 1000.0
    foreground_blocked_ms = 0.0
    completed = 0

    wall_start = time.perf_counter()
    for req in requests:
        future: Future[LLMResponse] = async_client.submit(req)

        if work_s > 0:
            time.sleep(work_s)

        if not future.done():
            block_start = time.perf_counter()
            future.result()  # block until ready (raises on inner failure)
            foreground_blocked_ms += (time.perf_counter() - block_start) * 1000.0
        else:
            future.result()  # surface any exception even on the fast path

        completed += 1
    wall_time_ms = (time.perf_counter() - wall_start) * 1000.0

    if wall_time_ms > 0:
        lost = foreground_blocked_ms / wall_time_ms
    else:
        lost = 0.0
    # Clip into [0, 1] -- timing skew on a busy host can produce tiny excursions.
    lost_overlap_frac = max(0.0, min(1.0, lost))

    return {
        "wall_time_ms": float(wall_time_ms),
        "foreground_blocked_ms": float(foreground_blocked_ms),
        "lost_overlap_frac": float(lost_overlap_frac),
        "n_requests": float(completed),
    }
