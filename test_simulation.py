from __future__ import annotations

import random
import unittest

from config import DEFAULT_REST_EVENTS
from models import Action, Job, Player, SimulationConfig
from simulation import (
    AI_MODE_COMPLETION,
    AI_MODE_IMMEDIATE,
    AI_MODE_ROLLOUT,
    _choose_action,
    _empty_single,
    _execute_rest_event,
    _apply_action_success,
)


def make_config(
    actions: list[Action],
    *,
    job_name: str = "大工",
    build_success_rate: float = 1.0,
    guard_bonus: float = 0.0,
) -> SimulationConfig:
    return SimulationConfig(
        trials=1,
        max_turns=1,
        player_jobs=[job_name],
        castle_costs=[100_000],
        build_success_rate=build_success_rate,
        build_failure_loss_rate=0.5,
        initial_stamina=10,
        base_max_stamina=10,
        knight_stamina_bonus=0,
        rest_events={key: dict(value) for key, value in DEFAULT_REST_EVENTS.items()},
        jobs={job_name: Job(name=job_name, normal_actions=actions)},
        seed=1,
        rollout_count=100,
        normal_guard_build_bonus=guard_bonus,
        normal_carpenter_build_discount=0,
        advanced_carpenter_build_discount=0,
    )


class CompletionAiTests(unittest.TestCase):
    def choose(self, config: SimulationConfig, actions: list[Action], money: int, mode: str) -> Action:
        return _choose_action(
            config=config,
            actions=actions,
            players=[Player(job_name=config.player_jobs[0], stamina=10)],
            player_index=0,
            money=money,
            progress=0,
            delayed=[],
            turn=1,
            max_stamina=10,
            rng=random.Random(123),
            policy_mode=mode,
            current_turn_build_success_bonus=0.0,
            current_turn_build_cost_halved=False,
            current_lottery_multiplier=1.0,
        )

    def test_completion_ai_values_carpenter_half_when_it_enables_final_turn_build(self) -> None:
        income = Action("大工", "A", "normal", 1.0, 1, amount=5_000)
        half = Action("大工", "B", "normal", 1.0, 1, effect_type="build_cost_multiplier")
        actions = [income, half]
        config = make_config(actions)

        selected = self.choose(config, actions, money=90_000, mode=AI_MODE_COMPLETION)

        self.assertEqual(selected.name, "B")

    def test_completion_ai_values_guard_bonus_when_build_cost_is_already_available(self) -> None:
        income = Action("騎士", "A", "normal", 1.0, 1, amount=5_000)
        guard = Action("騎士", "護衛", "normal", 1.0, 1, amount=0)
        actions = [income, guard]
        config = make_config(actions, job_name="騎士", build_success_rate=0.0, guard_bonus=1.0)

        selected = self.choose(config, actions, money=100_000, mode=AI_MODE_COMPLETION)

        self.assertEqual(selected.name, "護衛")

    def test_total_income_ai_and_completion_ai_can_choose_different_actions(self) -> None:
        income = Action("大工", "A", "normal", 1.0, 1, amount=5_000)
        half = Action("大工", "B", "normal", 1.0, 1, effect_type="build_cost_multiplier")
        actions = [income, half]
        config = make_config(actions)

        rollout_selected = self.choose(config, actions, money=90_000, mode=AI_MODE_ROLLOUT)
        completion_selected = self.choose(config, actions, money=90_000, mode=AI_MODE_COMPLETION)

        self.assertEqual(rollout_selected.name, "A")
        self.assertEqual(completion_selected.name, "B")

    def test_existing_immediate_ai_still_uses_immediate_expected_income(self) -> None:
        low = Action("大工", "low", "normal", 1.0, 1, amount=1_000)
        high = Action("大工", "high", "normal", 1.0, 1, amount=5_000)
        actions = [low, high]
        config = make_config(actions)

        selected = self.choose(config, actions, money=0, mode=AI_MODE_IMMEDIATE)

        self.assertEqual(selected.name, "high")

class NeetPrayerLotteryTests(unittest.TestCase):
    def test_neet_prayer_boosts_next_lottery_once_and_then_expires(self) -> None:
        action = Action("ニート", "神に祈る", "normal", 1.0, 1, amount=0)
        config = make_config([action], job_name="ニート")
        config.rest_events["lottery"]["success_rate"] = 1 / 6
        config.normal_neet_pray_lottery_multiplier = 3.0
        player = Player(job_name="ニート", stamina=10)
        stats = _empty_single()

        _, _, _, _, lottery_multiplier, _ = _apply_action_success(action, config, 0, 1, [], player, 10, False, 1.0)
        self.assertEqual(lottery_multiplier, 3.0)

        _, lottery_multiplier = _execute_rest_event("lottery", config, player, 1, 10, random.Random(1), stats, 0, lottery_multiplier)

        self.assertEqual(lottery_multiplier, 1.0)
        self.assertEqual(stats["boosted_lottery_attempts"], 1)
        self.assertEqual(stats["boosted_lottery_wins"], 1)

        _execute_rest_event("lottery", config, player, 1, 10, random.Random(2), stats, 0, lottery_multiplier)

        self.assertEqual(stats["unboosted_lottery_attempts"], 1)
        self.assertEqual(stats["unboosted_lottery_wins"], 0)

    def test_neet_prayer_keeps_highest_pending_multiplier(self) -> None:
        normal = Action("ニート", "神に祈る", "normal", 1.0, 1, amount=0)
        advanced = Action("ニート", "神に祈る", "advanced", 1.0, 1, amount=0)
        config = make_config([normal, advanced], job_name="ニート")
        player = Player(job_name="ニート", stamina=10)

        _, _, _, _, lottery_multiplier, _ = _apply_action_success(advanced, config, 0, 1, [], player, 10, False, 1.0)
        _, _, _, _, lottery_multiplier, _ = _apply_action_success(normal, config, 0, 1, [], player, 10, False, lottery_multiplier)

        self.assertEqual(lottery_multiplier, 4.0)

    def test_boosted_lottery_success_rate_is_capped_at_one(self) -> None:
        config = make_config([], job_name="ニート")
        config.rest_events["lottery"]["success_rate"] = 0.4
        player = Player(job_name="商人", stamina=10)
        stats = _empty_single()

        _execute_rest_event("lottery", config, player, 1, 10, random.Random(2), stats, 0, 4.0)

        self.assertEqual(stats["boosted_lottery_attempts"], 1)
        self.assertEqual(stats["boosted_lottery_wins"], 1)


if __name__ == "__main__":
    unittest.main()
