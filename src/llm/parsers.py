"""Robust parsers for LLM JSON outputs.

LLM outputs are routinely wrapped in markdown fences, prefixed with
chatter, or simply malformed. These parsers are the safety net so a bad
response never crashes the rollout.
"""

from __future__ import annotations

import json
import re

# Matches the most common markdown code-fence styles, with or without a
# language tag (e.g. ```json ... ``` or ``` ... ```).
_FENCE_RE = re.compile(
    r"^\s*```(?:[a-zA-Z0-9_-]+)?\s*\n?(?P<body>.*?)\n?```\s*$",
    re.DOTALL,
)


def _strip_markdown_fence(text: str) -> str:
    match = _FENCE_RE.match(text)
    if match:
        return match.group("body").strip()
    return text.strip()


def parse_subgoal(response_text: str) -> dict[str, str] | None:
    """Parse a `{agent_id: subgoal}` JSON object from an LLM response.

    Returns `None` (never raises) if the input is empty, not valid JSON,
    not an object, or contains non-string values.
    """
    if not response_text or not response_text.strip():
        return None

    cleaned = _strip_markdown_fence(response_text)
    if not cleaned:
        return None

    try:
        parsed = json.loads(cleaned)
    except (ValueError, TypeError):
        return None

    if not isinstance(parsed, dict):
        return None

    result: dict[str, str] = {}
    for key, value in parsed.items():
        if not isinstance(key, str) or not isinstance(value, str):
            return None
        result[key] = value

    return result
