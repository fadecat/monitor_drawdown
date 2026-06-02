from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import requests


JISILU_CB_INDEX_URL = "https://www.jisilu.cn/data/cbnew/cb_index/"
MARKET_TEMPERATURE_HISTORY_JSON = Path("market_temperature_history.json")
REQUEST_TIMEOUT = 20

RAW_FIELD_ALIASES = {"price": "index_value"}


def fetch_cb_index_page(url: str = JISILU_CB_INDEX_URL) -> str:
    response = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.text


def parse_jisilu_page(body: str) -> list[dict[str, str]]:
    date_match = re.search(r"var __date\s*=\s*(\[[^\]]*\]);", body)
    if not date_match:
        raise RuntimeError("missing var __date")
    dates = re.findall(r"'([^']*)'", date_match.group(1))

    data_match = re.search(r"var __data\s*=\s*\{([\s\S]*?)\};", body)
    if not data_match:
        raise RuntimeError("missing var __data")

    pairs = re.findall(r"'([a-zA-Z_]+)'\s*:\s*\[([^\]]*)\]", data_match.group(1))
    series: dict[str, list[str]] = {}
    for raw_key, raw_values in pairs:
        series[raw_key] = [value.strip() for value in raw_values.split(",") if value.strip()]

    records: list[dict[str, str]] = []
    for index, row_date in enumerate(dates):
        record: dict[str, str] = {"date": row_date}
        for raw_key, values in series.items():
            if index >= len(values):
                continue
            target_key = RAW_FIELD_ALIASES.get(raw_key, raw_key)
            record[target_key] = values[index]
        records.append(record)
    return records


def load_history(path: Path | None = None) -> list[dict[str, Any]]:
    history_path = path or MARKET_TEMPERATURE_HISTORY_JSON
    if not history_path.exists():
        return []
    return json.loads(history_path.read_text(encoding="utf-8"))


def merge_records(
    history: list[dict[str, Any]],
    live_records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    by_date = {str(record["date"]): dict(record) for record in history if record.get("date")}
    stats = {"history": len(by_date), "updated": 0, "added": 0}

    for record in live_records:
        row_date = str(record.get("date") or "").strip()
        if not row_date:
            raise ValueError("live record missing date")
        if row_date in by_date:
            by_date[row_date].update({key: value for key, value in record.items() if key != "date"})
            stats["updated"] += 1
        else:
            by_date[row_date] = dict(record)
            stats["added"] += 1

    merged = [by_date[row_date] for row_date in sorted(by_date)]
    return merged, stats


def build_merged_history() -> tuple[list[dict[str, Any]], dict[str, int]]:
    history = load_history(MARKET_TEMPERATURE_HISTORY_JSON)
    live_records = parse_jisilu_page(fetch_cb_index_page())
    return merge_records(history, live_records)


def build_runtime_merged_history() -> list[dict[str, Any]]:
    merged, _ = build_merged_history()
    return merged


def build_runtime_index_series() -> list[dict[str, Any]]:
    series: list[dict[str, Any]] = []
    for record in build_runtime_merged_history():
        row_date = str(record.get("date") or "").strip()
        raw_value = record.get("index_value")
        if not row_date or raw_value in (None, ""):
            continue
        series.append(
            {
                "date": row_date,
                "value": float(raw_value),
            }
        )
    if not series:
        raise ValueError("empty cb index runtime series")
    return series
