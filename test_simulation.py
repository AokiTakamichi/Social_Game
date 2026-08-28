from __future__ import annotations

import random
import unittest

from config import CARD_HAND_SWAP, CARD_LOTTERY, CARD_ORDER_SWAP, CARD_PROMOTION, CARD_SLEEP, CARD_WALK, DEFAULT_REST_EVENTS
from models import Action, CardState, Job, Player, SimulationConfig
from simulation import (
    AI_MODE_COMPLETION,
    AI_MODE_IMMEDIATE,
    AI_MODE_ROLLOUT,
    _choose_action,
    _choose_rest_card,
    _clone_cards,
    _create_card_state,
    _deal_initial_hands,
    _discard_drawn_unusable_card,
    _draw_cards,
    _empty_single,
    _execute_rest_event,
    _rebuild_deck,
    _run_mulligans,
    _total_cards,
    _use_rest_card,
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
            cards=CardState(deck=[], discard=[], hands=[[]]),
            turn=1,
            order_position=0,
            action_order=[0],
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


class RestCardSystemTests(unittest.TestCase):
    def test_a_initial_deal_before_turn_gives_each_player_two_cards(self) -> None:
        config = make_config([])
        config.player_jobs = ["A", "B", "C"]
        cards = _create_card_state(config, 3, random.Random(1))
        _deal_initial_hands(config, cards, random.Random(2), _empty_single())

        self.assertEqual([len(hand) for hand in cards.hands], [2, 2, 2])

    def test_b_without_mulligan_hands_stay_two(self) -> None:
        config = make_config([])
        config.mulligan_enabled = False
        cards = _create_card_state(config, 2, random.Random(1))
        _deal_initial_hands(config, cards, random.Random(2), _empty_single())

        self.assertEqual([len(hand) for hand in cards.hands], [2, 2])

    def test_c_mulligan_one_card_draws_replacement_and_keeps_two(self) -> None:
        config = make_config([])
        cards = CardState(deck=[CARD_WALK], discard=[], hands=[[CARD_PROMOTION, CARD_LOTTERY]])
        stats = _empty_single()

        _run_mulligans(config, cards, [Player("A", 10)], random.Random(3), stats, 0, AI_MODE_IMMEDIATE)

        self.assertEqual(len(cards.hands[0]), 2)
        self.assertIn(CARD_WALK, cards.hands[0])
        self.assertEqual(stats["mulligan_cards"], 1)

    def test_d_mulligan_removed_card_is_not_drawn_before_reinsert(self) -> None:
        config = make_config([])
        cards = CardState(deck=[CARD_LOTTERY], discard=[], hands=[[CARD_PROMOTION, CARD_WALK]])

        _run_mulligans(config, cards, [Player("A", 10)], random.Random(3), _empty_single(), 0, AI_MODE_IMMEDIATE)

        self.assertIn(CARD_PROMOTION, cards.deck)
        self.assertIn(CARD_LOTTERY, cards.hands[0])

    def test_e_rest_draw_to_three_use_one_return_to_two(self) -> None:
        config = make_config([])
        cards = CardState(deck=[CARD_LOTTERY], discard=[], hands=[[CARD_WALK, CARD_SLEEP]])
        stats = _empty_single()
        player = Player("A", 1)

        _draw_cards(cards, 0, 1, random.Random(1), stats)
        selected = _choose_rest_card(config, [player], 0, 0, 0, [], cards, 1, 0, [0], 10, random.Random(1), AI_MODE_IMMEDIATE, 0, False, 1.0)
        _use_rest_card(selected, config, [player], 0, 0, 0, [], cards, 1, 0, [0], 10, random.Random(1), stats, AI_MODE_IMMEDIATE, 0, False, 1.0)

        self.assertEqual(len(cards.hands[0]), 2)

    def test_f_used_card_goes_to_discard(self) -> None:
        config = make_config([])
        cards = CardState(deck=[], discard=[], hands=[[CARD_WALK, CARD_SLEEP, CARD_LOTTERY]])

        _use_rest_card(CARD_WALK, config, [Player("A", 10)], 0, 0, 0, [], cards, 1, 0, [0], 10, random.Random(1), _empty_single(), AI_MODE_IMMEDIATE, 0, False, 1.0)

        self.assertIn(CARD_WALK, cards.discard)

    def test_g_empty_deck_rebuilds_from_discard(self) -> None:
        cards = CardState(deck=[], discard=[CARD_WALK], hands=[[]])
        stats = _empty_single()

        _draw_cards(cards, 0, 1, random.Random(1), stats)

        self.assertEqual(cards.hands[0], [CARD_WALK])
        self.assertEqual(stats["deck_rebuilds"], 1)

    def test_h_card_exchange_swaps_remaining_two_cards_with_target(self) -> None:
        config = make_config([])
        cards = CardState(deck=[], discard=[], hands=[[CARD_LOTTERY, CARD_WALK, CARD_HAND_SWAP], [CARD_PROMOTION, CARD_SLEEP]])
        players = [Player("A", 10), Player("B", 10)]

        _use_rest_card(CARD_HAND_SWAP, config, players, 0, 0, 0, [], cards, 1, 0, [0, 1], 10, random.Random(1), _empty_single(), AI_MODE_IMMEDIATE, 0, False, 1.0)

        self.assertEqual(cards.hands[0], [CARD_PROMOTION, CARD_SLEEP])
        self.assertEqual(cards.hands[1], [CARD_LOTTERY, CARD_WALK])
        self.assertEqual(cards.discard, [CARD_HAND_SWAP])

    def test_i_order_swap_changes_only_unacted_players(self) -> None:
        config = make_config([])
        players = [Player("A", 10), Player("大工", 10), Player("商人", 10), Player("騎士", 10)]
        cards = CardState(deck=[], discard=[], hands=[[], [CARD_ORDER_SWAP], [], []])
        order = [0, 1, 2, 3]

        _use_rest_card(CARD_ORDER_SWAP, config, players, 1, 0, 0, [], cards, 1, 1, order, 10, random.Random(1), _empty_single(), AI_MODE_COMPLETION, 0, False, 1.0)

        self.assertEqual(order[:2], [0, 1])
        self.assertCountEqual(order[2:], [2, 3])

    def test_j_next_turn_order_is_default(self) -> None:
        config = make_config([])
        players = [Player("A", 10), Player("大工", 10), Player("商人", 10)]
        altered = [1, 2, 0]

        next_order = list(range(len(players)))

        self.assertNotEqual(altered, next_order)
        self.assertEqual(next_order, [0, 1, 2])

    def test_k_locked_promotion_card_is_not_usable_and_stays_in_hand(self) -> None:
        config = make_config([])
        cards = CardState(deck=[], discard=[], hands=[[CARD_PROMOTION, CARD_PROMOTION]])
        player = Player("A", 10)

        selected = _choose_rest_card(config, [player], 0, 0, 0, [], cards, 1, 0, [0], 10, random.Random(1), AI_MODE_IMMEDIATE, 0, False, 1.0)

        self.assertIsNone(selected)
        self.assertEqual(cards.hands[0], [CARD_PROMOTION, CARD_PROMOTION])

    def test_locked_promotion_only_hand_discards_only_newly_drawn_card(self) -> None:
        config = make_config([])
        cards = CardState(deck=[CARD_PROMOTION], discard=[], hands=[[CARD_PROMOTION, CARD_PROMOTION]])
        stats = _empty_single()
        player = Player("A", 10)

        drawn = _draw_cards(cards, 0, 1, random.Random(1), stats)
        selected = _choose_rest_card(config, [player], 0, 0, 0, [], cards, 1, 0, [0], 10, random.Random(1), AI_MODE_IMMEDIATE, 0, False, 1.0)
        if selected is None:
            _discard_drawn_unusable_card(cards, 0, drawn[-1], stats)

        self.assertIsNone(selected)
        self.assertEqual(cards.hands[0], [CARD_PROMOTION, CARD_PROMOTION])
        self.assertEqual(cards.discard, [CARD_PROMOTION])

    def test_l_lottery_multiplier_applies_and_is_consumed_on_card_use(self) -> None:
        config = make_config([])
        config.rest_events["lottery"]["success_rate"] = 1 / 6
        cards = CardState(deck=[], discard=[], hands=[[CARD_LOTTERY]])
        stats = _empty_single()

        _money, multiplier = _use_rest_card(CARD_LOTTERY, config, [Player("A", 10)], 0, 0, 0, [], cards, 1, 0, [0], 10, random.Random(1), stats, AI_MODE_IMMEDIATE, 0, False, 3.0)

        self.assertEqual(multiplier, 1.0)
        self.assertEqual(stats["boosted_lottery_attempts"], 1)

    def test_m_rollout_card_state_copy_does_not_mutate_original(self) -> None:
        cards = CardState(deck=[CARD_LOTTERY], discard=[CARD_WALK], hands=[[CARD_SLEEP, CARD_ORDER_SWAP]])
        cloned = _clone_cards(cards)
        cloned.deck.pop()
        cloned.hands[0].append(CARD_HAND_SWAP)

        self.assertEqual(cards.deck, [CARD_LOTTERY])
        self.assertEqual(cards.hands[0], [CARD_SLEEP, CARD_ORDER_SWAP])

    def test_n_card_total_is_conserved_across_draw_use_rebuild(self) -> None:
        config = make_config([])
        cards = CardState(deck=[CARD_LOTTERY], discard=[CARD_WALK], hands=[[CARD_SLEEP, CARD_ORDER_SWAP]])
        stats = _empty_single()
        total = _total_cards(cards)

        _draw_cards(cards, 0, 1, random.Random(1), stats)
        _use_rest_card(CARD_LOTTERY, config, [Player("A", 10)], 0, 0, 0, [], cards, 1, 0, [0], 10, random.Random(1), stats, AI_MODE_IMMEDIATE, 0, False, 1.0)
        _rebuild_deck(cards, random.Random(1), stats)

        self.assertEqual(_total_cards(cards), total)


if __name__ == "__main__":
    unittest.main()
