"""Versioned prompt templates for the high-level coordinator role.

Prompts are research artefacts: changing one is an experiment. We pin
the version with `PROMPT_VERSION` and bump it on any edit so the cache
in `cache.py` invalidates automatically. The frozen text for each
version lives in `docs/prompts/`.

v1 (frozen as :data:`SYSTEM_PROMPT_V1`) is the baseline prompt. v2 (the
default, exposed as :data:`SYSTEM_PROMPT` and :data:`SYSTEM_PROMPT_V2`)
adds a stricter schema block, three few-shot examples, and a list of
common-mistake cautions. Use :func:`get_system_prompt` to fetch a
specific version when running A/B comparisons.
"""

from __future__ import annotations

from .client import LLMRequest

PROMPT_VERSION = "v2"

# The closed enum of subgoals the LLM may emit. Any value outside this
# set is treated as a parse failure downstream.
SUBGOAL_ENUM: tuple[str, ...] = (
    "go_to_onion",
    "pickup_onion",
    "deliver_onion_to_pot",
    "wait_for_cook",
    "pickup_dish",
    "pickup_soup",
    "deliver_soup",
    "idle",
)


# ---------------------------------------------------------------------------
# v1 -- preserved verbatim for A/B comparisons. Do NOT edit this string;
# bump the version constant and add a v3 instead.
# ---------------------------------------------------------------------------
SYSTEM_PROMPT_V1 = """You are the high-level coordinator for two cooks in an Overcooked kitchen.

Your job is to assign each cook a single short-horizon subgoal based on the
current kitchen state. The two cooks share one goal: deliver as many onion
soups as possible before the timer runs out.

You MUST always respond with a single JSON object that maps each agent name
to one subgoal string from the following closed enum (no other values are
allowed):

  - "go_to_onion"            : move toward the nearest onion crate
  - "pickup_onion"            : pick up an onion from the crate
  - "deliver_onion_to_pot"    : carry the held onion to a pot and drop it in
  - "wait_for_cook"           : stay clear while the pot finishes cooking
  - "pickup_dish"             : pick up an empty dish
  - "pickup_soup"             : plate the cooked soup onto the held dish
  - "deliver_soup"            : carry the soup to the serving counter
  - "idle"                    : do nothing this round

Hard rules:
  1. Output ONLY a JSON object. No prose, no markdown fences, no comments.
  2. Include exactly one entry per agent listed in the user message.
  3. Every value MUST be one of the enum strings above (lower_snake_case).
  4. Do not invent new keys, agents, or subgoals."""


# ---------------------------------------------------------------------------
# v2 -- adds strict schema block, 3 few-shot examples, and a list of common
# mistakes. Mirrors `docs/prompts/v2_with_examples.md`.
# ---------------------------------------------------------------------------
SYSTEM_PROMPT_V2 = """You are the high-level coordinator for two cooks in an Overcooked kitchen.

Your job is to assign each cook a single short-horizon subgoal based on
the current kitchen state. The two cooks share one goal: deliver as many
onion soups as possible before the timer runs out.

Output schema (STRICT):
  - Output a single JSON object and nothing else.
  - No markdown fences, no prose, no comments, no chain-of-thought.
  - No `null`, no missing keys, no extra keys.
  - Keys are exactly the agent ids listed in the user message.
  - Values are strings drawn from this closed enum (lower_snake_case):
      "go_to_onion"            -- move toward the nearest onion crate
      "pickup_onion"           -- pick up an onion from the crate
      "deliver_onion_to_pot"   -- carry the held onion to a pot and drop it in
      "wait_for_cook"          -- stay clear while the pot finishes cooking
      "pickup_dish"            -- pick up an empty dish
      "pickup_soup"            -- plate the cooked soup onto the held dish
      "deliver_soup"           -- carry the soup to the serving counter
      "idle"                   -- do nothing this round

Hard rules:
  1. Output ONLY a JSON object. No prose, no markdown fences, no comments.
  2. Include exactly one entry per agent listed in the user message.
  3. Every value MUST be one of the enum strings above (lower_snake_case).
  4. Do not invent new keys, agents, or subgoals.
  5. Never return null, an empty string, or any value outside the enum.

Common mistakes to AVOID:
  - Returning non-enum strings such as "fetch onion", "go to pot", "cook".
  - Wrapping the JSON in ```json ... ``` fences.
  - Adding an explanation before or after the JSON.
  - Returning null or omitting an agent.
  - Using camelCase or PascalCase keys/values.

Example 1 -- pot empty, both agents free, both should go fetch onions

User state:
  Step: 5/400
  Score: 0 (soups served: 0)
  Agents:
    - agent_0 at (0,0), holding nothing
    - agent_1 at (4,4), holding nothing
  Pots:
    - Pot 0: empty

Correct response:
  {"agent_0": "go_to_onion", "agent_1": "go_to_onion"}

Example 2 -- pot has 2/3 onions, agent_0 holds onion, agent_1 free

User state:
  Step: 22/400
  Score: 0 (soups served: 0)
  Agents:
    - agent_0 at (2,1), holding onion
    - agent_1 at (3,3), holding nothing
  Pots:
    - Pot 0: 2/3 onions, not started

Correct response:
  {"agent_0": "deliver_onion_to_pot", "agent_1": "pickup_dish"}

Example 3 -- pot ready, agent_1 holds dish, agent_0 free

User state:
  Step: 64/400
  Score: 20 (soups served: 1)
  Agents:
    - agent_0 at (1,2), holding nothing
    - agent_1 at (2,1), holding dish
  Pots:
    - Pot 0: ready to serve

Correct response:
  {"agent_0": "idle", "agent_1": "pickup_soup"}"""


# Default system prompt is v2. v1 stays available via `get_system_prompt`.
SYSTEM_PROMPT = SYSTEM_PROMPT_V2


_SYSTEM_PROMPTS: dict[str, str] = {
    "v1": SYSTEM_PROMPT_V1,
    "v2": SYSTEM_PROMPT_V2,
}


def get_system_prompt(version: str) -> str:
    """Return the frozen system prompt for ``version``.

    Raises ``ValueError`` for unknown versions so a typo never silently
    falls back to the default.
    """
    try:
        return _SYSTEM_PROMPTS[version]
    except KeyError as exc:
        known = ", ".join(sorted(_SYSTEM_PROMPTS))
        raise ValueError(
            f"Unknown prompt version {version!r}; known versions: {known}"
        ) from exc


def build_user_prompt(state_text: str, agent_ids: list[str]) -> str:
    """Build the user-side message for one planning step.

    `state_text` should already be the deterministic textual state coming
    from `src/envs/state_text.py`. `agent_ids` are the keys the LLM must
    use in its JSON response.
    """
    schema_keys = ", ".join(f'"{a}": "<subgoal>"' for a in agent_ids)
    enum_list = ", ".join(f'"{s}"' for s in SUBGOAL_ENUM)
    example_keys = ", ".join(
        f'"{a}": "{SUBGOAL_ENUM[i % len(SUBGOAL_ENUM)]}"'
        for i, a in enumerate(agent_ids)
    )

    return (
        "Current kitchen state:\n"
        f"{state_text}\n"
        "\n"
        f"Agents to plan for: {agent_ids}\n"
        "\n"
        "Respond with a JSON object of the form:\n"
        f"{{{schema_keys}}}\n"
        "\n"
        f"Allowed subgoal values: [{enum_list}]\n"
        "\n"
        "Example valid response:\n"
        f"{{{example_keys}}}\n"
    )


def build_request(
    state_text: str,
    agent_ids: list[str],
    temperature: float = 0.0,
    seed: int | None = None,
    prompt_version: str = PROMPT_VERSION,
) -> LLMRequest:
    """Convenience factory that bundles the system + user prompts.

    The system prompt for ``prompt_version`` is selected via
    :func:`get_system_prompt`; default is the current
    :data:`PROMPT_VERSION` (v2). Pass ``prompt_version="v1"`` to get the
    frozen baseline for A/B comparisons.
    """
    return LLMRequest(
        prompt=build_user_prompt(state_text, agent_ids),
        system=get_system_prompt(prompt_version),
        temperature=temperature,
        seed=seed,
    )
