"""Background-thread wrapper that lets the rollout loop fire-and-forget LLM calls.

The rollout submits a request and continues stepping the environment with
the previous subgoal; later, when `future.done()`, the new subgoal is
applied. This keeps the RL loop unblocked even though the underlying
LM Studio queue is single-stream.
"""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor

from .client import LLMClient, LLMRequest, LLMResponse


class AsyncLLMClient:
    """Submits LLM requests to a thread pool and returns futures."""

    def __init__(self, inner: LLMClient, max_workers: int = 4) -> None:
        self.inner = inner
        self.executor = ThreadPoolExecutor(max_workers=max_workers)

    def submit(self, req: LLMRequest) -> Future[LLMResponse]:
        return self.executor.submit(self.inner.call, req)

    def shutdown(self, wait: bool = True) -> None:
        self.executor.shutdown(wait=wait)
