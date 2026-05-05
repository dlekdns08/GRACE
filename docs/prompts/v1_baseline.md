# Prompt v1 — baseline

Frozen reference for `PROMPT_VERSION = "v1"`. Any change to the wording
below requires bumping `PROMPT_VERSION` in `src/llm/prompts.py`, which
will automatically invalidate the response cache.

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

## System prompt

```
You are the high-level coordinator for two cooks in an Overcooked kitchen.

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
  4. Do not invent new keys, agents, or subgoals.
```

## User prompt template

`build_user_prompt(state_text, agent_ids)` produces:

```
Current kitchen state:
<state_text>

Agents to plan for: <agent_ids>

Respond with a JSON object of the form:
{"agent_a": "<subgoal>", "agent_b": "<subgoal>"}

Allowed subgoal values: ["go_to_onion", "pickup_onion", "deliver_onion_to_pot", "wait_for_cook", "pickup_dish", "pickup_soup", "deliver_soup", "idle"]

Example valid response:
{"agent_a": "go_to_onion", "agent_b": "pickup_onion"}
```

## JSON schema

```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "agent_a": { "type": "string", "enum": [
      "go_to_onion", "pickup_onion", "deliver_onion_to_pot", "wait_for_cook",
      "pickup_dish", "pickup_soup", "deliver_soup", "idle"
    ]},
    "agent_b": { "type": "string", "enum": [
      "go_to_onion", "pickup_onion", "deliver_onion_to_pot", "wait_for_cook",
      "pickup_dish", "pickup_soup", "deliver_soup", "idle"
    ]}
  },
  "required": ["agent_a", "agent_b"]
}
```

## Worked example

Input state text (from `state_to_text`):

```
Step: 42/400
Score: 20 (soups served: 1)

Agents:
  - agent_a at (2, 3), holding nothing
  - agent_b at (4, 1), holding onion

Pots:
  - Pot 0: 2/3 onions, not started
```

Expected response:

```json
{"agent_a": "go_to_onion", "agent_b": "deliver_onion_to_pot"}
```
