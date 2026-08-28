from __future__ import annotations

DEFAULT_EXCEL_FILENAME = "Team2_確率 (1).xlsx"

DEFAULT_TRIALS = 10_000
DEFAULT_MAX_TURNS = 15
DEFAULT_CASTLE_COSTS = [100_000, 200_000, 300_000, 400_000, 500_000]
DEFAULT_BUILD_SUCCESS_RATE = 0.5
DEFAULT_BUILD_FAILURE_LOSS_RATE = 0.5

DEFAULT_INITIAL_STAMINA = 10
DEFAULT_MAX_STAMINA = 10
DEFAULT_KNIGHT_STAMINA_BONUS = 1

DEFAULT_PLAYER_COUNT = 4

DEFAULT_REST_EVENTS = {
    "lottery": {"name": "宝くじ", "success_rate": 1 / 6, "amount": 300_000},
    "walk": {"name": "散歩", "success_rate": 0.5, "amount": 10_000},
    "sleep": {"name": "ドカ寝", "recovery": 2},
    "promotion": {"name": "昇格", "unlock_turn": 6, "success_rate": 2 / 6},
}
