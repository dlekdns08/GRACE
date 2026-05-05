"""Robust parsers for LLM JSON outputs.

LLM outputs are routinely wrapped in markdown fences, prefixed with
chatter, or simply malformed. These parsers are the safety net so a bad
response never crashes the rollout.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable

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


def parse_subgoal_with_validation(
    response_text: str,
    agent_ids: Iterable[str],
    valid_subgoals: Iterable[str] | None = None,
) -> dict[str, str] | None:
    """Strict variant of :func:`parse_subgoal`.

    Layered checks (any failing returns ``None``):

      1. ``parse_subgoal`` returns a dict.
      2. Every requested ``agent_id`` is a key in that dict.
      3. Every value is a member of ``valid_subgoals`` (defaults to
         :data:`src.llm.prompts.SUBGOAL_ENUM`).

    Returning ``None`` rather than raising keeps the rollout uninterrupted —
    callers should treat ``None`` as "no usable plan, keep last subgoal".
    """
    parsed = parse_subgoal(response_text)
    if parsed is None:
        return None

    required = list(agent_ids)
    if not all(aid in parsed for aid in required):
        return None

    if valid_subgoals is None:
        # Local import keeps the module free of import-time deps for tests
        # that exercise `parse_subgoal` alone.
        from .prompts import SUBGOAL_ENUM

        allowed: frozenset[str] = frozenset(SUBGOAL_ENUM)
    else:
        allowed = frozenset(valid_subgoals)

    if not all(parsed[aid] in allowed for aid in required):
        return None

    # Return a dict containing exactly the requested agents (drops extras).
    return {aid: parsed[aid] for aid in required}
