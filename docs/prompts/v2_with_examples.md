# Prompt v2 — strict schema with few-shot examples

Frozen reference for `PROMPT_VERSION = "v2"`. Any change to the wording
below requires bumping `PROMPT_VERSION` in `src/llm/prompts.py`, which
will automatically invalidate the response cache.

The intent of v2 is to harden the v1 prompt with:

1. A more explicit schema statement (JSON only, no markdown fences,
   no prose, no chain-of-thought outside required fields, no `null`).
2. Three concrete worked examples covering the most common kitchen
   transitions (empty pot, pot filling, pot ready).
3. A short list of common mistakes the LLM tends to make so the model
   can self-correct before sampling.

The v1 system prompt is preserved verbatim under `SYSTEM_PROMPT_V1` in
`src/llm/prompts.py` so A/B comparisons stay trivial.

## Subgoal enum

The LLM must select each agent's subgoal from this closed list:

| Subgoal                  | Meaning                                      |
| ------------------------ | -------------------------------------------- |
| `go_to_onion`            | Move toward the nearest onion crate          |
| `pickup_onion`           | Pick up an onion from the crate              |
| `deliver_onion_to_pot`   | Carry the held onion to a pot and drop it in |
| `wait_for_cook`          | Stay clear while the pot finishes cooking    |
| `pickup_dish`            | Pick up an empty dish                        |
| `pickup_soup`            | Plate the cooked soup onto the held dish     |
| `deliver_soup`           | Carry the soup to the serving counter        |
| `idle`                   | Do nothing this round                        |

## System prompt (v2)

```
You are the high-level coordinator for two cooks in an Overcooked kitchen.

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

### Example 1 -- pot empty, both agents free, both should go fetch onions

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

### Example 2 -- pot has 2/3 onions, agent_0 holds onion, agent_1 free

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

### Example 3 -- pot ready, agent_1 holds dish, agent_0 free

User state:
  Step: 64/400
  Score: 20 (soups served: 1)
  Agents:
    - agent_0 at (1,2), holding nothing
    - agent_1 at (2,1), holding dish
  Pots:
    - Pot 0: ready to serve

Correct response:
  {"agent_0": "idle", "agent_1": "pickup_soup"}
```

## User prompt template

`build_user_prompt(state_text, agent_ids)` produces the same body as v1:

```
Current kitchen state:
<state_text>

Agents to plan for: <agent_ids>

Respond with a JSON object of the form:
{"agent_0": "<subgoal>", "agent_1": "<subgoal>"}

Allowed subgoal values: ["go_to_onion", "pickup_onion", "deliver_onion_to_pot", "wait_for_cook", "pickup_dish", "pickup_soup", "deliver_soup", "idle"]

Example valid response:
{"agent_0": "go_to_onion", "agent_1": "pickup_onion"}
```

## JSON schema

```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "agent_0": { "type": "string", "enum": [
      "go_to_onion", "pickup_onion", "deliver_onion_to_pot", "wait_for_cook",
      "pickup_dish", "pickup_soup", "deliver_soup", "idle"
    ]},
    "agent_1": { "type": "string", "enum": [
      "go_to_onion", "pickup_onion", "deliver_onion_to_pot", "wait_for_cook",
      "pickup_dish", "pickup_soup", "deliver_soup", "idle"
    ]}
  },
  "required": ["agent_0", "agent_1"]
}
```

## What changed vs v1

- Added an explicit "Output schema (STRICT)" block with negative
  constraints (no fences, no prose, no chain-of-thought, no `null`).
- Inlined three few-shot examples covering the empty / filling / ready
  pot transitions.
- Added a "Common mistakes to AVOID" section enumerating the most
  frequent failure modes observed in v1 (non-enum strings, code fences,
  explanations, missing agents, camelCase).

## How to iterate further

A future `notebooks/01_prompt_tuning.ipynb` should:

1. Load a frozen 200-state corpus saved from rollouts under both v1 and
   v2 prompts (use `MockLLMClient` or LM Studio).
2. Compute parse-success rate, validity rate, and average completion
   length per prompt version.
3. Inspect failure cases by category (non-enum string, code fence,
   missing agent) and propose v3 wording.
4. Run a paired-bootstrap CI on the v1-vs-v2 validity rate using
   `src.eval.statistics`.

Skip the notebook for now — it is for the user to author once a
real LLM has produced enough samples to study.
