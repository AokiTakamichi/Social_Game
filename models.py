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
