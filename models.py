from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Action:
    job: str
    name: str
    tier: str
    success_rate: float
    stamina_cost: int
    amount: int = 0
    multiplier: float | None = None
    effect_type: str = "income"
    delay_turns: int = 0
    delay_multiplier: float = 1.0
    raw_effect: str = ""
    notes: str = ""


@dataclass
class Job:
    name: str
    normal_actions: list[Action] = field(default_factory=list)
    advanced_actions: list[Action] = field(default_factory=list)
    passive: dict[str, Any] = field(default_factory=dict)


@dataclass
class Player:
    job_name: str
    stamina: int
    promoted: bool = False


@dataclass
class DelayedEvent:
    due_turn: int
    amount: int
    source: str


@dataclass
class SimulationConfig:
    trials: int
    max_turns: int
    player_jobs: list[str]
    castle_costs: list[int]
    build_success_rate: float
    build_failure_loss_rate: float
    initial_stamina: int
    base_max_stamina: int
    knight_stamina_bonus: int
    rest_events: dict[str, dict[str, float | int | str]]
    jobs: dict[str, Job]
    seed: int | None = None
    action_ai_mode: str = "rollout"
    rollout_count: int = 100
    normal_guard_build_bonus: float = 1 / 6
    advanced_guard_build_bonus: float = 2 / 6
    normal_carpenter_build_discount: int = 20_000
    advanced_carpenter_build_discount: int = 50_000
    carpenter_build_cost_multiplier: float = 0.5
    normal_merchant_turn_income: int = 5_000
    advanced_merchant_turn_income: int = 10_000
    normal_neet_turn_recovery: int = 1
    normal_neet_pray_lottery_multiplier: float = 3.0
    advanced_neet_pray_lottery_multiplier: float = 4.0
