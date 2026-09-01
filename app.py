from __future__ import annotations

from pathlib import Path
import time

import pandas as pd
import streamlit as st

from config import CARD_LABELS, DEFAULT_CARD_COUNTS
from config_io import (
    CONFIG_FILENAME,
    config_path,
    load_config,
    load_config_from_json,
    load_default_config_from_excel,
    save_config_to_json,
)
from models import Action, Job, SimulationConfig
from simulation import run_ai_mode_comparison, run_monte_carlo, run_promotion_rate_comparison


st.set_page_config(page_title="城建築モンテカルロシミュレーター", layout="wide")


def main() -> None:
    st.title("城建築モンテカルロシミュレーター")

    base_dir = Path(__file__).parent
    if "config_version" not in st.session_state:
        st.session_state["config_version"] = 0
    if "active_config" not in st.session_state:
        try:
            config, source, warnings = load_config(base_dir)
        except FileNotFoundError as error:
            st.error(str(error))
            st.stop()
        st.session_state["active_config"] = config
        st.session_state["config_source"] = source
        st.session_state["config_warnings"] = warnings

    current_config: SimulationConfig = st.session_state["active_config"]
    config_file = config_path(base_dir)
    render_config_file_controls(base_dir, config_file)

    source_label = {
        "json": "JSON",
        "excel_initialized": "Excel -> JSON initialized",
        "excel_fallback": "Excel fallback",
        "excel_default": "Excel default",
    }.get(st.session_state.get("config_source"), "unknown")
    st.caption(f"設定: {CONFIG_FILENAME} / 読み込み元: {source_label}")

    warnings = st.session_state.get("config_warnings", [])
    with st.expander("設定読み込み結果 / 注意点", expanded=bool(warnings)):
        st.write("職業:", ", ".join(current_config.jobs.keys()) or "なし")
        if warnings:
            for warning in warnings:
                st.warning(warning)
        else:
            st.success("警告はありません。")

    sim_settings = render_simulation_settings(current_config)
    castle_settings = render_castle_settings(current_config)
    stamina_settings = render_stamina_settings(current_config)
    passive_settings = render_passive_settings(current_config)
    edited_jobs = render_job_settings(current_config.jobs)
    edited_rest_events = render_rest_settings(current_config.rest_events)
    card_settings = render_card_settings(current_config)
    edited_config = build_config_from_settings(
        sim_settings,
        castle_settings,
        stamina_settings,
        passive_settings,
        edited_jobs,
        edited_rest_events,
        card_settings,
    )
    st.session_state["active_config"] = edited_config

    with st.sidebar:
        if st.button("設定を保存"):
            save_config_to_json(edited_config, config_file)
            st.success(f"{CONFIG_FILENAME} に保存しました")

    if st.button("シミュレーション実行", type="primary"):
        with st.spinner("シミュレーション中..."):
            result = run_monte_carlo(edited_config)
        st.session_state["last_result"] = result
        st.session_state["last_config"] = edited_config

    if "last_result" in st.session_state and "last_config" in st.session_state:
        render_results(st.session_state["last_result"])
        render_ai_mode_comparison(st.session_state["last_config"])
        render_promotion_comparison(st.session_state["last_config"])


def render_config_file_controls(base_dir: Path, config_file: Path) -> None:
    with st.sidebar:
        st.subheader("現在の設定ファイル")
        st.code(CONFIG_FILENAME)
        if st.button("設定を再読み込み"):
            try:
                default_config, warnings = load_default_config_from_excel(base_dir)
                st.session_state["active_config"] = load_config_from_json(config_file, default_config)
                st.session_state["config_source"] = "json"
                st.session_state["config_warnings"] = warnings
                st.session_state["config_version"] += 1
                st.rerun()
            except Exception as error:
                fallback, warnings = load_default_config_from_excel(base_dir)
                warnings.append(f"{CONFIG_FILENAME} could not be loaded: {error}")
                st.session_state["active_config"] = fallback
                st.session_state["config_source"] = "excel_fallback"
                st.session_state["config_warnings"] = warnings
                st.session_state["config_version"] += 1
                st.error(f"{CONFIG_FILENAME} の読み込みに失敗したため、Excel の初期値を表示しました。")
                st.rerun()
        if st.button("デフォルトに戻す"):
            try:
                default_config, warnings = load_default_config_from_excel(base_dir)
            except FileNotFoundError as error:
                st.error(str(error))
                return
            st.session_state["active_config"] = default_config
            st.session_state["config_source"] = "excel_default"
            st.session_state["config_warnings"] = warnings
            st.session_state["config_version"] += 1
            st.info("Excel の初期値を UI に反映しました。保存するまで JSON は変更されません。")
            st.rerun()


def build_config_from_settings(
    sim_settings: dict,
    castle_settings: dict,
    stamina_settings: dict,
    passive_settings: dict,
    edited_jobs: dict[str, Job],
    edited_rest_events: dict[str, dict],
    card_settings: dict,
) -> SimulationConfig:
    return SimulationConfig(
        trials=sim_settings["trials"],
        max_turns=sim_settings["max_turns"],
        player_jobs=sim_settings["player_jobs"],
        castle_costs=castle_settings["costs"],
        build_success_rate=castle_settings["success_rate"],
        build_failure_loss_rate=castle_settings["failure_loss_rate"],
        normal_guard_build_bonus=castle_settings["normal_guard_build_bonus"],
        advanced_guard_build_bonus=castle_settings["advanced_guard_build_bonus"],
        normal_carpenter_build_discount=passive_settings["normal_carpenter_build_discount"],
        advanced_carpenter_build_discount=passive_settings["advanced_carpenter_build_discount"],
        carpenter_build_cost_multiplier=passive_settings["carpenter_build_cost_multiplier"],
        normal_merchant_turn_income=passive_settings["normal_merchant_turn_income"],
        advanced_merchant_turn_income=passive_settings["advanced_merchant_turn_income"],
        normal_neet_turn_recovery=passive_settings["normal_neet_turn_recovery"],
        normal_neet_pray_lottery_multiplier=passive_settings["normal_neet_pray_lottery_multiplier"],
        advanced_neet_pray_lottery_multiplier=passive_settings["advanced_neet_pray_lottery_multiplier"],
        initial_stamina=stamina_settings["initial"],
        base_max_stamina=stamina_settings["maximum"],
        knight_stamina_bonus=stamina_settings["knight_bonus"],
        rest_events=edited_rest_events,
        jobs=edited_jobs,
        seed=sim_settings["seed"],
        initial_hand_size=card_settings["initial_hand_size"],
        mulligan_enabled=card_settings["mulligan_enabled"],
        card_counts=card_settings["card_counts"],
        action_ai_mode=sim_settings["action_ai_mode"],
        rollout_count=sim_settings["rollout_count"],
    )


def widget_key(name: str) -> str:
    return f"{name}_{st.session_state['config_version']}"


def render_simulation_settings(config: SimulationConfig) -> dict:
    st.header("1. シミュレーション設定")
    col1, col2, col3, col4 = st.columns(4)
    trials = col1.number_input("試行回数", min_value=1, max_value=200_000, value=int(config.trials), step=1_000, key=widget_key("trials"))
    max_turns = col2.number_input("最大ターン", min_value=1, max_value=100, value=int(config.max_turns), step=1, key=widget_key("max_turns"))
    player_count = col3.number_input("プレイヤー人数", min_value=1, max_value=20, value=max(1, len(config.player_jobs)), step=1, key=widget_key("player_count"))
    seed_text = col4.text_input("乱数シード（空ならランダム）", value="" if config.seed is None else str(config.seed), key=widget_key("seed"))
    seed = int(seed_text) if seed_text.strip().lstrip("-").isdigit() else None

    job_names = list(jobs.keys())
    if not job_names:
        st.error("職業データがありません。")
        st.stop()

    st.subheader("プレイヤー職業")
    player_jobs = []
    cols = st.columns(min(int(player_count), 6))
    for idx in range(int(player_count)):
        default_job = config.player_jobs[idx] if idx < len(config.player_jobs) and config.player_jobs[idx] in job_names else job_names[idx % len(job_names)]
        with cols[idx % len(cols)]:
            player_jobs.append(st.selectbox(f"Player {idx + 1}", job_names, index=job_names.index(default_job), key=widget_key(f"player_{idx}")))

    st.subheader("行動AI")
    ai_label = st.radio(
        "評価方法",
        ["残りターン期待総収入最大化", "即時期待値最大化", "城完成率最大化"],
        index={"rollout": 0, "immediate": 1, "completion": 2}.get(config.action_ai_mode, 0),
        horizontal=True,
        key=widget_key("action_ai_mode"),
    )
    rollout_options = [10, 50, 100, 500]
    rollout_index = rollout_options.index(config.rollout_count) if config.rollout_count in rollout_options else 2
    rollout_count = st.selectbox("Rollout回数", rollout_options, index=rollout_index, key=widget_key("rollout_count"))
    st.caption("Rollout回数を増やすと精度は上がりますが、処理時間も増加します。内部rolloutでは即時期待値ポリシーを使い、rolloutの再帰は行いません。")
    action_ai_mode = {
        "即時期待値最大化": "immediate",
        "残りターン期待総収入最大化": "rollout",
        "城完成率最大化": "completion",
    }[ai_label]

    return {
        "trials": int(trials),
        "max_turns": int(max_turns),
        "player_jobs": player_jobs,
        "seed": seed,
        "action_ai_mode": action_ai_mode,
        "rollout_count": int(rollout_count),
    }


def render_castle_settings(config: SimulationConfig) -> dict:
    st.header("2. 城設定")
    cols = st.columns(5)
    costs_source = list(config.castle_costs) or [0]
    costs = [
        int(cols[i].number_input(f"第{i + 1}段階 建築費", min_value=0, value=int(costs_source[i] if i < len(costs_source) else costs_source[-1]), step=10_000, key=widget_key(f"castle_cost_{i}")))
        for i in range(5)
    ]
    col1, col2 = st.columns(2)
    success_rate = col1.number_input("建築成功率", min_value=0.0, max_value=1.0, value=float(config.build_success_rate), step=0.01, format="%.4f", key=widget_key("build_success_rate"))
    failure_loss_rate = col2.number_input("失敗時損失割合", min_value=0.0, max_value=1.0, value=float(config.build_failure_loss_rate), step=0.01, format="%.4f", key=widget_key("build_failure_loss_rate"))
    col3, col4 = st.columns(2)
    normal_guard_text = col3.text_input("通常騎士 護衛成功時 建築成功率バフ", value=str(config.normal_guard_build_bonus), key=widget_key("normal_guard_build_bonus"))
    advanced_guard_text = col4.text_input("騎士団長 護衛成功時 建築成功率バフ", value=str(config.advanced_guard_build_bonus), key=widget_key("advanced_guard_build_bonus"))
    normal_guard_build_bonus = parse_rate(normal_guard_text, config.normal_guard_build_bonus)
    advanced_guard_build_bonus = parse_rate(advanced_guard_text, config.advanced_guard_build_bonus)
    if not 0 <= normal_guard_build_bonus <= 1:
        st.warning("通常騎士の護衛バフは0から1の範囲で入力してください。デフォルト値を使用します。")
        normal_guard_build_bonus = config.normal_guard_build_bonus
    if not 0 <= advanced_guard_build_bonus <= 1:
        st.warning("騎士団長の護衛バフは0から1の範囲で入力してください。デフォルト値を使用します。")
        advanced_guard_build_bonus = config.advanced_guard_build_bonus
    return {
        "costs": costs,
        "success_rate": float(success_rate),
        "failure_loss_rate": float(failure_loss_rate),
        "normal_guard_build_bonus": normal_guard_build_bonus,
        "advanced_guard_build_bonus": advanced_guard_build_bonus,
    }


def render_stamina_settings(config: SimulationConfig) -> dict:
    st.header("3. 体力設定")
    col1, col2, col3 = st.columns(3)
    initial = col1.number_input("基本初期体力", min_value=1, value=int(config.initial_stamina), step=1, key=widget_key("initial_stamina"))
    maximum = col2.number_input("基本最大体力", min_value=1, value=int(config.base_max_stamina), step=1, key=widget_key("base_max_stamina"))
    knight_bonus = col3.number_input("騎士1人あたり最大体力ボーナス", min_value=0, value=int(config.knight_stamina_bonus), step=1, key=widget_key("knight_stamina_bonus"))
    return {"initial": int(initial), "maximum": int(maximum), "knight_bonus": int(knight_bonus)}


def render_passive_settings(config: SimulationConfig) -> dict:
    st.header("4. パッシブ設定")
    col1, col2, col3 = st.columns(3)
    normal_carpenter = col1.number_input("通常大工 パッシブ建築費減額", min_value=0, value=int(config.normal_carpenter_build_discount), step=10_000, key=widget_key("normal_carpenter_build_discount"))
    advanced_carpenter = col2.number_input("上級大工 パッシブ建築費減額", min_value=0, value=int(config.advanced_carpenter_build_discount), step=10_000, key=widget_key("advanced_carpenter_build_discount"))
    carpenter_multiplier = col3.number_input("大工 建築費半減行動の倍率", min_value=0.0, max_value=1.0, value=float(config.carpenter_build_cost_multiplier), step=0.05, format="%.4f", key=widget_key("carpenter_build_cost_multiplier"))

    col4, col5, col6 = st.columns(3)
    normal_merchant = col4.number_input("通常商人 ターン開始収入", min_value=0, value=int(config.normal_merchant_turn_income), step=1_000, key=widget_key("normal_merchant_turn_income"))
    advanced_merchant = col5.number_input("上級商人 ターン開始収入", min_value=0, value=int(config.advanced_merchant_turn_income), step=1_000, key=widget_key("advanced_merchant_turn_income"))
    normal_neet = col6.number_input("通常ニート ターン開始回復", min_value=0, value=int(config.normal_neet_turn_recovery), step=1, key=widget_key("normal_neet_turn_recovery"))

    col7, col8 = st.columns(2)
    normal_neet_pray_lottery_multiplier = col7.number_input(
        "通常ニート 神に祈る成功時 宝くじ確率倍率",
        min_value=1.0,
        value=float(config.normal_neet_pray_lottery_multiplier),
        step=0.1,
        format="%.2f",
        key=widget_key("normal_neet_pray_lottery_multiplier"),
    )
    advanced_neet_pray_lottery_multiplier = col8.number_input(
        "上級ニート 神に祈る成功時 宝くじ確率倍率",
        min_value=1.0,
        value=float(config.advanced_neet_pray_lottery_multiplier),
        step=0.1,
        format="%.2f",
        key=widget_key("advanced_neet_pray_lottery_multiplier"),
    )

    return {
        "normal_carpenter_build_discount": int(normal_carpenter),
        "advanced_carpenter_build_discount": int(advanced_carpenter),
        "carpenter_build_cost_multiplier": float(carpenter_multiplier),
        "normal_merchant_turn_income": int(normal_merchant),
        "advanced_merchant_turn_income": int(advanced_merchant),
        "normal_neet_turn_recovery": int(normal_neet),
        "normal_neet_pray_lottery_multiplier": float(normal_neet_pray_lottery_multiplier),
        "advanced_neet_pray_lottery_multiplier": float(advanced_neet_pray_lottery_multiplier),
    }


def render_job_settings(jobs: dict[str, Job]) -> dict[str, Job]:
    st.header("5. 職業設定")
    edited_jobs: dict[str, Job] = {}
    for job_name, job in jobs.items():
        with st.expander(job_name, expanded=False):
            normal_df = actions_to_df(job.normal_actions)
            advanced_df = actions_to_df(job.advanced_actions)
            st.markdown("通常行動")
            edited_normal = st.data_editor(normal_df, num_rows="dynamic", key=widget_key(f"{job_name}_normal"))
            st.markdown("上級行動")
            edited_advanced = st.data_editor(advanced_df, num_rows="dynamic", key=widget_key(f"{job_name}_advanced"))
            edited_jobs[job_name] = Job(
                name=job_name,
                normal_actions=df_to_actions(job_name, "normal", edited_normal),
                advanced_actions=df_to_actions(job_name, "advanced", edited_advanced),
                passive=job.passive,
            )
    return edited_jobs


def actions_to_df(actions: list[Action]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "行動名": action.name,
                "成功確率": action.success_rate,
                "消費体力": action.stamina_cost,
                "獲得金額": action.amount,
                "倍率": action.multiplier or 0.0,
                "効果タイプ": action.effect_type,
                "遅延ターン": action.delay_turns,
                "遅延倍率": action.delay_multiplier,
                "元効果": action.raw_effect,
            }
            for action in actions
        ]
    )


def df_to_actions(job_name: str, tier: str, df: pd.DataFrame) -> list[Action]:
    actions: list[Action] = []
    for _, row in df.fillna("").iterrows():
        name = str(row.get("行動名", "")).strip()
        if not name:
            continue
        multiplier = float(row.get("倍率", 0) or 0)
        actions.append(
            Action(
                job=job_name,
                name=name,
                tier=tier,
                success_rate=float(row.get("成功確率", 0) or 0),
                stamina_cost=int(row.get("消費体力", 0) or 0),
                amount=int(row.get("獲得金額", 0) or 0),
                multiplier=multiplier if multiplier > 0 else None,
                effect_type=str(row.get("効果タイプ", "income") or "income"),
                delay_turns=int(row.get("遅延ターン", 0) or 0),
                delay_multiplier=float(row.get("遅延倍率", 1) or 1),
                raw_effect=str(row.get("元効果", "") or ""),
            )
        )
    return actions


def render_rest_settings(rest_events: dict[str, dict]) -> dict[str, dict]:
    st.header("6. 休みイベント設定")
    col1, col2 = st.columns(2)
    lottery_rate = col1.number_input("宝くじ 成功確率", min_value=0.0, max_value=1.0, value=float(rest_events["lottery"]["success_rate"]), step=0.01, format="%.4f", key=widget_key("lottery_success_rate"))
    lottery_amount = col2.number_input("宝くじ 当選額", min_value=0, value=int(rest_events["lottery"]["amount"]), step=10_000, key=widget_key("lottery_amount"))
    col3, col4 = st.columns(2)
    walk_rate = col3.number_input("散歩 成功確率", min_value=0.0, max_value=1.0, value=float(rest_events["walk"]["success_rate"]), step=0.01, format="%.4f", key=widget_key("walk_success_rate"))
    walk_amount = col4.number_input("散歩 獲得額", min_value=0, value=int(rest_events["walk"]["amount"]), step=1_000, key=widget_key("walk_amount"))
    col5, col6, col7 = st.columns(3)
    sleep_recovery = col5.number_input("ドカ寝 追加回復量", min_value=0, value=int(rest_events["sleep"]["recovery"]), step=1, key=widget_key("sleep_recovery"))
    promotion_turn = col6.number_input("昇格 解禁ターン", min_value=1, value=int(rest_events["promotion"]["unlock_turn"]), step=1, key=widget_key("promotion_unlock_turn"))
    promotion_rate = col7.number_input("昇格 成功率", min_value=0.0, max_value=1.0, value=float(rest_events["promotion"]["success_rate"]), step=0.01, format="%.4f", key=widget_key("promotion_success_rate"))
    return {
        "lottery": {"name": "宝くじ", "success_rate": float(lottery_rate), "amount": int(lottery_amount)},
        "walk": {"name": "散歩", "success_rate": float(walk_rate), "amount": int(walk_amount)},
        "sleep": {"name": "ドカ寝", "recovery": int(sleep_recovery)},
        "promotion": {"name": "昇格", "unlock_turn": int(promotion_turn), "success_rate": float(promotion_rate)},
    }


def render_card_settings(config: SimulationConfig) -> dict:
    st.header("7. カード設定")
    col1, col2, col3 = st.columns(3)
    initial_hand_size = col1.number_input("初期手札枚数", min_value=0, max_value=10, value=int(config.initial_hand_size), step=1, key=widget_key("initial_hand_size"))
    mulligan_enabled = col2.checkbox("マリガン有効", value=bool(config.mulligan_enabled), key=widget_key("mulligan_enabled"))
    counts: dict[str, int] = {}
    cols = st.columns(3)
    card_counts = dict(DEFAULT_CARD_COUNTS)
    card_counts.update(config.card_counts)
    for idx, (card_name, default_count) in enumerate(card_counts.items()):
        label = CARD_LABELS.get(card_name, card_name)
        counts[card_name] = int(cols[idx % len(cols)].number_input(
            f"{label} 枚数",
            min_value=0,
            max_value=999,
            value=int(default_count),
            step=1,
            key=widget_key(f"card_count_{card_name}"),
        ))
    col3.metric("山札総枚数", sum(counts.values()))
    return {
        "initial_hand_size": int(initial_hand_size),
        "mulligan_enabled": bool(mulligan_enabled),
        "card_counts": counts,
    }


def render_results(result: dict) -> None:
    st.header("7. シミュレーション結果")
    cols = st.columns(5)
    cols[0].metric("ゲームクリア率", f"{result['clear_rate']:.2%}")
    cols[1].metric("失敗率", f"{result['fail_rate']:.2%}")
    cols[2].metric("平均クリアターン", "-" if result["average_clear_turn"] is None else f"{result['average_clear_turn']:.2f}")
    cols[3].metric("15ターン終了時 平均建築進捗", f"{result['average_final_progress']:.2f}")
    cols[4].metric("宝くじ収入割合", f"{result['lottery_income_share']:.2%}")
    st.metric("平均総収入", f"{result['average_total_income']:,.0f}円")

    col1, col2 = st.columns(2)
    clear_df = pd.DataFrame(sorted(result["clear_turn_distribution"].items()), columns=["ターン", "回数"])
    col1.subheader("クリアターン分布")
    col1.bar_chart(clear_df.set_index("ターン") if not clear_df.empty else pd.DataFrame())

    money_df = pd.DataFrame({"ターン": range(1, len(result["average_money_by_turn"]) + 1), "平均共有所持金": result["average_money_by_turn"]})
    col2.subheader("ターンごとの平均所持金")
    col2.line_chart(money_df.set_index("ターン"))

    st.subheader("建築統計")
    st.dataframe(pd.DataFrame([{
        "建築挑戦回数": result["build_attempts"],
        "建築成功回数": result["build_successes"],
        "建築失敗回数": result["build_failures"],
        "護衛選択回数": result["guard_selected"],
        "護衛成功回数": result["guard_success"],
        "護衛による建築バフ発生回数": result["guard_build_bonus_events"],
        "護衛バフあり建築挑戦回数": result["guard_buffed_build_attempts"],
        "護衛バフあり建築成功率": result["guard_buffed_build_success_rate"],
        "護衛バフなし建築成功率": result["unbuffed_build_success_rate"],
        "護衛バフによる平均成功率上昇": result["average_guard_build_bonus_rate_uplift"],
        "大工パッシブ建築費総減額": result["carpenter_passive_build_discount_total"],
        "大工半減行動選択回数": result["carpenter_build_half_selected"],
        "大工半減行動成功回数": result["carpenter_build_half_success"],
        "大工半減効果発動回数": result["carpenter_build_half_effect_events"],
        "大工半減効果あり建築回数": result["carpenter_build_half_applied_builds"],
    }]), use_container_width=True)
    st.dataframe(pd.DataFrame([{"段階": k, "到達率": v} for k, v in result["stage_reach_rates"].items()]), use_container_width=True)

    st.subheader("行動統計")
    action_names = sorted(set(result["action_selected"]) | set(result["action_success"]))
    action_df = pd.DataFrame([
        {"行動": name, "選択回数": result["action_selected"].get(name, 0), "成功回数": result["action_success"].get(name, 0)}
        for name in action_names
    ])
    st.dataframe(action_df, use_container_width=True)

    st.subheader("収入統計")
    st.dataframe(pd.DataFrame([{
        "商人パッシブ総収入": result["merchant_passive_income_total"],
        "ニートパッシブ総回復量": result["neet_passive_recovery_total"],
        "上級ニート全回復発動回数": result["advanced_neet_full_recovery_events"],
    }]), use_container_width=True)
    source_df = pd.DataFrame([{"収入源": k, "総収入": v} for k, v in result["income_by_source"].items()])
    job_df = pd.DataFrame([
        {"職業": k, "総収入": v, "1試行あたり平均収入": result["average_income_by_job"].get(k, 0)}
        for k, v in result["income_by_job"].items()
    ])
    col3, col4 = st.columns(2)
    col3.bar_chart(source_df.set_index("収入源") if not source_df.empty else pd.DataFrame())
    col4.bar_chart(job_df.set_index("職業")[["総収入"]] if not job_df.empty else pd.DataFrame())
    st.dataframe(job_df, use_container_width=True)

    st.subheader("休みイベント統計")
    st.dataframe(pd.DataFrame([{
        "休み回数": result["rests"],
        "宝くじ選択回数": result["lottery_selected"],
        "宝くじ当選回数": result["lottery_wins"],
        "宝くじ当選率": result["lottery_win_rate"],
        "宝くじ総収入": result["lottery_income"],
        "散歩選択回数": result["walk_selected"],
        "散歩成功回数": result["walk_success"],
        "散歩収入": result["walk_income"],
        "ドカ寝選択回数": result["sleep_selected"],
        "昇格挑戦回数": result["promotion_attempts"],
        "昇格成功回数": result["promotion_success"],
    }]), use_container_width=True)

    st.subheader("昇格による上昇幅")
    card_names = sorted(
        set(result["card_draw_counts"])
        | set(result["card_use_counts"])
        | set(result["card_discard_counts"])
    )
    card_df = pd.DataFrame([
        {
            "カード": CARD_LABELS.get(card, card),
            "ドロー回数": result["card_draw_counts"].get(card, 0),
            "使用回数": result["card_use_counts"].get(card, 0),
            "使用率": result["card_use_rates"].get(card, 0),
            "捨て札回数": result["card_discard_counts"].get(card, 0),
        }
        for card in card_names
    ])
    st.subheader("カード統計")
    st.dataframe(card_df, use_container_width=True)
    st.dataframe(pd.DataFrame([{
        "マリガン実行人数": result["mulligan_players"],
        "マリガン枚数": result["mulligan_cards"],
        "山札再構築回数": result["deck_rebuilds"],
        "カード交換使用回数": result["hand_swap_uses"],
        "順番入れ替え使用回数": result["order_swap_uses"],
        "実際に順番が変更された回数": result["order_swap_changed"],
        "昇格カード使用回数": result["promotion_card_uses"],
        "解禁前昇格滞留回数": result["promotion_locked_stalls"],
        "宝くじカード使用回数": result["lottery_card_uses"],
        "ドカ寝総追加回復量": result["sleep_extra_recovery_total"],
        "カード総数不一致ゲーム数": result["card_total_mismatch_games"],
    }]), use_container_width=True)

    promotion_rows = [
        {
            "職業": row["job"],
            "通常職時の平均1行動収入": row["normal_average_action_income"],
            "上級職時の平均1行動収入": row["advanced_average_action_income"],
            "差額": row["difference"],
            "上昇率": row["uplift_rate"],
            "平均昇格ターン": row["average_promotion_turn"],
            "昇格挑戦率": row["promotion_attempt_rate"],
            "昇格成功率": row["promotion_success_rate"],
            "昇格挑戦回数": row["promotion_attempts"],
            "昇格成功回数": row["promotion_successes"],
            "昇格したゲームでの平均総収入": row["promoted_game_average_total_income"],
            "昇格しなかったゲームでの平均総収入": row["unpromoted_game_average_total_income"],
        }
        for row in result["promotion_by_job"]
    ]
    st.dataframe(pd.DataFrame(promotion_rows), use_container_width=True)

    st.subheader("神に祈る / 宝くじ倍率 統計")
    st.dataframe(pd.DataFrame([{
        "神に祈る選択回数": result["neet_pray_selected"],
        "神に祈る成功回数": result["neet_pray_success"],
        "通常ニートによる宝くじ倍率発動回数": result["normal_neet_lottery_multiplier_activations"],
        "上級ニートによる宝くじ倍率発動回数": result["advanced_neet_lottery_multiplier_activations"],
        "倍率あり宝くじ挑戦回数": result["boosted_lottery_attempts"],
        "倍率あり宝くじ当選回数": result["boosted_lottery_wins"],
        "倍率なし宝くじ当選率": result["unboosted_lottery_win_rate"],
        "倍率あり宝くじ当選率": result["boosted_lottery_win_rate"],
    }]), use_container_width=True)


def render_ai_mode_comparison(config: SimulationConfig) -> None:
    with st.expander("行動AI方式 一括比較", expanded=False):
        st.caption("同じ設定・同じseedで3つのAI方式を比較します。各方式で同じseedから再実行します。")
        if not st.button("行動AI方式を比較"):
            return
        started = time.perf_counter()
        with st.spinner("行動AI方式を比較中..."):
            rows = run_ai_mode_comparison(config)
        elapsed = time.perf_counter() - started
        df = pd.DataFrame([
            {
                "AI方式": row["ai_label"],
                "クリア率": row["clear_rate"],
                "平均クリアターン": row["average_clear_turn"],
                "平均総収入": row["average_total_income"],
                "15ターン終了時平均所持金": row["average_final_money"],
                "平均建築進捗": row["average_final_progress"],
                "宝くじ選択回数": row["lottery_selected"],
                "護衛選択回数": row["guard_selected"],
                "大工建築費半減選択回数": row["carpenter_build_half_selected"],
                "昇格挑戦回数": row["promotion_attempts"],
            }
            for row in rows
        ])
        st.dataframe(df, use_container_width=True)
        st.caption(f"処理時間: {elapsed:.2f}秒")


def render_promotion_comparison(config: SimulationConfig) -> None:
    with st.expander("昇格成功率の一括比較", expanded=False):
        rate_text = st.text_input("比較する昇格成功率", value="1/6, 2/6, 3/6, 4/6")
        st.caption("同じゲーム条件で昇格成功率だけを変更して比較します。例: 1/6, 2/6, 0.5")
        if not st.button("昇格成功率を比較"):
            return
        rates = parse_rate_list(rate_text)
        if not rates:
            st.warning("比較する成功率を読み取れませんでした。")
            return
        with st.spinner("昇格成功率を比較中..."):
            rows = run_promotion_rate_comparison(config, rates)
        df = pd.DataFrame([
            {
                "昇格成功確率": row["promotion_success_rate_setting"],
                "クリア率": row["clear_rate"],
                "平均クリアターン": row["average_clear_turn"],
                "平均総収入": row["average_total_income"],
                "昇格挑戦率": row["promotion_attempt_rate"],
                "昇格成功率": row["promotion_success_rate"],
                "平均昇格ターン": row["average_promotion_turn"],
                "宝くじ依存度": row["lottery_income_share"],
            }
            for row in rows
        ])
        st.dataframe(df, use_container_width=True)
        chart_df = df.set_index("昇格成功確率")
        st.line_chart(chart_df[["平均総収入"]])
        st.line_chart(chart_df[["クリア率"]])


def parse_rate(value: str, default: float | None = None) -> float | None:
    text = value.strip()
    if not text:
        return default
    is_percent = text.endswith("%")
    if is_percent:
        text = text[:-1].strip()
    try:
        if "/" in text:
            numerator, denominator = text.split("/", 1)
            rate = float(numerator.strip()) / float(denominator.strip())
        else:
            rate = float(text)
    except (ValueError, ZeroDivisionError):
        return default
    return rate / 100 if is_percent else rate


def parse_rate_list(value: str) -> list[float]:
    rates: list[float] = []
    for token in value.replace("\n", ",").split(","):
        rate = parse_rate(token)
        if rate is not None and 0 <= rate <= 1:
            rates.append(rate)
    return rates


if __name__ == "__main__":
    main()
