"""Rollout collection (DESIGN section 3.4).

The rollout loop ties together env, action policy, meta-policy, and LLM
client. Each step is exactly the four-stage decision pipeline laid out in
DESIGN: meta-policy decides whether to call the LLM, the LLM (optionally)
updates the current subgoal, the action policy chooses actions, the env
advances. Every transition records the subgoal in effect *and* whether
the LLM was called this step so post-hoc analysis can reproduce the
full decision trace.
"""

from __future__ import annotations

import time
from concurrent.futures import Future
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from src.envs import EnvObservation, OvercookedEnv
from src.llm import (
    AsyncLLMClient,
    LLMClient,
    LLMResponse,
    build_request,
    parse_subgoal,
)
from src.policies.base import MetaPolicy, Policy, PolicyContext
from src.utils.logging import (
    EpisodeRecord,
    LLMCallRecord,
    RolloutLogger,
    TransitionRecord,
)

SUBGOAL_TO_IDX: dict[str, int] = {
    "go_to_onion": 0,
    "pickup_onion": 1,
    "deliver_onion_to_pot": 2,
    "wait_for_cook": 3,
    "pickup_dish": 4,
    "pickup_soup": 5,
    "deliver_soup": 6,
    "idle": 7,
}

N_SUBGOAL_CLASSES = len(SUBGOAL_TO_IDX)


def subgoal_to_onehot(subgoal: str | None, n_classes: int = N_SUBGOAL_CLASSES) -> np.ndarray:
    """Encode a subgoal name as a one-hot float32 vector.

    Returns an all-zero vector when ``subgoal`` is ``None`` or unknown so
    "no subgoal yet" is a valid representable input to the policy.
    """
    arr = np.zeros((n_classes,), dtype=np.float32)
    if subgoal is None:
        return arr
    idx = SUBGOAL_TO_IDX.get(subgoal)
    if idx is None or idx >= n_classes:
        return arr
    arr[idx] = 1.0
    return arr


@dataclass(slots=True)
class Transition:
    """One environment transition with full per-agent decision context."""

    obs_raw: dict[str, np.ndarray]
    actions: dict[str, int]
    rewards: dict[str, float]
    next_obs_raw: dict[str, np.ndarray]
    done: bool
    subgoal: dict[str, str] | None
    subgoal_oh: dict[str, np.ndarray] | None
    llm_called: bool
    log_probs: dict[str, float]
    values: dict[str, float]


@dataclass(slots=True)
class RolloutBatch:
    """The output of a single :func:`collect_rollout` call."""

    transitions: list[Transition]
    episode_returns: list[float]
    episode_lengths: list[int]
    soup_counts: list[int]
    n_llm_calls: int
    n_cached_calls: int
    n_invalid_subgoals: int = 0
    extras: dict[str, Any] = field(default_factory=dict)


def _validate_subgoal_dict(
    parsed: dict[str, str] | None,
    agent_ids: list[str],
) -> tuple[dict[str, str] | None, int]:
    """Drop subgoals that are not in :data:`SUBGOAL_TO_IDX`.

    Returns ``(cleaned, n_invalid)`` where ``cleaned`` keeps only the agents
    whose value is a known subgoal name. If ``parsed`` is None or every entry
    is invalid we return ``(None, n_invalid)`` so callers can fall back to the
    "no subgoal" branch.
    """
    if parsed is None:
        return None, 0
    n_invalid = 0
    cleaned: dict[str, str] = {}
    for aid in agent_ids:
        val = parsed.get(aid)
        if val is None:
            continue
        if val in SUBGOAL_TO_IDX:
            cleaned[aid] = val
        else:
            n_invalid += 1
    if not cleaned:
        return None, n_invalid
    return cleaned, n_invalid


# ----------------------------------------------------------------------------- helpers
def _join_reward(rewards: dict[str, float]) -> float:
    """Sum across agents — DESIGN's shared-reward convention."""
    return float(sum(rewards.values()))


def _build_subgoal_onehots(
    subgoal: dict[str, str] | None, agent_ids: list[str]
) -> dict[str, np.ndarray]:
    """One-hot encode the per-agent subgoals into a dict for storage."""
    out: dict[str, np.ndarray] = {}
    sg_map = subgoal or {}
    for aid in agent_ids:
        out[aid] = subgoal_to_onehot(sg_map.get(aid))
    return out


def _log_llm_call(
    logger: RolloutLogger | None,
    episode: int,
    step: int,
    response: LLMResponse,
    subgoal: dict[str, str] | None,
) -> None:
    if logger is None:
        return
    # Encode the dict subgoal compactly for the parquet column.
    subgoal_str: str | None
    if subgoal is None:
        subgoal_str = None
    else:
        subgoal_str = ";".join(f"{k}={v}" for k, v in sorted(subgoal.items()))
    logger.log_llm_call(
        LLMCallRecord(
            episode=episode,
            step=step,
            latency_ms=float(response.latency_ms),
            tokens_in=int(response.prompt_tokens),
            tokens_out=int(response.completion_tokens),
            cached=bool(response.cached),
            subgoal=subgoal_str,
        )
    )


def _log_transition(
    logger: RolloutLogger | None,
    episode: int,
    step: int,
    transition: Transition,
) -> None:
    if logger is None:
        return
    if transition.subgoal is None:
        sg_str: str | None = None
    else:
        sg_str = ";".join(f"{k}={v}" for k, v in sorted(transition.subgoal.items()))
    logger.log_transition(
        TransitionRecord(
            episode=episode,
            step=step,
            reward=_join_reward(transition.rewards),
            subgoal=sg_str,
            llm_called=transition.llm_called,
            done=transition.done,
        )
    )


# ----------------------------------------------------------------------- main entry
def collect_rollout(
    env: OvercookedEnv,
    policy: Policy,
    meta_policy: MetaPolicy,
    llm_client: LLMClient,
    n_steps: int,
    logger: RolloutLogger | None = None,
    episode_id: int = 0,
    use_async_llm: bool = False,
) -> RolloutBatch:
    """Roll out for exactly ``n_steps`` env steps, possibly across episodes.

    Each step follows the DESIGN-mandated order:

      1. ``meta_policy.should_call_llm(ctx)``
      2. (if yes) ``llm_client.call(...)`` -> parse subgoal -> update state
      3. ``policy.act(ctx)`` -> action dict
      4. ``env.step(actions)`` -> next obs, reward, done

    The rollout records a `Transition` for every env step and an
    `EpisodeRecord` whenever the env terminates or truncates.

    Async mode wraps ``llm_client`` in :class:`AsyncLLMClient` (one
    in-flight request at a time) so the rollout is never blocked on the
    LLM. While a future is pending and the meta-policy still wants to
    call, the request is dropped (the next "should call" will retry).
    """
    if n_steps <= 0:
        raise ValueError("n_steps must be positive")

    async_client: AsyncLLMClient | None = None
    if use_async_llm:
        async_client = AsyncLLMClient(llm_client, max_workers=1)

    transitions: list[Transition] = []
    episode_returns: list[float] = []
    episode_lengths: list[int] = []
    soup_counts: list[int] = []

    n_llm_calls = 0
    n_cached_calls = 0
    n_invalid_subgoals = 0

    obs: EnvObservation = env.reset()
    current_subgoal: dict[str, str] | None = None
    steps_since_call = 0
    episode_step = 0
    current_episode = episode_id
    episode_return = 0.0
    episode_llm_calls = 0
    episode_cached_calls = 0
    pending_future: Future[LLMResponse] | None = None

    meta_policy.reset()
    agent_ids = list(env.agent_ids)

    try:
        for _ in range(n_steps):
            ctx = PolicyContext(
                obs=obs,
                current_subgoal=current_subgoal,
                steps_since_llm_call=steps_since_call,
                episode_step=episode_step,
            )

            # 1) Meta-policy decision (and surface it on the meta object for logs).
            decision = bool(meta_policy.should_call_llm(ctx))
            meta_policy.last_decision = decision

            llm_called_this_step = False

            # 2) LLM call (sync or async).
            if async_client is not None:
                # First, pick up any completed future.
                if pending_future is not None and pending_future.done():
                    try:
                        resp = pending_future.result()
                    except Exception:  # pragma: no cover - defensive
                        resp = None
                    pending_future = None
                    if resp is not None:
                        parsed = parse_subgoal(resp.text)
                        if parsed is not None:
                            current_subgoal = parsed
                        steps_since_call = 0
                        n_llm_calls += 1
                        episode_llm_calls += 1
                        if resp.cached:
                            n_cached_calls += 1
                            episode_cached_calls += 1
                        _log_llm_call(
                            logger, current_episode, episode_step, resp, current_subgoal
                        )
                        llm_called_this_step = True

                # Then, if the meta-policy wants to call AND nothing is in flight, submit.
                if decision and pending_future is None:
                    req = build_request(ctx.obs.text, agent_ids)
                    pending_future = async_client.submit(req)
            else:
                if decision:
                    req = build_request(ctx.obs.text, agent_ids)
                    response = llm_client.call(req)
                    parsed = parse_subgoal(response.text)
                    if parsed is not None:
                        current_subgoal = parsed
                    steps_since_call = 0
                    n_llm_calls += 1
                    episode_llm_calls += 1
                    if response.cached:
                        n_cached_calls += 1
                        episode_cached_calls += 1
                    _log_llm_call(
                        logger, current_episode, episode_step, response, current_subgoal
                    )
                    llm_called_this_step = True

            if not llm_called_this_step:
                steps_since_call += 1

            # 3) Action policy.
            actions = policy.act(ctx)

            # 4) Environment step.
            env_step = env.step(actions)

            # Pull the per-agent (log_prob, value) the policy cached during act().
            log_probs: dict[str, float] = {}
            values: dict[str, float] = {}
            cache = getattr(policy, "last_step_cache", None)
            if isinstance(cache, dict):
                for aid in agent_ids:
                    entry = cache.get(aid, {})
                    log_probs[aid] = float(entry.get("log_prob", 0.0))
                    values[aid] = float(entry.get("value", 0.0))
            else:
                log_probs = {aid: 0.0 for aid in agent_ids}
                values = {aid: 0.0 for aid in agent_ids}

            done = bool(env_step.terminated or env_step.truncated)
            obs_raw_copy = {aid: np.asarray(v).copy() for aid, v in obs.raw.items()}
            next_obs_raw_copy = {
                aid: np.asarray(v).copy() for aid, v in env_step.obs.raw.items()
            }
            subgoal_oh_dict = (
                _build_subgoal_onehots(current_subgoal, agent_ids)
                if current_subgoal is not None
                else None
            )

            transition = Transition(
                obs_raw=obs_raw_copy,
                actions=dict(actions),
                rewards=dict(env_step.rewards),
                next_obs_raw=next_obs_raw_copy,
                done=done,
                subgoal=dict(current_subgoal) if current_subgoal is not None else None,
                subgoal_oh=subgoal_oh_dict,
                llm_called=llm_called_this_step,
                log_probs=log_probs,
                values=values,
            )
            transitions.append(transition)
            _log_transition(logger, current_episode, episode_step, transition)

            episode_return += _join_reward(env_step.rewards)
            episode_step += 1
            obs = env_step.obs

            if done:
                soup_count = int(env_step.info.get("soup_count", 0))
                episode_returns.append(episode_return)
                episode_lengths.append(episode_step)
                soup_counts.append(soup_count)

                if logger is not None:
                    logger.log_episode(
                        EpisodeRecord(
                            episode=current_episode,
                            return_=episode_return,
                            length=episode_step,
                            soup_count=soup_count,
                            llm_calls=episode_llm_calls,
                            cached_calls=episode_cached_calls,
                        )
                    )

                # Roll into the next episode.
                current_episode += 1
                episode_return = 0.0
                episode_step = 0
                episode_llm_calls = 0
                episode_cached_calls = 0
                steps_since_call = 0
                current_subgoal = None
                pending_future = None
                meta_policy.reset()
                obs = env.reset()
    finally:
        if async_client is not None:
            # Don't wait on a still-running call — the result would be
            # discarded anyway.
            async_client.shutdown(wait=False)

    return RolloutBatch(
        transitions=transitions,
        episode_returns=episode_returns,
        episode_lengths=episode_lengths,
        soup_counts=soup_counts,
        n_llm_calls=n_llm_calls,
        n_cached_calls=n_cached_calls,
        extras={"wallclock_sec": time.perf_counter()},
    )
