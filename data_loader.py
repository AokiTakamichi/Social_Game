from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile

from config import DEFAULT_EXCEL_FILENAME, DEFAULT_REST_EVENTS
from models import Action, Job

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS = {"main": MAIN_NS}


def find_excel_file(base_dir: Path) -> Path:
    candidate = base_dir / DEFAULT_EXCEL_FILENAME
    if not candidate.exists():
        raise FileNotFoundError(f"{DEFAULT_EXCEL_FILENAME} が見つかりません")
    return candidate


def load_game_data(path: Path) -> tuple[dict[str, Job], dict[str, dict], list[str]]:
    sheets = _read_workbook(path)
    jobs: dict[str, Job] = {}
    warnings: list[str] = []
    rest_events = {k: dict(v) for k, v in DEFAULT_REST_EVENTS.items()}

    if "宝くじ" in sheets:
        rows = sheets["宝くじ"]
        try:
            if len(rows) > 1 and len(rows[1]) >= 3:
                rest_events["lottery"]["success_rate"] = _to_float(rows[1][0], 1 / 6)
                rest_events["lottery"]["amount"] = _to_int(rows[1][2], 300_000)
        except (TypeError, ValueError):
            warnings.append("宝くじシートの確率/金額を読み取れなかったためデフォルト値を使います。")

    for sheet_name, rows in sheets.items():
        if sheet_name == "宝くじ" or not rows:
            continue
        job = Job(name=sheet_name)
        for row in rows[1:]:
            action = _parse_action(sheet_name, row)
            if action is None:
                continue
            if action.tier == "advanced":
                job.advanced_actions.append(action)
            else:
                job.normal_actions.append(action)
            if action.notes:
                warnings.append(f"{sheet_name}/{action.name}: {action.notes}")
        if job.name == "騎士":
            job.passive = {"max_stamina_bonus_per_player": True}
        jobs[job.name] = job

    if not jobs:
        warnings.append("職業シートを読み取れませんでした。")
    _apply_official_action_values(jobs, warnings)
    return jobs, rest_events, warnings


def _apply_official_action_values(jobs: dict[str, Job], warnings: list[str]) -> None:
    neet_job = jobs.get("ニート")
    if neet_job is None:
        neet_job = next((job for job in jobs.values() if "ニート" in job.name), None)
    if neet_job is not None:
        official_neet_amounts = {
            "神に祈る": 0,
            "お手伝い": 0,
            "バイト": 6_000,
            "脛かじり": 20_000,
            "親のすね": 20_000,
            "すねをかじる": 20_000,
        }
        for action in neet_job.normal_actions + neet_job.advanced_actions:
            for label, amount in official_neet_amounts.items():
                if label in action.name:
                    action.amount = amount
                    action.effect_type = "income"
                    action.multiplier = None
                    break
        warnings.append("ニートの行動金額は正式仕様（神に祈る0円、お手伝い0円、バイト6,000円、脛かじり20,000円）で初期化しました。")

    merchant_job = jobs.get("商人")
    merchant_jobs = [merchant_job] if merchant_job is not None else [job for job in jobs.values() if "商人" in job.name]
    merchant_overridden = False
    for job in merchant_jobs:
        for action in job.advanced_actions:
            if action.effect_type == "multiplier" and "1.5" in action.name:
                action.multiplier = 1.5
                merchant_overridden = True
    if merchant_overridden:
        warnings.append("商人上級の「所持金1.5倍（上級）」は正式仕様の1.5倍で初期化しました。")


def _parse_action(job: str, row: list[object]) -> Action | None:
    if not row or not row[0]:
        return None
    name_raw = str(row[0]).strip()
    if not name_raw:
        return None
    tier = "advanced" if "上級" in name_raw else "normal"
    name = _clean_action_name(name_raw)
    success_rate = _to_float(row[2] if len(row) > 2 else None, 0.0)
    stamina_cost = _to_int(row[3] if len(row) > 3 else None, 0)
    effect = str(row[4]).strip() if len(row) > 4 and row[4] is not None else ""

    multiplier = _parse_multiplier(effect)
    effect_type = "income"
    amount = 0
    delay_turns = 0
    delay_multiplier = 1.0
    notes = ""

    if multiplier is not None:
        effect_type = "multiplier"
    elif "2ターン後" in effect and "3倍" in effect:
        effect_type = "delayed_investment"
        delay_turns = 2
        delay_multiplier = 3.0
    elif effect and _to_int(effect, 0) > 0 and not any(token in effect for token in ("体力", "建築費")):
        amount = _to_int(effect, 0)
    elif "建築費" in effect and "半分" in effect:
        effect_type = "build_cost_multiplier"
        multiplier = 0.5
    elif "建築費" in effect:
        effect_type = "unsupported"
        notes = f"特殊効果「{effect}」は対象指定がないため収入0の未対応効果として扱います。"
    elif "体力回復" in effect:
        effect_type = "stamina_recovery"
        amount = _to_int(effect, 0)
    elif effect and amount == 0:
        effect_type = "unsupported"
        notes = f"効果「{effect}」を数値収入として解釈できません。"
    elif not effect:
        notes = "金額/効果が空のため収入0として扱います。"

    if "所持金1.5倍" in name_raw and effect and "1.25倍" in effect:
        notes = (notes + " " if notes else "") + "行動名は1.5倍ですが効果欄は1.25倍です。効果欄の倍率を初期値にします。"

    return Action(
        job=job,
        name=name,
        tier=tier,
        success_rate=success_rate,
        stamina_cost=stamina_cost,
        amount=amount,
        multiplier=multiplier,
        effect_type=effect_type,
        delay_turns=delay_turns,
        delay_multiplier=delay_multiplier,
        raw_effect=effect,
        notes=notes,
    )


def _clean_action_name(value: str) -> str:
    text = value.strip()
    if ")" in text:
        return text[: text.index(")") + 1]
    if "）" in text:
        return text[: text.index("）") + 1]
    match = re.match(r"^(.+?[一-龥ぁ-んー])([ァ-ン]+)$", text)
    return match.group(1) if match else text


def _parse_multiplier(value: str) -> float | None:
    match = re.search(r"所持金\s*([0-9]+(?:\.[0-9]+)?)倍", value)
    if match:
        return float(match.group(1))
    return None


def _to_int(value: object, default: int = 0) -> int:
    if value is None or value == "":
        return default
    if isinstance(value, (int, float)):
        return int(round(float(value)))
    text = str(value).replace(",", "")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    return int(round(float(match.group(0)))) if match else default


def _to_float(value: object, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace("%", "")
    try:
        parsed = float(text)
        return parsed / 100 if "%" in str(value) else parsed
    except ValueError:
        return default


def _read_workbook(path: Path) -> dict[str, list[list[object]]]:
    with ZipFile(path) as archive:
        shared = _read_shared_strings(archive)
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        rel_map = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels}
        result: dict[str, list[list[object]]] = {}
        for sheet in workbook.find("main:sheets", NS):
            name = sheet.attrib["name"]
            rid = sheet.attrib[f"{{{REL_NS}}}id"]
            target = rel_map[rid]
            if not target.startswith("xl/"):
                target = f"xl/{target}"
            result[name] = _read_sheet(archive, target, shared)
        return result


def _read_shared_strings(archive: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    return ["".join(t.text or "" for t in si.findall(".//main:t", NS)) for si in root.findall("main:si", NS)]


def _read_sheet(archive: ZipFile, target: str, shared: list[str]) -> list[list[object]]:
    root = ET.fromstring(archive.read(target))
    rows: list[list[object]] = []
    for row in root.findall(".//main:sheetData/main:row", NS):
        values: list[object] = []
        for cell in row.findall("main:c", NS):
            idx = _column_index(cell.attrib.get("r", "A1"))
            while len(values) < idx:
                values.append("")
            value_node = cell.find("main:v", NS)
            value: object = ""
            if value_node is not None:
                raw = value_node.text or ""
                if cell.attrib.get("t") == "s":
                    value = shared[int(raw)] if raw else ""
                else:
                    value = _number_or_text(raw)
            values.append(value)
        rows.append(values)
    return rows


def _column_index(ref: str) -> int:
    match = re.match(r"([A-Z]+)", ref)
    if not match:
        return 0
    index = 0
    for char in match.group(1):
        index = index * 26 + ord(char) - 64
    return index - 1


def _number_or_text(raw: str) -> object:
    try:
        number = float(raw)
    except ValueError:
        return raw
    return int(number) if number.is_integer() else number
