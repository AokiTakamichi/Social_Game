from __future__ import annotations

import copy
import json
import math
from dataclasses import fields
from pathlib import Path
from typing import Any

from config import (
    DEFAULT_BUILD_FAILURE_LOSS_RATE,
    DEFAULT_BUILD_SUCCESS_RATE,
    DEFAULT_CASTLE_COSTS,
    DEFAULT_EXCEL_FILENAME,
    DEFAULT_INITIAL_STAMINA,
    DEFAULT_KNIGHT_STAMINA_BONUS,
    DEFAULT_MAX_STAMINA,
    DEFAULT_MAX_TURNS,
    DEFAULT_PLAYER_COUNT,
    DEFAULT_TRIALS,
    DEFAULT_CARD_COUNTS,
    DEFAULT_REST_EVENTS,
    DEFAULT_NORMAL_GUARD_BUILD_BONUS,
    DEFAULT_ADVANCED_GUARD_BUILD_BONUS,
    DEFAULT_NORMAL_CARPENTER_BUILD_DISCOUNT,
    DEFAULT_ADVANCED_CARPENTER_BUILD_DISCOUNT,
    DEFAULT_CARPENTER_BUILD_COST_MULTIPLIER,
    DEFAULT_NORMAL_MERCHANT_TURN_INCOME,
    DEFAULT_ADVANCED_MERCHANT_TURN_INCOME,
    DEFAULT_NORMAL_NEET_TURN_RECOVERY,
    DEFAULT_NORMAL_NEET_PRAY_LOTTERY_MULTIPLIER,
    DEFAULT_ADVANCED_NEET_PRAY_LOTTERY_MULTIPLIER,
)
from data_loader import find_excel_file, load_game_data
from models import Action, Job, SimulationConfig

CONFIG_FILENAME = "simulation_config.json"


class ConfigLoadError(Exception):
    pass


def config_path(base_dir: Path) -> Path:
    return base_dir / CONFIG_FILENAME


def load_config(base_dir: Path) -> tuple[SimulationConfig, str, list[str]]:
    path = config_path(base_dir)
    if path.exists():
        try:
            return load_config_from_json(path), "json", []
        except Exception as error:
            fallback, warnings = load_default_config_from_excel(base_dir)
            warnings.append(f"{CONFIG_FILENAME} could not be loaded: {error}")
            return fallback, "excel_fallback", warnings

    config, warnings = load_default_config_from_excel(base_dir)
    save_config_to_json(config, path)
    return config, "excel_initialized", warnings


def load_config_from_json(path: Path, default_config: SimulationConfig | None = None) -> SimulationConfig:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ConfigLoadError("root must be a JSON object")
    if default_config is None:
        default_config = _base_default_config()
    return dict_to_config(data, default_config)


def save_config_to_json(config: SimulationConfig, path: Path) -> None:
    data = config_to_dict(config)
    _validate_json_value(data)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2, allow_nan=False)
        file.write("\n")


def load_default_config_from_excel(base_dir: Path) -> tuple[SimulationConfig, list[str]]:
    excel_path = find_excel_file(base_dir)
    jobs, rest_events, warnings = load_game_data(excel_path)
    job_names = list(jobs.keys())
    player_jobs = [job_names[idx % len(job_names)] for idx in range(DEFAULT_PLAYER_COUNT)] if job_names else []
    config = SimulationConfig(
        trials=DEFAULT_TRIALS,
        max_turns=DEFAULT_MAX_TURNS,
        player_jobs=player_jobs,
        castle_costs=list(DEFAULT_CASTLE_COSTS),
        build_success_rate=DEFAULT_BUILD_SUCCESS_RATE,
        build_failure_loss_rate=DEFAULT_BUILD_FAILURE_LOSS_RATE,
        initial_stamina=DEFAULT_INITIAL_STAMINA,
        base_max_stamina=DEFAULT_MAX_STAMINA,
        knight_stamina_bonus=DEFAULT_KNIGHT_STAMINA_BONUS,
        rest_events=copy.deepcopy(rest_events),
        jobs=copy.deepcopy(jobs),
        seed=None,
        initial_hand_size=2,
        mulligan_enabled=True,
        card_counts=dict(DEFAULT_CARD_COUNTS),
        action_ai_mode="rollout",
        rollout_count=100,
        normal_guard_build_bonus=DEFAULT_NORMAL_GUARD_BUILD_BONUS,
        advanced_guard_build_bonus=DEFAULT_ADVANCED_GUARD_BUILD_BONUS,
        normal_carpenter_build_discount=DEFAULT_NORMAL_CARPENTER_BUILD_DISCOUNT,
        advanced_carpenter_build_discount=DEFAULT_ADVANCED_CARPENTER_BUILD_DISCOUNT,
        carpenter_build_cost_multiplier=DEFAULT_CARPENTER_BUILD_COST_MULTIPLIER,
        normal_merchant_turn_income=DEFAULT_NORMAL_MERCHANT_TURN_INCOME,
        advanced_merchant_turn_income=DEFAULT_ADVANCED_MERCHANT_TURN_INCOME,
        normal_neet_turn_recovery=DEFAULT_NORMAL_NEET_TURN_RECOVERY,
        normal_neet_pray_lottery_multiplier=DEFAULT_NORMAL_NEET_PRAY_LOTTERY_MULTIPLIER,
        advanced_neet_pray_lottery_multiplier=DEFAULT_ADVANCED_NEET_PRAY_LOTTERY_MULTIPLIER,
    )
    return config, warnings


def _base_default_config() -> SimulationConfig:
    return SimulationConfig(
        trials=DEFAULT_TRIALS,
        max_turns=DEFAULT_MAX_TURNS,
        player_jobs=[],
        castle_costs=list(DEFAULT_CASTLE_COSTS),
        build_success_rate=DEFAULT_BUILD_SUCCESS_RATE,
        build_failure_loss_rate=DEFAULT_BUILD_FAILURE_LOSS_RATE,
        initial_stamina=DEFAULT_INITIAL_STAMINA,
        base_max_stamina=DEFAULT_MAX_STAMINA,
        knight_stamina_bonus=DEFAULT_KNIGHT_STAMINA_BONUS,
        rest_events=copy.deepcopy(DEFAULT_REST_EVENTS),
        jobs={},
        seed=None,
        initial_hand_size=2,
        mulligan_enabled=True,
        card_counts=dict(DEFAULT_CARD_COUNTS),
        action_ai_mode="rollout",
        rollout_count=100,
        normal_guard_build_bonus=DEFAULT_NORMAL_GUARD_BUILD_BONUS,
        advanced_guard_build_bonus=DEFAULT_ADVANCED_GUARD_BUILD_BONUS,
        normal_carpenter_build_discount=DEFAULT_NORMAL_CARPENTER_BUILD_DISCOUNT,
        advanced_carpenter_build_discount=DEFAULT_ADVANCED_CARPENTER_BUILD_DISCOUNT,
        carpenter_build_cost_multiplier=DEFAULT_CARPENTER_BUILD_COST_MULTIPLIER,
        normal_merchant_turn_income=DEFAULT_NORMAL_MERCHANT_TURN_INCOME,
        advanced_merchant_turn_income=DEFAULT_ADVANCED_MERCHANT_TURN_INCOME,
        normal_neet_turn_recovery=DEFAULT_NORMAL_NEET_TURN_RECOVERY,
        normal_neet_pray_lottery_multiplier=DEFAULT_NORMAL_NEET_PRAY_LOTTERY_MULTIPLIER,
        advanced_neet_pray_lottery_multiplier=DEFAULT_ADVANCED_NEET_PRAY_LOTTERY_MULTIPLIER,
    )


def config_to_dict(config: SimulationConfig) -> dict[str, Any]:
    return {
        "game": {
            "trials": config.trials,
            "max_turns": config.max_turns,
            "player_jobs": list(config.player_jobs),
            "initial_stamina": config.initial_stamina,
            "base_max_stamina": config.base_max_stamina,
            "knight_stamina_bonus": config.knight_stamina_bonus,
            "seed": config.seed,
        },
        "castle": {
            "costs": list(config.castle_costs),
            "base_build_success_rate": config.build_success_rate,
            "build_failure_loss_rate": config.build_failure_loss_rate,
            "normal_guard_build_bonus": config.normal_guard_build_bonus,
            "advanced_guard_build_bonus": config.advanced_guard_build_bonus,
        },
        "rest": copy.deepcopy(config.rest_events),
        "cards": {
            "initial_hand_size": config.initial_hand_size,
            "mulligan_enabled": config.mulligan_enabled,
            "counts": dict(config.card_counts),
        },
        "jobs": {name: _job_to_dict(job) for name, job in config.jobs.items()},
        "passives": {
            "normal_carpenter_build_discount": config.normal_carpenter_build_discount,
            "advanced_carpenter_build_discount": config.advanced_carpenter_build_discount,
            "carpenter_build_cost_multiplier": config.carpenter_build_cost_multiplier,
            "normal_merchant_turn_income": config.normal_merchant_turn_income,
            "advanced_merchant_turn_income": config.advanced_merchant_turn_income,
            "normal_neet_turn_recovery": config.normal_neet_turn_recovery,
            "normal_neet_pray_lottery_multiplier": config.normal_neet_pray_lottery_multiplier,
            "advanced_neet_pray_lottery_multiplier": config.advanced_neet_pray_lottery_multiplier,
        },
        "ai": {
            "action_ai_mode": config.action_ai_mode,
            "rollout_count": config.rollout_count,
        },
    }


def dict_to_config(data: dict[str, Any], default_config: SimulationConfig) -> SimulationConfig:
    values = _config_values(default_config)
    game = _section(data, "game")
    castle = _section(data, "castle")
    cards = _section(data, "cards")
    passives = _section(data, "passives")
    ai = _section(data, "ai")

    values["trials"] = _as_int(game.get("trials"), values["trials"])
    values["max_turns"] = _as_int(game.get("max_turns"), values["max_turns"])
    values["player_jobs"] = _as_str_list(game.get("player_jobs"), values["player_jobs"])
    values["initial_stamina"] = _as_int(game.get("initial_stamina"), values["initial_stamina"])
    values["base_max_stamina"] = _as_int(game.get("base_max_stamina"), values["base_max_stamina"])
    values["knight_stamina_bonus"] = _as_int(game.get("knight_stamina_bonus"), values["knight_stamina_bonus"])
    values["seed"] = _as_optional_int(game.get("seed"), values["seed"])

    values["castle_costs"] = _as_int_list(castle.get("costs"), values["castle_costs"])
    values["build_success_rate"] = _as_float(castle.get("base_build_success_rate"), values["build_success_rate"])
    values["build_failure_loss_rate"] = _as_float(castle.get("build_failure_loss_rate"), values["build_failure_loss_rate"])
    values["normal_guard_build_bonus"] = _as_float(castle.get("normal_guard_build_bonus"), values["normal_guard_build_bonus"])
    values["advanced_guard_build_bonus"] = _as_float(castle.get("advanced_guard_build_bonus"), values["advanced_guard_build_bonus"])

    rest = data.get("rest")
    if isinstance(rest, dict):
        values["rest_events"] = _merge_known_dict(values["rest_events"], rest)

    values["initial_hand_size"] = _as_int(cards.get("initial_hand_size"), values["initial_hand_size"])
    values["mulligan_enabled"] = _as_bool(cards.get("mulligan_enabled"), values["mulligan_enabled"])
    if isinstance(cards.get("counts"), dict):
        values["card_counts"] = _merge_known_dict(values["card_counts"], cards["counts"])

    values["normal_carpenter_build_discount"] = _as_int(passives.get("normal_carpenter_build_discount"), values["normal_carpenter_build_discount"])
    values["advanced_carpenter_build_discount"] = _as_int(passives.get("advanced_carpenter_build_discount"), values["advanced_carpenter_build_discount"])
    values["carpenter_build_cost_multiplier"] = _as_float(passives.get("carpenter_build_cost_multiplier"), values["carpenter_build_cost_multiplier"])
    values["normal_merchant_turn_income"] = _as_int(passives.get("normal_merchant_turn_income"), values["normal_merchant_turn_income"])
    values["advanced_merchant_turn_income"] = _as_int(passives.get("advanced_merchant_turn_income"), values["advanced_merchant_turn_income"])
    values["normal_neet_turn_recovery"] = _as_int(passives.get("normal_neet_turn_recovery"), values["normal_neet_turn_recovery"])
    values["normal_neet_pray_lottery_multiplier"] = _as_float(passives.get("normal_neet_pray_lottery_multiplier"), values["normal_neet_pray_lottery_multiplier"])
    values["advanced_neet_pray_lottery_multiplier"] = _as_float(passives.get("advanced_neet_pray_lottery_multiplier"), values["advanced_neet_pray_lottery_multiplier"])

    values["action_ai_mode"] = str(ai.get("action_ai_mode") or values["action_ai_mode"])
    values["rollout_count"] = _as_int(ai.get("rollout_count"), values["rollout_count"])

    jobs = data.get("jobs")
    if isinstance(jobs, dict):
        values["jobs"] = _dict_to_jobs(jobs, values["jobs"])

    _validate_required(values)
    return SimulationConfig(**values)


def _config_values(config: SimulationConfig) -> dict[str, Any]:
    result = {field.name: copy.deepcopy(getattr(config, field.name)) for field in fields(SimulationConfig)}
    if not result["card_counts"]:
        result["card_counts"] = dict(DEFAULT_CARD_COUNTS)
    return result


def _job_to_dict(job: Job) -> dict[str, Any]:
    return {
        "name": job.name,
        "passive": copy.deepcopy(job.passive),
        "normal_actions": [_action_to_dict(action) for action in job.normal_actions],
        "advanced_actions": [_action_to_dict(action) for action in job.advanced_actions],
    }


def _action_to_dict(action: Action) -> dict[str, Any]:
    return {
        "job": action.job,
        "name": action.name,
        "tier": action.tier,
        "success_rate": action.success_rate,
        "stamina_cost": action.stamina_cost,
        "amount": action.amount,
        "multiplier": action.multiplier,
        "effect_type": action.effect_type,
        "delay_turns": action.delay_turns,
        "delay_multiplier": action.delay_multiplier,
        "raw_effect": action.raw_effect,
        "notes": action.notes,
    }


def _dict_to_jobs(data: dict[str, Any], defaults: dict[str, Job]) -> dict[str, Job]:
    result = copy.deepcopy(defaults)
    for job_name, raw_job in data.items():
        if not isinstance(raw_job, dict):
            continue
        default_job = result.get(job_name, Job(name=job_name))
        normal = raw_job.get("normal_actions")
        advanced = raw_job.get("advanced_actions")
        result[job_name] = Job(
            name=str(raw_job.get("name") or job_name),
            normal_actions=_dict_to_actions(normal, job_name, "normal", default_job.normal_actions),
            advanced_actions=_dict_to_actions(advanced, job_name, "advanced", default_job.advanced_actions),
            passive=raw_job.get("passive") if isinstance(raw_job.get("passive"), dict) else copy.deepcopy(default_job.passive),
        )
    return result


def _dict_to_actions(data: Any, job_name: str, tier: str, defaults: list[Action]) -> list[Action]:
    if not isinstance(data, list):
        return copy.deepcopy(defaults)
    actions: list[Action] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        actions.append(
            Action(
                job=str(item.get("job") or job_name),
                name=name,
                tier=str(item.get("tier") or tier),
                success_rate=_as_float(item.get("success_rate"), 0.0),
                stamina_cost=_as_int(item.get("stamina_cost"), 0),
                amount=_as_int(item.get("amount"), 0),
                multiplier=_as_optional_float(item.get("multiplier"), None),
                effect_type=str(item.get("effect_type") or "income"),
                delay_turns=_as_int(item.get("delay_turns"), 0),
                delay_multiplier=_as_float(item.get("delay_multiplier"), 1.0),
                raw_effect=str(item.get("raw_effect") or ""),
                notes=str(item.get("notes") or ""),
            )
        )
    return actions


def _section(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key)
    return value if isinstance(value, dict) else {}


def _merge_known_dict(default: dict, updates: dict) -> dict:
    result = copy.deepcopy(default)
    for key, value in updates.items():
        if key not in result:
            continue
        if isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _merge_known_dict(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _validate_required(values: dict[str, Any]) -> None:
    if not values["player_jobs"]:
        raise ConfigLoadError("game.player_jobs must not be empty")
    if not values["castle_costs"]:
        raise ConfigLoadError("castle.costs must not be empty")
    if not values["jobs"]:
        raise ConfigLoadError("jobs must not be empty")


def _validate_json_value(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("JSON config cannot contain NaN or Infinity")
    if isinstance(value, dict):
        for child in value.values():
            _validate_json_value(child)
    elif isinstance(value, list):
        for child in value:
            _validate_json_value(child)


def _as_bool(value: Any, default: bool) -> bool:
    return value if isinstance(value, bool) else default


def _as_int(value: Any, default: int) -> int:
    if isinstance(value, bool) or value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_optional_int(value: Any, default: int | None) -> int | None:
    if value is None:
        return None
    return _as_int(value, default if default is not None else 0)


def _as_float(value: Any, default: float) -> float:
    if isinstance(value, bool) or value is None:
        return default
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def _as_optional_float(value: Any, default: float | None) -> float | None:
    if value is None:
        return None
    return _as_float(value, default if default is not None else 0.0)


def _as_int_list(value: Any, default: list[int]) -> list[int]:
    if not isinstance(value, list):
        return copy.deepcopy(default)
    return [_as_int(item, 0) for item in value]


def _as_str_list(value: Any, default: list[str]) -> list[str]:
    if not isinstance(value, list):
        return copy.deepcopy(default)
    result = [str(item) for item in value if str(item)]
    return result or copy.deepcopy(default)
