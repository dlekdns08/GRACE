# LLM-Overcooked Meta-Policy: 프로젝트 설계 가이드

> **목표**: Overcooked 협동 환경에서 LLM planner를 *언제* 호출할지 학습하는 메타-policy를 통해, 고정 주기 호출 대비 LLM 호출당 성능 효율을 향상시킨다.

---

## 1. 프로젝트 개요

### 연구 질문

LLM을 RL 에이전트의 high-level planner로 쓰는 기존 연구들(SayCan, Plan-Seq-Learn 등)은 대부분 **고정 주기**로 LLM을 호출한다. 이 가정은 두 가지 비효율을 낳는다.

1. **불필요한 호출**: 상황이 안정적일 때도 매번 LLM을 부르면 추론 비용이 낭비된다.
2. **부족한 호출**: 상황이 급변하거나 협동이 깨질 때 즉시 재계획이 필요한데 다음 호출 시점까지 기다린다.

본 프로젝트는 **"호출 시점 자체를 학습"** 하는 메타-policy를 제안하고, 고정 주기·휴리스틱 baseline 대비 호출-성능 Pareto frontier를 개선함을 보인다.

### 핵심 가설

> H1: 학습된 메타-policy는 고정 주기 호출 대비 동일 성능에서 LLM 호출 횟수를 X% 줄인다.
> H2: 메타-policy는 새로운 주방 layout에 zero-shot transfer 된다.
> H3: 더 강한 LLM(reasoning model)일수록 호출 빈도가 줄어들어도 성능이 유지된다.

### 시스템 구성 요소

```
┌────────────────────────────────────────────────────────────────┐
│                    Experiment Orchestrator                      │
│           (config, seed, logging, checkpoint 관리)              │
└────────────────┬───────────────────────────────┬───────────────┘
                 │                               │
        ┌────────▼─────────┐           ┌────────▼─────────┐
        │   RL Trainer     │           │   Eval Runner    │
        │   (PPO / GRPO)   │           │                  │
        └────────┬─────────┘           └────────┬─────────┘
                 │                               │
                 │   ┌───────────────────────────┘
                 │   │
        ┌────────▼───▼─────┐
        │   Agent Policy   │   ← 행동 정책 (저수준 액션)
        │   + Meta-Policy  │   ← 호출 정책 (LLM 부를지 말지)
        └────────┬─────────┘
                 │
        ┌────────▼─────────┐         ┌──────────────────┐
        │   Environment    │◄────────┤   LLM Client     │
        │   (Unity / Py)   │         │  (LM Studio API) │
        └──────────────────┘         └──────────────────┘
```

---

## 2. 저장소 구조

명확한 분리가 가장 중요하다. **연구 코드의 가장 흔한 실패는 "한 파일에 모든 게 다 들어가서 실험 비교가 불가능해지는 것"** 이다.

```
llm-overcooked-meta/
├── README.md                     # 빠른 시작, 결과 요약
├── DESIGN.md                     # 이 문서
├── pyproject.toml                # 의존성 (uv 또는 poetry)
├── .python-version               # 3.11 권장
│
├── unity_env/                    # Unity 프로젝트 (별도 레포로 분리해도 OK)
│   ├── Assets/
│   │   ├── Scripts/
│   │   │   ├── KitchenEnvironment.cs
│   │   │   ├── ChefAgent.cs
│   │   │   ├── PotController.cs
│   │   │   └── StateSerializer.cs
│   │   └── Scenes/
│   ├── Packages/
│   └── ProjectSettings/
│
├── src/
│   ├── envs/                     # 환경 wrapper (Gym 인터페이스)
│   │   ├── __init__.py
│   │   ├── base.py               # OvercookedEnv 추상 클래스
│   │   ├── unity_env.py          # ML-Agents Unity 래퍼
│   │   ├── python_env.py         # Carroll's Overcooked-AI fallback
│   │   └── state_text.py         # 상태 → 텍스트 변환
│   │
│   ├── llm/                      # LLM 인터페이스 계층
│   │   ├── __init__.py
│   │   ├── client.py             # OpenAI 호환 클라이언트
│   │   ├── async_client.py       # 비동기 호출 래퍼
│   │   ├── prompts.py            # 프롬프트 템플릿
│   │   ├── parsers.py            # JSON 응답 파싱
│   │   ├── cache.py              # prompt-hash 기반 캐시
│   │   └── mock.py               # 테스트용 mock 클라이언트
│   │
│   ├── policies/                 # 정책 모듈
│   │   ├── __init__.py
│   │   ├── base.py               # Policy, MetaPolicy 추상 클래스
│   │   ├── ppo.py                # 기본 PPO 정책
│   │   ├── llm_augmented.py      # PPO + subgoal 조건부 정책
│   │   ├── meta_heuristic.py     # 고정 K, entropy, 상태 변화 기반
│   │   └── meta_learned.py       # GRPO로 학습되는 메타-policy
│   │
│   ├── training/                 # 학습 루프
│   │   ├── __init__.py
│   │   ├── ppo_trainer.py        # 표준 PPO
│   │   ├── grpo_trainer.py       # GRPO (메타-policy용)
│   │   ├── rollout.py            # 환경-정책 상호작용
│   │   └── callbacks.py          # 로깅, 체크포인트, eval
│   │
│   ├── eval/                     # 평가
│   │   ├── __init__.py
│   │   ├── runner.py             # eval 에피소드 실행
│   │   ├── metrics.py            # soup_count, llm_calls, etc.
│   │   └── transfer.py           # layout 일반화 평가
│   │
│   └── utils/
│       ├── __init__.py
│       ├── logging.py            # W&B + 로컬 parquet
│       ├── seeding.py            # 결정론 seed 관리
│       └── config.py             # config 병합/검증
│
├── configs/                      # Hydra 설정
│   ├── base.yaml
│   ├── env/
│   │   ├── cramped_room.yaml
│   │   └── asymmetric_advantages.yaml
│   ├── policy/
│   │   ├── ppo.yaml
│   │   └── llm_augmented.yaml
│   ├── meta/
│   │   ├── fixed_k10.yaml
│   │   ├── fixed_k100.yaml
│   │   ├── entropy.yaml
│   │   └── learned.yaml
│   └── llm/
│       ├── qwen3.6_35b.yaml
│       ├── qwen3_thinking.yaml
│       └── qwen3_8b.yaml
│
├── scripts/
│   ├── train.py                  # 학습 진입점
│   ├── eval.py                   # 평가 진입점
│   ├── sweep.py                  # 여러 시드/설정 일괄 실행
│   └── plot_results.py           # 그래프 생성
│
├── tests/
│   ├── test_state_text.py        # 직렬화/파싱 단위 테스트
│   ├── test_llm_parsers.py
│   ├── test_meta_policy.py
│   └── test_env_smoke.py
│
├── notebooks/                    # 탐색용, 결과는 여기서 만들지 않음
│   ├── 00_env_exploration.ipynb
│   ├── 01_prompt_tuning.ipynb
│   └── 02_results_analysis.ipynb
│
└── docs/
    ├── prompts/                  # 프롬프트 버전 관리
    │   ├── v1_baseline.md
    │   └── v2_with_examples.md
    └── experiments/              # 실험 일지
        └── 2026-05-week1.md
```

**핵심 원칙**:
- `src/`는 **재사용 가능한 라이브러리**처럼 작성한다. 실험별 분기는 `scripts/` + `configs/`에서.
- `notebooks/`는 탐색용. **노트북에서 만든 결과를 논문에 직접 쓰지 않는다**. 결과는 항상 `scripts/`로 재현 가능해야 한다.
- 프롬프트는 `docs/prompts/`에 버전별로 보관. 프롬프트 변경은 코드 변경만큼 중요한 실험 변수다.

---

## 3. 핵심 인터페이스 (가장 중요한 섹션)

설계 전체가 이 추상화들 위에 서 있다. 처음에 시간을 들여 잘 잡으면 6개월이 편하고, 대충 잡으면 매주 리팩토링하게 된다.

### 3.1 Environment

```python
# src/envs/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any
import numpy as np

@dataclass
class EnvObservation:
    """환경 한 스텝의 관측. 정책과 LLM이 모두 사용."""
    raw: dict[str, np.ndarray]    # 에이전트별 raw observation (RL 정책 입력)
    text: str                      # LLM 입력용 텍스트 표현
    info: dict                     # 디버그/로깅용 (좌표, 타이머 등)

@dataclass
class EnvStep:
    obs: EnvObservation
    rewards: dict[str, float]      # agent_id -> reward
    terminated: bool
    truncated: bool
    info: dict

class OvercookedEnv(ABC):
    """모든 환경 구현이 따라야 하는 인터페이스."""

    @abstractmethod
    def reset(self, seed: int | None = None) -> EnvObservation: ...

    @abstractmethod
    def step(self, actions: dict[str, int]) -> EnvStep: ...

    @abstractmethod
    def render(self, mode: str = "rgb_array") -> np.ndarray | None: ...

    @property
    @abstractmethod
    def agent_ids(self) -> list[str]: ...

    @property
    @abstractmethod
    def action_space_size(self) -> int: ...
```

**왜 이렇게**:
- `raw`와 `text`를 동시에 들고 다닌다. 둘 다 매 스텝 필요할 수 있고, 따로 계산하면 비싸다.
- `dict[str, ...]`로 멀티에이전트 처리. 단일 에이전트도 dict 하나짜리로 통일.
- Unity와 Python 환경이 같은 인터페이스를 만족하므로, **본 실험은 Unity로, 디버깅은 빠른 Python으로** 가능.

### 3.2 LLM Client

```python
# src/llm/client.py
from dataclasses import dataclass
from typing import Protocol

@dataclass
class LLMRequest:
    prompt: str
    system: str | None = None
    temperature: float = 0.0
    max_tokens: int = 512
    seed: int | None = None
    metadata: dict = None  # 로깅용 (episode_id, step 등)

@dataclass
class LLMResponse:
    text: str
    latency_ms: float
    prompt_tokens: int
    completion_tokens: int
    cached: bool
    request_id: str

class LLMClient(Protocol):
    """LLM 호출 추상화. 실제 구현은 OpenAI 호환 HTTP, mock, 캐시 wrapper 등."""

    def call(self, req: LLMRequest) -> LLMResponse: ...

    async def call_async(self, req: LLMRequest) -> LLMResponse: ...
```

**왜 Protocol**:
- `Protocol`은 duck typing 친화적이라 mock 클라이언트와 실제 클라이언트를 쉽게 교체 가능.
- 학습 코드는 `LLMClient`만 알면 되고, 실제 구현(LM Studio, OpenAI, mock)은 의존성 주입.

### 3.3 Policy & Meta-Policy

```python
# src/policies/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class PolicyContext:
    """정책이 의사결정에 쓰는 모든 컨텍스트."""
    obs: EnvObservation
    current_subgoal: str | None    # LLM이 마지막으로 준 subgoal
    steps_since_llm_call: int      # 마지막 호출 이후 경과
    episode_step: int

class Policy(ABC):
    """행동 정책: 관측 → 액션."""
    @abstractmethod
    def act(self, ctx: PolicyContext) -> dict[str, int]: ...

class MetaPolicy(ABC):
    """메타-정책: 관측 → LLM 호출 여부 (이진)."""
    @abstractmethod
    def should_call_llm(self, ctx: PolicyContext) -> bool: ...
```

**왜 분리**:
- 메타-policy는 행동 policy와 **다른 입력·다른 출력·다른 학습 알고리즘**을 가진다. 한 클래스에 섞으면 ablation할 때 끔찍해진다.
- 휴리스틱 baseline (`should_call_llm = step % k == 0`)도 같은 인터페이스를 따르므로 비교 실험이 한 줄 변경.

### 3.4 학습 루프 (Rollout 생성기)

```python
# src/training/rollout.py
def collect_rollout(
    env: OvercookedEnv,
    policy: Policy,
    meta_policy: MetaPolicy,
    llm_client: LLMClient,
    max_steps: int,
    logger: RolloutLogger,
) -> RolloutBatch:
    """한 에피소드(또는 max_steps만큼) 굴리며 transition을 모은다."""
    obs = env.reset()
    current_subgoal = None
    steps_since_call = 0
    transitions = []

    for step in range(max_steps):
        ctx = PolicyContext(obs, current_subgoal, steps_since_call, step)

        # 메타-policy가 호출 결정
        if meta_policy.should_call_llm(ctx):
            req = build_llm_request(ctx)
            response = llm_client.call(req)
            current_subgoal = parse_subgoal(response.text)
            steps_since_call = 0
            logger.log_llm_call(step, response, current_subgoal)
        else:
            steps_since_call += 1

        # 행동 policy가 액션 선택
        actions = policy.act(ctx)

        # 환경 진행
        env_step = env.step(actions)

        transitions.append(Transition(
            obs=obs, actions=actions, reward=env_step.rewards,
            next_obs=env_step.obs, done=env_step.terminated,
            subgoal=current_subgoal, llm_called=meta_policy.last_decision,
        ))
        obs = env_step.obs

        if env_step.terminated:
            break

    return RolloutBatch(transitions)
```

**핵심 패턴**:
- 모든 의사결정 시점이 **메타-policy → LLM(선택적) → policy → env** 순서로 명확히 분리됨.
- 모든 transition이 `subgoal`과 `llm_called`를 포함 → 사후 분석에서 "어느 시점에 호출했는가"를 정확히 추적 가능.
- 정책 학습은 이 `transitions`를 받아서 따로 진행. Rollout은 데이터 수집만.

---

## 4. 모듈별 상세 설계

### 4.1 Unity 환경 (C#)

ML-Agents의 `Agent` 클래스를 상속하되, **관측을 raw float[]와 텍스트로 동시에 노출**하는 게 핵심.

```csharp
// unity_env/Assets/Scripts/ChefAgent.cs
public class ChefAgent : Agent
{
    public KitchenEnvironment kitchen;
    public StateSerializer serializer;

    public override void CollectObservations(VectorSensor sensor)
    {
        // 표준 ML-Agents 관측: 위치, 들고 있는 아이템, 솥 상태 등 float[]
        sensor.AddObservation(transform.localPosition);
        sensor.AddObservation((int)heldItem);
        sensor.AddObservation(kitchen.PotState);
        // ...
    }

    public override void OnActionReceived(ActionBuffers actions)
    {
        int discreteAction = actions.DiscreteActions[0];
        // 0: noop, 1-4: 이동, 5: pickup/drop, 6: interact
        ExecuteAction(discreteAction);
    }
}

// StateSerializer.cs - Side Channel로 텍스트 관측을 Python으로 보냄
public class StateSerializer : SideChannel
{
    public StateSerializer() {
        ChannelId = new Guid("621f0a70-4f87-11ea-a6bf-784f4387d1f7");
    }

    public string SerializeKitchen(KitchenEnvironment k) {
        var sb = new StringBuilder();
        sb.AppendLine($"Step: {k.Step}/{k.MaxSteps}");
        sb.AppendLine($"Score: {k.Score}");
        foreach (var agent in k.Agents) {
            sb.AppendLine($"- {agent.Name} at ({agent.X},{agent.Y}) " +
                          $"holding {agent.HeldItem ?? "nothing"}");
        }
        sb.AppendLine($"Pot: {k.Pot.OnionsIn}/3 onions, " +
                      $"cooking {k.Pot.CookingTime}s remaining");
        return sb.ToString();
    }
}
```

**중요한 결정**:
- Unity 측에서 텍스트를 만들어 넘긴다. Python에서 raw 관측을 받아 텍스트화하는 것보다 **버그가 적고 디버깅이 쉽다**(Unity Editor에서 직접 확인 가능).
- Side Channel을 쓰면 ML-Agents 표준 관측 외에 임의 데이터를 보낼 수 있다.

### 4.2 상태 → 텍스트 변환 (Python 측 fallback)

Unity 없이 Python Overcooked-AI로 디버깅할 때를 대비한 동일한 텍스트 형식.

```python
# src/envs/state_text.py
def state_to_text(state: OvercookedState) -> str:
    """게임 상태를 LLM이 이해할 수 있는 텍스트로 변환."""
    lines = [
        f"Step: {state.timestep}/{state.max_steps}",
        f"Score: {state.score} (soups served: {state.soups_served})",
        "",
        "Agents:",
    ]
    for agent in state.agents:
        held = agent.held_item.name if agent.held_item else "nothing"
        lines.append(f"  - {agent.name} at {agent.position}, holding {held}")

    lines.append("")
    lines.append("Pots:")
    for i, pot in enumerate(state.pots):
        if pot.is_empty:
            lines.append(f"  - Pot {i}: empty")
        elif pot.is_cooking:
            lines.append(f"  - Pot {i}: cooking, {pot.time_left}s remaining")
        elif pot.is_ready:
            lines.append(f"  - Pot {i}: ready to serve")
        else:
            lines.append(f"  - Pot {i}: {pot.onion_count}/3 onions, not started")

    return "\n".join(lines)
```

**원칙**:
- **결정론적**: 같은 상태는 항상 같은 텍스트. 캐시가 작동하기 위한 필수 조건.
- **압축**: 토큰 수를 의식한다. 200~400 토큰 이내가 이상적.
- **버전 관리**: 이 함수가 바뀌면 모든 캐시를 무효화하고 실험을 다시 돌려야 한다. `__version__` 상수를 두고 캐시 키에 포함시킨다.

### 4.3 LLM Client 구현

```python
# src/llm/client.py
import time
import hashlib
from openai import OpenAI

class LMStudioClient:
    """LM Studio (또는 vLLM/MLX-LM) OpenAI 호환 서버용 클라이언트."""

    def __init__(self, base_url: str, model: str, timeout: float = 30.0):
        self.client = OpenAI(base_url=base_url, api_key="local", timeout=timeout)
        self.model = model

    def call(self, req: LLMRequest) -> LLMResponse:
        start = time.perf_counter()
        messages = []
        if req.system:
            messages.append({"role": "system", "content": req.system})
        messages.append({"role": "user", "content": req.prompt})

        resp = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
            seed=req.seed,
        )
        latency = (time.perf_counter() - start) * 1000

        return LLMResponse(
            text=resp.choices[0].message.content,
            latency_ms=latency,
            prompt_tokens=resp.usage.prompt_tokens,
            completion_tokens=resp.usage.completion_tokens,
            cached=False,
            request_id=resp.id,
        )
```

```python
# src/llm/cache.py
class CachedLLMClient:
    """프롬프트 해시 기반 캐시 wrapper. 같은 입력은 한 번만 호출."""

    def __init__(self, inner: LLMClient, prompt_version: str):
        self.inner = inner
        self.cache: dict[str, LLMResponse] = {}
        self.prompt_version = prompt_version

    def _key(self, req: LLMRequest) -> str:
        # 프롬프트 버전을 키에 포함해서 프롬프트 변경 시 캐시 자동 무효화
        material = f"{self.prompt_version}|{req.system}|{req.prompt}|{req.temperature}|{req.seed}"
        return hashlib.sha256(material.encode()).hexdigest()

    def call(self, req: LLMRequest) -> LLMResponse:
        key = self._key(req)
        if key in self.cache:
            cached = self.cache[key]
            return LLMResponse(**{**cached.__dict__, "cached": True, "latency_ms": 0.1})

        resp = self.inner.call(req)
        self.cache[key] = resp
        return resp
```

**성능 영향**: 학습 초반 exploration에서 같은 상태가 자주 나오므로 캐시 적중률이 30~60% 정도 나온다. 학습 시간이 절반 가까이 줄 수 있다.

### 4.4 비동기 호출 패턴

LLM 호출이 RL 루프를 막지 않게 한다.

```python
# src/llm/async_client.py
import asyncio
from concurrent.futures import Future, ThreadPoolExecutor

class AsyncLLMClient:
    """LLM 호출을 백그라운드로 보내고 future를 반환.
    rollout이 LLM 응답을 기다리는 동안 정책은 마지막 subgoal로 행동을 계속.
    """

    def __init__(self, inner: LLMClient, max_workers: int = 4):
        self.inner = inner
        self.executor = ThreadPoolExecutor(max_workers=max_workers)

    def submit(self, req: LLMRequest) -> Future[LLMResponse]:
        return self.executor.submit(self.inner.call, req)
```

**rollout 측 사용**:
```python
pending_call: Future | None = None

for step in range(max_steps):
    # 응답이 도착했으면 적용
    if pending_call is not None and pending_call.done():
        resp = pending_call.result()
        current_subgoal = parse_subgoal(resp.text)
        pending_call = None

    # 새 호출 결정
    if pending_call is None and meta_policy.should_call_llm(ctx):
        pending_call = async_client.submit(build_llm_request(ctx))

    # 정책은 막힘 없이 진행
    actions = policy.act(ctx)
    obs = env.step(actions).obs
```

**주의**: Mac Studio + LM Studio는 기본적으로 단일 inference 큐다. `max_workers=4`로 보낸다고 4배 빨라지지 않는다. 그러나 RL 루프의 *블로킹*은 사라진다(이게 진짜 이득).

### 4.5 메타-Policy 구현들

**휴리스틱 (baseline)**:
```python
# src/policies/meta_heuristic.py
class FixedKMetaPolicy(MetaPolicy):
    def __init__(self, k: int):
        self.k = k

    def should_call_llm(self, ctx: PolicyContext) -> bool:
        return ctx.episode_step % self.k == 0

class EntropyMetaPolicy(MetaPolicy):
    """행동 정책의 entropy가 임계값을 넘으면 LLM에 도움 요청."""
    def __init__(self, policy: Policy, threshold: float):
        self.policy = policy
        self.threshold = threshold

    def should_call_llm(self, ctx: PolicyContext) -> bool:
        with torch.no_grad():
            logits = self.policy.get_logits(ctx.obs.raw)
            entropy = -(logits.softmax(-1) * logits.log_softmax(-1)).sum(-1).mean()
        return entropy.item() > self.threshold
```

**학습된 메타-policy (메인 기여)**:
```python
# src/policies/meta_learned.py
class LearnedMetaPolicy(MetaPolicy, nn.Module):
    """관측 + 컨텍스트를 받아 호출 확률을 출력하는 작은 MLP.
    GRPO로 학습. 보상 = (성능 개선) - λ * (호출 비용).
    """
    def __init__(self, obs_dim: int, hidden_dim: int = 64):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(obs_dim + 3, hidden_dim),  # +3: subgoal_active, steps_since_call, episode_step
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 2),  # 0: skip, 1: call
        )

    def should_call_llm(self, ctx: PolicyContext) -> bool:
        feat = self._featurize(ctx)
        logits = self.net(feat)
        if self.training:
            action = torch.distributions.Categorical(logits=logits).sample()
        else:
            action = logits.argmax(-1)
        self.last_decision = action.item() == 1
        self.last_logp = F.log_softmax(logits, -1)[action]
        return self.last_decision
```

GRPO 학습 루프는 별도 trainer에서 처리. 그룹 단위로 (호출 정책, 행동 정책) 쌍을 평가하고 상대적 순위로 업데이트.

---

## 5. 실험 구성 시스템

### Hydra 구조

```yaml
# configs/base.yaml
defaults:
  - env: cramped_room
  - policy: llm_augmented
  - meta: fixed_k100
  - llm: qwen3.6_35b
  - _self_

experiment:
  name: ${meta.name}_${env.name}_seed${seed}
  seed: 0
  total_steps: 5_000_000
  eval_every: 100_000
  log_dir: ./runs

logging:
  wandb_project: llm-overcooked
  wandb_mode: online    # offline / disabled
```

```yaml
# configs/meta/learned.yaml
name: learned
_target_: src.policies.meta_learned.LearnedMetaPolicy
obs_dim: ${env.obs_dim}
hidden_dim: 64

training:
  trainer: grpo
  call_cost: 0.01     # 호출당 페널티 (튜닝 변수)
  group_size: 8       # GRPO 그룹 크기
```

### 실험 실행

```bash
# 단일 실험
python scripts/train.py meta=fixed_k10 seed=0

# 시드 sweep
python scripts/train.py -m meta=fixed_k10 seed=0,1,2,3,4

# 메타-policy 비교
python scripts/train.py -m \
    meta=fixed_k10,fixed_k100,entropy,learned \
    seed=0,1,2 \
    env=cramped_room

# 모델 ablation (이게 본 실험)
python scripts/train.py -m \
    llm=qwen3.6_35b,qwen3_thinking,qwen3_8b \
    meta=learned \
    seed=0,1,2
```

---

## 6. 로깅 전략

> **이게 잘못되면 6개월 일이 무의미해진다.**

### 무엇을 로깅하는가

| 카테고리 | 항목 | 어디에 |
|---|---|---|
| 환경 | episode return, soup count, episode length | W&B |
| 메타-policy | LLM 호출 횟수/에피소드, 호출 시점 분포, 호출 결정 entropy | W&B + parquet |
| LLM | latency, prompt/completion tokens, 캐시 적중률 | parquet |
| 학습 | policy loss, value loss, KL, entropy | W&B |
| 시스템 | GPU/MPS 사용률, RAM, throughput (steps/sec) | W&B |

### 왜 parquet도?

W&B는 시각화에 좋지만 **사후 통계 분석에는 불편하다**. 모든 transition을 parquet로 떨어뜨려 두면 pandas/polars로 자유롭게 분석 가능.

```python
# src/utils/logging.py
class RolloutLogger:
    def __init__(self, run_dir: Path):
        self.transitions: list[dict] = []
        self.llm_calls: list[dict] = []
        self.run_dir = run_dir

    def log_transition(self, t: Transition):
        self.transitions.append({
            "episode": t.episode_id,
            "step": t.step,
            "reward": sum(t.reward.values()),
            "subgoal": t.subgoal,
            "llm_called": t.llm_called,
        })

    def log_llm_call(self, step: int, resp: LLMResponse, subgoal: str):
        self.llm_calls.append({
            "step": step,
            "latency_ms": resp.latency_ms,
            "tokens_in": resp.prompt_tokens,
            "tokens_out": resp.completion_tokens,
            "cached": resp.cached,
            "subgoal": subgoal,
        })

    def flush(self):
        pd.DataFrame(self.transitions).to_parquet(self.run_dir / "transitions.parquet")
        pd.DataFrame(self.llm_calls).to_parquet(self.run_dir / "llm_calls.parquet")
```

---

## 7. 테스트 전략

연구 코드라고 테스트를 안 짜면 디버깅에 한 달 날린다. **최소 이것들만은 반드시**:

### 단위 테스트

```python
# tests/test_state_text.py
def test_state_to_text_deterministic():
    """같은 상태 → 같은 텍스트 (캐시 작동의 전제)."""
    state = make_test_state(seed=42)
    assert state_to_text(state) == state_to_text(state)

def test_state_to_text_distinguishes_states():
    """서로 다른 상태는 다른 텍스트."""
    s1 = make_test_state(pot_onions=2)
    s2 = make_test_state(pot_onions=3)
    assert state_to_text(s1) != state_to_text(s2)


# tests/test_llm_parsers.py
def test_parse_valid_subgoal():
    response = '{"agent_a": "go_to_pot", "agent_b": "fetch_dish"}'
    assert parse_subgoal(response) == {"agent_a": "go_to_pot", "agent_b": "fetch_dish"}

def test_parse_malformed_returns_none():
    """LLM이 망가진 출력을 줘도 학습이 안 죽어야 함."""
    assert parse_subgoal("uhh I think...") is None
    assert parse_subgoal("{not valid json") is None


# tests/test_meta_policy.py
def test_fixed_k_calls_at_correct_intervals():
    meta = FixedKMetaPolicy(k=10)
    decisions = [meta.should_call_llm(make_ctx(step=i)) for i in range(30)]
    assert sum(decisions) == 3  # step 0, 10, 20
```

### Smoke 테스트

```python
# tests/test_env_smoke.py
def test_unity_env_runs_5_steps():
    """Unity 빌드가 깨졌는지 5초 안에 확인."""
    env = UnityOvercookedEnv(build_path=TEST_BUILD)
    obs = env.reset()
    for _ in range(5):
        actions = {a: 0 for a in env.agent_ids}
        env.step(actions)
    env.close()
```

### Mock LLM

CI에서 실제 LLM을 부르면 안 된다. 모든 학습 테스트는 mock으로.

```python
# src/llm/mock.py
class MockLLMClient:
    """미리 정해진 응답을 순환적으로 반환."""
    def __init__(self, responses: list[str]):
        self.responses = responses
        self.call_count = 0

    def call(self, req: LLMRequest) -> LLMResponse:
        text = self.responses[self.call_count % len(self.responses)]
        self.call_count += 1
        return LLMResponse(
            text=text, latency_ms=0.0, prompt_tokens=10,
            completion_tokens=5, cached=False, request_id=f"mock-{self.call_count}",
        )
```

---

## 8. 개발 워크플로우

### 일일 루틴

1. **연구 일지 첫 5분**: 어제 무엇을 했고, 오늘 무엇을 할 것인가. `docs/experiments/`에 markdown.
2. **새 브랜치**: 기능당 브랜치. `feat/learned-meta-policy`, `exp/qwen-comparison`.
3. **작은 커밋**: 의미 단위로. 커밋 메시지에 *왜*를 쓴다.
4. **테스트 먼저**: 새 모듈은 단위 테스트와 동시에. CI 없어도 로컬에서 `pytest`.

### 주간 루틴

1. **금요일 회고**: `docs/experiments/`에 그 주의 진척, 막힌 것, 다음 주 계획.
2. **결과 백업**: `runs/` 디렉토리를 외장 드라이브 또는 클라우드로 sync. 학습된 모델 + parquet 로그.
3. **GitHub push**: private repo면 매일 push해도 OK.

### 실험 단위

각 실험은 다음을 만족해야 한다:
- 한 줄 명령으로 재현 가능 (`python scripts/train.py +experiment=foo seed=0`)
- 로그/체크포인트가 고유 디렉토리(`runs/{exp_name}_{timestamp}_{seed}/`)에 저장됨
- 결과 그래프는 `scripts/plot_results.py runs/{exp_name}_*`로 자동 생성됨

---

## 9. 코딩 표준

연구 코드라고 자유분방하면 6개월 후에 자기 코드를 못 읽는다. 최소한 이것들은:

### Python
- **타입 힌트 필수**: 모든 함수 시그니처에. `mypy`가 통과하면 좋지만 강제는 아님.
- **포매터**: `ruff format` (black 호환). pre-commit hook으로.
- **린터**: `ruff check`. 에러는 머지 금지.
- **docstring**: 공개 함수/클래스에 짧게. 길게 쓰지 말고 *왜*를 적기.
- **dataclass / pydantic**: 데이터 구조는 dict 말고 타입을 가진 클래스로.

### 명명 규칙
- `make_*`: 새 객체 생성 (`make_env`, `make_policy`)
- `compute_*`: 순수 계산 (`compute_returns`, `compute_advantages`)
- `*_fn`: 함수 객체 (`reward_fn`, `obs_fn`)
- 약어 금지: `obs` OK (관용), `cfg` OK (관용), `mp` 금지 (`meta_policy`로)

### 절대 하지 말 것
- 매직 넘버 (`if step % 100 == 0`) → config로 빼기
- 글로벌 상태 (`global last_subgoal`) → 명시적으로 전달
- 한 함수 100줄 이상 → 분리
- 노트북에서 학습된 결과를 논문에 직접 → 항상 `scripts/`로 재현

---

## 10. 시작 순서 (첫 2주)

이론은 충분하니 첫 행동을 분명히.

### Day 1
- 레포 만들고 위 구조대로 빈 디렉토리 세팅
- `pyproject.toml` 작성, `uv sync`
- README에 한 문단으로 프로젝트 설명

### Day 2~3
- LM Studio 띄우고 Qwen3.6-35B-A3B 다운로드
- `src/llm/client.py`로 "Hello, world" 테스트
- `tests/test_llm_parsers.py` 골격 작성

### Day 4~7
- Overcooked-AI (Carroll's) 클론, Python으로 한 에피소드 실행
- `src/envs/python_env.py` 래퍼 작성
- `src/envs/state_text.py` 첫 버전, 단위 테스트

### Week 2
- ML-Agents 공식 GridWorld 튜토리얼 완주
- `src/policies/ppo.py`로 Python Overcooked 학습 (LLM 없이 baseline)
- 학습 곡선이 W&B에 뜨는지 확인 → 이 시점에서 인프라가 다 작동함

이렇게 하면 Month 1 끝까지 인프라가 다 갖춰지고, Month 2부터 본격적으로 Unity와 LLM 통합에 들어갈 수 있다.

---

## 마무리

이 문서는 6개월간 "지금 뭘 해야 하지"가 흐려질 때마다 돌아올 기준점이다. 매주 이 문서와 실제 코드가 일치하는지 점검하고, 설계가 바뀌면 *코드보다 먼저* 이 문서를 업데이트하라.

코드는 6개월 뒤 GitHub에 공개될 것이고, 다른 연구자들이 이 인터페이스 위에서 후속 연구를 할 것이다. **인터페이스가 곧 기여의 일부다**.

질문/막힘이 생기면 `docs/experiments/`에 적어두고, 일주일 안에 답이 안 나오면 사람한테 물어봐라. 혼자 닫혀서 버티는 게 가장 비싸다.
