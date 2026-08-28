from __future__ import annotations

import random
from collections import Counter, defaultdict
from statistics import mean

from models import Action, DelayedEvent, Player, SimulationConfig

AI_MODE_IMMEDIATE = "immediate"
AI_MODE_ROLLOUT = "rollout"


def run_monte_carlo(config: SimulationConfig) -> dict:
    rng = random.Random(config.seed)
    aggregate = _empty_aggregate(config.max_turns, len(config.castle_costs))

    for _ in range(config.trials):
        result = _run_single_game(config, rng)
        _merge_result(aggregate, result)

    return _finalize(aggregate, config.trials, config.max_turns)


def run_promotion_rate_comparison(config: SimulationConfig, rates: list[float]) -> list[dict]:
    rows: list[dict] = []
    for rate in rates:
        rest_events = {key: dict(value) for key, value in config.rest_events.items()}
        rest_events["promotion"]["success_rate"] = rate
        compared = SimulationConfig(
            trials=config.trials,
            max_turns=config.max_turns,
            player_jobs=list(config.player_jobs),
            castle_costs=list(config.castle_costs),
            build_success_rate=config.build_success_rate,
            build_failure_loss_rate=config.build_failure_loss_rate,
            initial_stamina=config.initial_stamina,
            base_max_stamina=config.base_max_stamina,
            knight_stamina_bonus=config.knight_stamina_bonus,
            rest_events=rest_events,
            jobs=config.jobs,
            seed=config.seed,
            action_ai_mode=config.action_ai_mode,
            rollout_count=config.rollout_count,
            normal_guard_build_bonus=config.normal_guard_build_bonus,
            advanced_guard_build_bonus=config.advanced_guard_build_bonus,
        )
        result = run_monte_carlo(compared)
        rows.append({
            "promotion_success_rate_setting": rate,
            "clear_rate": result["clear_rate"],
            "average_clear_turn": result["average_clear_turn"],
            "average_total_income": result["average_total_income"],
            "promotion_attempt_rate": result["promotion_attempt_game_rate"],
            "promotion_success_rate": result["promotion_success_game_rate"],
            "average_promotion_turn": result["average_promotion_turn"],
            "lottery_income_share": result["lottery_income_share"],
        })
    return rows


def _run_single_game(config: SimulationConfig, rng: random.Random) -> dict:
    max_stamina = _max_stamina(config)
    initial_stamina = min(config.initial_stamina, max_stamina)
    players = [Player(job_name=job, stamina=initial_stamina) for job in config.player_jobs]
    stats = _empty_single()
    reached = [False] * (len(config.castle_costs) + 1)
    reached[0] = True

    money, progress, _delayed, turn_end_money = _simulate_from(
        config=config,
        rng=rng,
        players=players,
        money=0,
        progress=0,
        delayed=[],
        start_turn=1,
        start_player_index=0,
        max_stamina=max_stamina,
        stats=stats,
        policy_mode=config.action_ai_mode,
        collect_turn_money=True,
        reached=reached,
    )

    while len(turn_end_money) < config.max_turns:
        turn_end_money.append(money)

    for idx in range(1, progress + 1):
        reached[idx] = True
    stats["final_progress"] = progress
    stats["turn_end_money"] = turn_end_money
    stats["reached"] = reached
    stats["promotion_attempt_game_jobs"].update(stats["promotion_attempt_jobs"].keys())
    stats["promotion_success_game_jobs"].update(stats["promotion_success_jobs"].keys())
    stats["promotion_attempt_games"] = 1 if stats["promotion_attempt_jobs"] else 0
    stats["promotion_success_games"] = 1 if stats["promotion_success_jobs"] else 0
    for job in set(config.player_jobs):
        if job in stats["promotion_success_jobs"]:
            stats["promoted_game_income_by_job"][job] += stats["income_total"]
            stats["promoted_game_count_by_job"][job] += 1
        else:
            stats["unpromoted_game_income_by_job"][job] += stats["income_total"]
            stats["unpromoted_game_count_by_job"][job] += 1
    return stats


def _simulate_from(
    config: SimulationConfig,
    rng: random.Random,
    players: list[Player],
    money: int,
    progress: int,
    delayed: list[DelayedEvent],
    start_turn: int,
    start_player_index: int,
    max_stamina: int,
    stats: dict,
    policy_mode: str,
    collect_turn_money: bool,
    reached: list[bool] | None = None,
    current_turn_build_success_bonus: float = 0.0,
) -> tuple[int, int, list[DelayedEvent], list[int]]:
    turn_end_money: list[int] = []
    player_count = len(players)

    for turn in range(start_turn, config.max_turns + 1):
        if start_player_index == 0:
            due = [event for event in delayed if event.due_turn == turn]
            delayed = [event for event in delayed if event.due_turn != turn]
            for event in due:
                money += event.amount
                stats["income_by_source"][event.source] += event.amount
                stats["income_total"] += event.amount

        build_success_bonus = current_turn_build_success_bonus if turn == start_turn and start_player_index > 0 else 0.0
        for player_index in range(start_player_index, player_count):
            player = players[player_index]
            job = config.jobs.get(player.job_name)
            actions = (job.advanced_actions if player.promoted else job.normal_actions) if job else []
            available = [a for a in actions if player.stamina - a.stamina_cost >= 1 and a.effect_type != "unsupported"]
            if available:
                action = _choose_action(config, available, players, player_index, money, progress, delayed, turn, max_stamina, rng, policy_mode, build_success_bonus)
                money, build_success_bonus = _execute_action(action, config, player, money, turn, delayed, max_stamina, rng, stats, build_success_bonus)
            else:
                stats["rests"] += 1
                player.stamina = min(max_stamina, player.stamina + 2)
                event_name = _choose_rest_event(config, players, player_index, money, progress, delayed, turn, max_stamina, rng, policy_mode, build_success_bonus)
                money = _execute_rest_event(event_name, config, player, turn, max_stamina, rng, stats, money)

        progress, money = _execute_build(config, rng, stats, progress, money, reached, build_success_bonus)
        if collect_turn_money:
            turn_end_money.append(money)
        if progress >= len(config.castle_costs):
            stats["cleared"] = True
            stats["clear_turn"] = turn
            break
        start_player_index = 0

    return money, progress, delayed, turn_end_money


def _choose_action(
    config: SimulationConfig,
    actions: list[Action],
    players: list[Player],
    player_index: int,
    money: int,
    progress: int,
    delayed: list[DelayedEvent],
    turn: int,
    max_stamina: int,
    rng: random.Random,
    policy_mode: str,
    current_turn_build_success_bonus: float,
) -> Action:
    if policy_mode != AI_MODE_ROLLOUT or config.rollout_count <= 0:
        return _choose_best_action(actions, money, rng)
    scored = [
        (action, _rollout_action_value(config, action, players, player_index, money, progress, delayed, turn, max_stamina, rng, current_turn_build_success_bonus))
        for action in actions
    ]
    best = max(score for _, score in scored)
    return rng.choice([action for action, score in scored if score == best])


def _choose_best_action(actions: list[Action], money: int, rng: random.Random) -> Action:
    scored = [(action, _expected_action_income(action, money)) for action in actions]
    best = max(score for _, score in scored)
    candidates = [action for action, score in scored if score == best]
    return rng.choice(candidates)


def _rollout_action_value(
    config: SimulationConfig,
    action: Action,
    players: list[Player],
    player_index: int,
    money: int,
    progress: int,
    delayed: list[DelayedEvent],
    turn: int,
    max_stamina: int,
    rng: random.Random,
    current_turn_build_success_bonus: float,
) -> float:
    total = 0.0
    for _ in range(config.rollout_count):
        rollout_rng = random.Random(rng.randrange(2**63))
        rollout_players = _clone_players(players)
        rollout_delayed = _clone_delayed(delayed)
        rollout_stats = _empty_single()
        rollout_player = rollout_players[player_index]
        rollout_player.stamina -= action.stamina_cost
        rollout_money = money
        rollout_build_success_bonus = current_turn_build_success_bonus
        if rollout_rng.random() < action.success_rate:
            income, rollout_money, bonus_delta = _apply_action_success(action, config, rollout_money, turn, rollout_delayed, rollout_player, max_stamina)
            rollout_build_success_bonus += bonus_delta
            rollout_stats["income_total"] += income
            rollout_stats["income_by_source"][action.job] += income
            _record_guard_success_stats(action, bonus_delta, rollout_stats)
        _simulate_from(
            config=config,
            rng=rollout_rng,
            players=rollout_players,
            money=rollout_money,
            progress=progress,
            delayed=rollout_delayed,
            start_turn=turn,
            start_player_index=player_index + 1,
            max_stamina=max_stamina,
            stats=rollout_stats,
            policy_mode=AI_MODE_IMMEDIATE,
            collect_turn_money=False,
            current_turn_build_success_bonus=rollout_build_success_bonus,
        )
        total += rollout_stats["income_total"]
    return total / config.rollout_count


def _expected_action_income(action: Action, money: int) -> float:
    if action.effect_type == "multiplier" and action.multiplier is not None:
        return action.success_rate * max(0, money * action.multiplier - money)
    if action.effect_type == "delayed_investment":
        invested = money // 2
        return action.success_rate * (invested * action.delay_multiplier - invested)
    if action.effect_type == "stamina_recovery":
        return 0.0
    return action.success_rate * action.amount


def _execute_action(action: Action, config: SimulationConfig, player: Player, money: int, turn: int, delayed: list[DelayedEvent], max_stamina: int, rng: random.Random, stats: dict, build_success_bonus: float) -> tuple[int, float]:
    player.stamina -= action.stamina_cost
    key = f"{action.job}:{action.name}"
    stats["action_selected"][key] += 1
    stats[f"{action.tier}_action_count_by_job"][action.job] += 1
    if _is_guard_action(action):
        stats["guard_selected"] += 1
    if rng.random() < action.success_rate:
        stats["action_success"][key] += 1
        income, money, bonus_delta = _apply_action_success(action, config, money, turn, delayed, player, max_stamina)
        build_success_bonus += bonus_delta
        _record_guard_success_stats(action, bonus_delta, stats)
        stats["income_by_job"][action.job] += income
        stats["income_by_source"][action.job] += income
        stats["income_total"] += income
        stats[f"{action.tier}_action_income_by_job"][action.job] += income
    return money, build_success_bonus


def _apply_action_success(action: Action, config: SimulationConfig, money: int, turn: int, delayed: list[DelayedEvent], player: Player, max_stamina: int) -> tuple[int, int, float]:
    bonus_delta = _guard_build_bonus(action, config)
    if action.effect_type == "multiplier" and action.multiplier is not None:
        new_money = int(round(money * action.multiplier))
        return new_money - money, new_money, bonus_delta
    if action.effect_type == "delayed_investment":
        invested = money // 2
        money -= invested
        delayed.append(DelayedEvent(turn + action.delay_turns, int(round(invested * action.delay_multiplier)), action.job))
        return 0, money, bonus_delta
    if action.effect_type == "stamina_recovery":
        player.stamina = min(max_stamina, player.stamina + action.amount)
        return 0, money, bonus_delta
    return action.amount, money + action.amount, bonus_delta


def _choose_rest_event(
    config: SimulationConfig,
    players: list[Player],
    player_index: int,
    money: int,
    progress: int,
    delayed: list[DelayedEvent],
    turn: int,
    max_stamina: int,
    rng: random.Random,
    policy_mode: str,
    current_turn_build_success_bonus: float,
) -> str:
    candidates = _available_rest_events(config, players[player_index], turn)
    if policy_mode != AI_MODE_ROLLOUT or config.rollout_count <= 0:
        values = {event_name: _expected_rest_income(config, event_name) for event_name in candidates}
    else:
        values = {
            event_name: _rollout_rest_value(config, event_name, players, player_index, money, progress, delayed, turn, max_stamina, rng, current_turn_build_success_bonus)
            for event_name in candidates
        }
    best = max(values.values())
    return rng.choice([name for name, value in values.items() if value == best])


def _available_rest_events(config: SimulationConfig, player: Player, turn: int) -> list[str]:
    events = ["lottery", "walk", "sleep"]
    if not player.promoted and turn >= int(config.rest_events["promotion"]["unlock_turn"]):
        events.append("promotion")
    return events


def _expected_rest_income(config: SimulationConfig, event_name: str) -> float:
    rest = config.rest_events
    if event_name == "lottery":
        return float(rest["lottery"]["success_rate"]) * int(rest["lottery"]["amount"])
    if event_name == "walk":
        return float(rest["walk"]["success_rate"]) * int(rest["walk"]["amount"])
    return 0.0


def _rollout_rest_value(
    config: SimulationConfig,
    event_name: str,
    players: list[Player],
    player_index: int,
    money: int,
    progress: int,
    delayed: list[DelayedEvent],
    turn: int,
    max_stamina: int,
    rng: random.Random,
    current_turn_build_success_bonus: float,
) -> float:
    total = 0.0
    for _ in range(config.rollout_count):
        rollout_rng = random.Random(rng.randrange(2**63))
        rollout_players = _clone_players(players)
        rollout_delayed = _clone_delayed(delayed)
        rollout_stats = _empty_single()
        rollout_money = _execute_rest_event(event_name, config, rollout_players[player_index], turn, max_stamina, rollout_rng, rollout_stats, money)
        _simulate_from(
            config=config,
            rng=rollout_rng,
            players=rollout_players,
            money=rollout_money,
            progress=progress,
            delayed=rollout_delayed,
            start_turn=turn,
            start_player_index=player_index + 1,
            max_stamina=max_stamina,
            stats=rollout_stats,
            policy_mode=AI_MODE_IMMEDIATE,
            collect_turn_money=False,
            current_turn_build_success_bonus=current_turn_build_success_bonus,
        )
        total += rollout_stats["income_total"]
    return total / config.rollout_count


def _execute_rest_event(event_name: str, config: SimulationConfig, player: Player, turn: int, max_stamina: int, rng: random.Random, stats: dict, money: int) -> int:
    rest = config.rest_events
    if event_name == "lottery":
        stats["lottery_selected"] += 1
        if rng.random() < float(rest["lottery"]["success_rate"]):
            amount = int(rest["lottery"]["amount"])
            money += amount
            stats["lottery_wins"] += 1
            stats["lottery_income"] += amount
            stats["income_total"] += amount
            stats["income_by_source"][_rest_name(rest, "lottery", "宝くじ")] += amount
    elif event_name == "walk":
        stats["walk_selected"] += 1
        if rng.random() < float(rest["walk"]["success_rate"]):
            amount = int(rest["walk"]["amount"])
            money += amount
            stats["walk_success"] += 1
            stats["walk_income"] += amount
            stats["income_total"] += amount
            stats["income_by_source"][_rest_name(rest, "walk", "謨｣豁ｩ")] += amount
    elif event_name == "sleep":
        stats["sleep_selected"] += 1
        player.stamina = min(max_stamina, player.stamina + int(rest["sleep"]["recovery"]))
    elif event_name == "promotion":
        stats["promotion_attempts"] += 1
        stats["promotion_attempt_jobs"][player.job_name] += 1
        if not player.promoted and rng.random() < float(rest["promotion"]["success_rate"]):
            player.promoted = True
            stats["promotion_success"] += 1
            stats["promotion_success_jobs"][player.job_name] += 1
            stats["promotion_turns_by_job"][player.job_name].append(turn)
            stats["promotion_turns"].append(turn)
    return money


def _execute_build(config: SimulationConfig, rng: random.Random, stats: dict, progress: int, money: int, reached: list[bool] | None, build_success_bonus: float) -> tuple[int, int]:
    if progress < len(config.castle_costs):
        cost = config.castle_costs[progress]
        if money >= cost:
            build_rate = min(1.0, config.build_success_rate + build_success_bonus)
            actual_bonus = build_rate - config.build_success_rate
            stats["build_attempts"] += 1
            if build_success_bonus > 0:
                stats["guard_buffed_build_attempts"] += 1
                stats["guard_build_bonus_rate_uplift_sum"] += actual_bonus
            else:
                stats["unbuffed_build_attempts"] += 1
            if rng.random() < build_rate:
                money -= cost
                progress += 1
                stats["build_successes"] += 1
                if build_success_bonus > 0:
                    stats["guard_buffed_build_successes"] += 1
                else:
                    stats["unbuffed_build_successes"] += 1
                if reached is not None:
                    reached[progress] = True
            else:
                money -= int(round(cost * config.build_failure_loss_rate))
                stats["build_failures"] += 1
                if build_success_bonus > 0:
                    stats["guard_buffed_build_failures"] += 1
                else:
                    stats["unbuffed_build_failures"] += 1
    return progress, money


def _max_stamina(config: SimulationConfig) -> int:
    knight_count = sum(1 for job in config.player_jobs if _is_knight_job_name(job))
    return config.base_max_stamina + knight_count * config.knight_stamina_bonus


def _is_knight_job_name(job_name: str) -> bool:
    knight = "\u9a0e\u58eb"
    return job_name == knight or knight in job_name


def _is_guard_action(action: Action) -> bool:
    return _is_knight_job_name(action.job) and "\u8b77\u885b" in action.name


def _guard_build_bonus(action: Action, config: SimulationConfig) -> float:
    if not _is_guard_action(action):
        return 0.0
    if action.tier == "advanced":
        return config.advanced_guard_build_bonus
    return config.normal_guard_build_bonus


def _record_guard_success_stats(action: Action, bonus_delta: float, stats: dict) -> None:
    if not _is_guard_action(action):
        return
    stats["guard_success"] += 1
    if bonus_delta > 0:
        stats["guard_build_bonus_events"] += 1
        stats["guard_build_bonus_generated_sum"] += bonus_delta


def _clone_players(players: list[Player]) -> list[Player]:
    return [Player(job_name=player.job_name, stamina=player.stamina, promoted=player.promoted) for player in players]


def _clone_delayed(delayed: list[DelayedEvent]) -> list[DelayedEvent]:
    return [DelayedEvent(event.due_turn, event.amount, event.source) for event in delayed]


def _rest_name(rest: dict[str, dict], key: str, fallback: str) -> str:
    return str(rest.get(key, {}).get("name") or fallback)


def _empty_single() -> dict:
    return {
        "cleared": False,
        "clear_turn": None,
        "final_progress": 0,
        "turn_end_money": [],
        "reached": [],
        "build_attempts": 0,
        "build_successes": 0,
        "build_failures": 0,
        "guard_selected": 0,
        "guard_success": 0,
        "guard_build_bonus_events": 0,
        "guard_build_bonus_generated_sum": 0.0,
        "guard_buffed_build_attempts": 0,
        "guard_buffed_build_successes": 0,
        "guard_buffed_build_failures": 0,
        "unbuffed_build_attempts": 0,
        "unbuffed_build_successes": 0,
        "unbuffed_build_failures": 0,
        "guard_build_bonus_rate_uplift_sum": 0.0,
        "action_selected": Counter(),
        "action_success": Counter(),
        "income_by_job": defaultdict(int),
        "income_by_source": defaultdict(int),
        "income_total": 0,
        "rests": 0,
        "lottery_selected": 0,
        "lottery_wins": 0,
        "lottery_income": 0,
        "walk_selected": 0,
        "walk_success": 0,
        "walk_income": 0,
        "sleep_selected": 0,
        "promotion_attempts": 0,
        "promotion_success": 0,
        "promotion_attempt_games": 0,
        "promotion_success_games": 0,
        "normal_action_count_by_job": defaultdict(int),
        "normal_action_income_by_job": defaultdict(int),
        "advanced_action_count_by_job": defaultdict(int),
        "advanced_action_income_by_job": defaultdict(int),
        "promotion_attempt_jobs": Counter(),
        "promotion_success_jobs": Counter(),
        "promotion_attempt_game_jobs": Counter(),
        "promotion_success_game_jobs": Counter(),
        "promotion_turns": [],
        "promotion_turns_by_job": defaultdict(list),
        "promoted_game_income_by_job": defaultdict(int),
        "promoted_game_count_by_job": defaultdict(int),
        "unpromoted_game_income_by_job": defaultdict(int),
        "unpromoted_game_count_by_job": defaultdict(int),
    }


def _empty_aggregate(max_turns: int, stages: int) -> dict:
    data = _empty_single()
    data.update({
        "clear_turns": [],
        "turn_money_sums": [0] * max_turns,
        "progress_sum": 0,
        "reached_counts": [0] * (stages + 1),
        "cleared_count": 0,
    })
    return data


def _merge_result(aggregate: dict, result: dict) -> None:
    if result["cleared"]:
        aggregate["cleared_count"] += 1
        aggregate["clear_turns"].append(result["clear_turn"])
    aggregate["progress_sum"] += result["final_progress"]
    for i, money in enumerate(result["turn_end_money"]):
        aggregate["turn_money_sums"][i] += money
    for i, reached in enumerate(result["reached"]):
        if reached:
            aggregate["reached_counts"][i] += 1
    for key in (
        "build_attempts", "build_successes", "build_failures", "income_total", "rests",
        "guard_selected", "guard_success", "guard_build_bonus_events",
        "guard_build_bonus_generated_sum", "guard_buffed_build_attempts",
        "guard_buffed_build_successes", "guard_buffed_build_failures",
        "unbuffed_build_attempts", "unbuffed_build_successes", "unbuffed_build_failures",
        "guard_build_bonus_rate_uplift_sum",
        "lottery_selected", "lottery_wins", "lottery_income", "walk_selected",
        "walk_success", "walk_income", "sleep_selected", "promotion_attempts", "promotion_success",
        "promotion_attempt_games", "promotion_success_games",
    ):
        aggregate[key] += result[key]
    for key in (
        "action_selected", "action_success", "income_by_job", "income_by_source",
        "normal_action_count_by_job", "normal_action_income_by_job",
        "advanced_action_count_by_job", "advanced_action_income_by_job",
        "promotion_attempt_jobs", "promotion_success_jobs",
        "promotion_attempt_game_jobs", "promotion_success_game_jobs",
        "promoted_game_income_by_job", "promoted_game_count_by_job",
        "unpromoted_game_income_by_job", "unpromoted_game_count_by_job",
    ):
        for subkey, value in result[key].items():
            aggregate[key][subkey] += value
    aggregate["promotion_turns"].extend(result["promotion_turns"])
    for job, turns in result["promotion_turns_by_job"].items():
        aggregate["promotion_turns_by_job"][job].extend(turns)


def _finalize(aggregate: dict, trials: int, max_turns: int) -> dict:
    clear_rate = aggregate["cleared_count"] / trials if trials else 0
    lottery_rate = aggregate["lottery_wins"] / aggregate["lottery_selected"] if aggregate["lottery_selected"] else 0
    lottery_share = aggregate["lottery_income"] / aggregate["income_total"] if aggregate["income_total"] else 0
    promotion_attempt_game_rate = aggregate["promotion_attempt_games"] / trials if trials else 0
    promotion_success_rate = aggregate["promotion_success"] / aggregate["promotion_attempts"] if aggregate["promotion_attempts"] else 0
    guard_buffed_build_success_rate = (
        aggregate["guard_buffed_build_successes"] / aggregate["guard_buffed_build_attempts"]
        if aggregate["guard_buffed_build_attempts"] else 0
    )
    unbuffed_build_success_rate = (
        aggregate["unbuffed_build_successes"] / aggregate["unbuffed_build_attempts"]
        if aggregate["unbuffed_build_attempts"] else 0
    )
    average_guard_build_bonus_rate_uplift = (
        aggregate["guard_build_bonus_rate_uplift_sum"] / aggregate["guard_buffed_build_attempts"]
        if aggregate["guard_buffed_build_attempts"] else 0
    )
    return {
        "clear_rate": clear_rate,
        "fail_rate": 1 - clear_rate,
        "average_clear_turn": mean(aggregate["clear_turns"]) if aggregate["clear_turns"] else None,
        "clear_turn_distribution": dict(Counter(aggregate["clear_turns"])),
        "average_money_by_turn": [value / trials for value in aggregate["turn_money_sums"]],
        "average_final_progress": aggregate["progress_sum"] / trials if trials else 0,
        "stage_reach_rates": {stage: count / trials for stage, count in enumerate(aggregate["reached_counts"])},
        "build_attempts": aggregate["build_attempts"],
        "build_successes": aggregate["build_successes"],
        "build_failures": aggregate["build_failures"],
        "guard_selected": aggregate["guard_selected"],
        "guard_success": aggregate["guard_success"],
        "guard_build_bonus_events": aggregate["guard_build_bonus_events"],
        "guard_buffed_build_attempts": aggregate["guard_buffed_build_attempts"],
        "guard_buffed_build_successes": aggregate["guard_buffed_build_successes"],
        "guard_buffed_build_failures": aggregate["guard_buffed_build_failures"],
        "guard_buffed_build_success_rate": guard_buffed_build_success_rate,
        "unbuffed_build_attempts": aggregate["unbuffed_build_attempts"],
        "unbuffed_build_successes": aggregate["unbuffed_build_successes"],
        "unbuffed_build_failures": aggregate["unbuffed_build_failures"],
        "unbuffed_build_success_rate": unbuffed_build_success_rate,
        "average_guard_build_bonus_rate_uplift": average_guard_build_bonus_rate_uplift,
        "action_selected": dict(aggregate["action_selected"]),
        "action_success": dict(aggregate["action_success"]),
        "income_by_job": dict(aggregate["income_by_job"]),
        "average_income_by_job": {k: v / trials for k, v in aggregate["income_by_job"].items()},
        "average_total_income": aggregate["income_total"] / trials if trials else 0,
        "rests": aggregate["rests"],
        "lottery_selected": aggregate["lottery_selected"],
        "lottery_wins": aggregate["lottery_wins"],
        "lottery_win_rate": lottery_rate,
        "lottery_income": aggregate["lottery_income"],
        "lottery_income_share": lottery_share,
        "walk_selected": aggregate["walk_selected"],
        "walk_success": aggregate["walk_success"],
        "walk_income": aggregate["walk_income"],
        "sleep_selected": aggregate["sleep_selected"],
        "promotion_attempts": aggregate["promotion_attempts"],
        "promotion_success": aggregate["promotion_success"],
        "promotion_attempt_game_rate": promotion_attempt_game_rate,
        "promotion_success_game_rate": promotion_success_rate,
        "average_promotion_turn": mean(aggregate["promotion_turns"]) if aggregate["promotion_turns"] else None,
        "income_by_source": dict(aggregate["income_by_source"]),
        "promotion_by_job": _finalize_promotion_by_job(aggregate, trials),
    }


def _finalize_promotion_by_job(aggregate: dict, trials: int) -> list[dict]:
    jobs = set()
    for key in (
        "normal_action_count_by_job", "advanced_action_count_by_job",
        "promotion_attempt_jobs", "promotion_success_jobs",
        "promoted_game_count_by_job", "unpromoted_game_count_by_job",
    ):
        jobs.update(aggregate[key].keys())

    rows: list[dict] = []
    for job in sorted(jobs):
        normal_count = aggregate["normal_action_count_by_job"].get(job, 0)
        advanced_count = aggregate["advanced_action_count_by_job"].get(job, 0)
        normal_avg = aggregate["normal_action_income_by_job"].get(job, 0) / normal_count if normal_count else 0
        advanced_avg = aggregate["advanced_action_income_by_job"].get(job, 0) / advanced_count if advanced_count else 0
        diff = advanced_avg - normal_avg
        uplift = diff / normal_avg if normal_avg else None
        attempts = aggregate["promotion_attempt_jobs"].get(job, 0)
        successes = aggregate["promotion_success_jobs"].get(job, 0)
        promoted_games = aggregate["promoted_game_count_by_job"].get(job, 0)
        unpromoted_games = aggregate["unpromoted_game_count_by_job"].get(job, 0)
        turns = aggregate["promotion_turns_by_job"].get(job, [])
        rows.append({
            "job": job,
            "normal_average_action_income": normal_avg,
            "advanced_average_action_income": advanced_avg,
            "difference": diff,
            "uplift_rate": uplift,
            "average_promotion_turn": mean(turns) if turns else None,
            "promotion_attempt_rate": aggregate["promotion_attempt_game_jobs"].get(job, 0) / trials if trials else 0,
            "promotion_success_rate": successes / attempts if attempts else 0,
            "promotion_attempts": attempts,
            "promotion_successes": successes,
            "promoted_game_average_total_income": aggregate["promoted_game_income_by_job"].get(job, 0) / promoted_games if promoted_games else None,
            "unpromoted_game_average_total_income": aggregate["unpromoted_game_income_by_job"].get(job, 0) / unpromoted_games if unpromoted_games else None,
        })
    return rows
