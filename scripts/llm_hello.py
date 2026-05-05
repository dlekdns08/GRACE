"""Smoke script: verify the local LM Studio server is reachable.

Usage:
    python scripts/llm_hello.py

Reads the model name from the `LMSTUDIO_MODEL` environment variable
(default: `qwen3.6-35b-a3b`) and the base URL from `LMSTUDIO_BASE_URL`
(default: `http://localhost:1234/v1`). Prints the response text plus
latency and token counts. Exits 1 with an error message if the call
fails for any reason (server not running, model not loaded, etc.).
"""

from __future__ import annotations

import os
import sys

from src.llm.client import LLMRequest, LMStudioClient


def main() -> int:
    base_url = os.environ.get("LMSTUDIO_BASE_URL", "http://localhost:1234/v1")
    model = os.environ.get("LMSTUDIO_MODEL", "qwen3.6-35b-a3b")
    timeout = float(os.environ.get("LMSTUDIO_TIMEOUT", "30"))

    print(f"Connecting to LM Studio at {base_url} (model={model}, timeout={timeout}s)")

    client = LMStudioClient(base_url=base_url, model=model, timeout=timeout)
    req = LLMRequest(
        prompt="Say hello in one short sentence.",
        system="You are a terse assistant.",
        temperature=0.0,
        max_tokens=64,
    )

    try:
        resp = client.call(req)
    except Exception as exc:  # noqa: BLE001 - this is a CLI smoke test
        print(f"ERROR: LLM call failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print("--- response ---")
    print(resp.text)
    print("--- metrics ---")
    print(f"latency_ms       : {resp.latency_ms:.1f}")
    print(f"prompt_tokens    : {resp.prompt_tokens}")
    print(f"completion_tokens: {resp.completion_tokens}")
    print(f"request_id       : {resp.request_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
