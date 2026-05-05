"""Versioned prompt templates for the high-level coordinator role.

Prompts are research artefacts: changing one is an experiment. We pin
the version with `PROMPT_VERSION` and bump it on any edit so the cache
in `cache.py` invalidates automatically. The frozen text for each
version lives in `docs/prompts/`.
"""

from __future__ import annotations

from .client import LLMRequest

PROMPT_VERSION = "v1"

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

SYSTEM_PROMPT = """You are the high-level coordinator for two cooks in an Overcooked kitchen.

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
) -> LLMRequest:
    """Convenience factory that bundles the v1 system + user prompts."""
    return LLMRequest(
        prompt=build_user_prompt(state_text, agent_ids),
        system=SYSTEM_PROMPT,
        temperature=temperature,
        seed=seed,
    )
