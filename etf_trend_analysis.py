from __future__ import annotations

from typing import Any

import pandas as pd


def _optional_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _normalize_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[tuple[pd.Timestamp, dict[str, Any]]] = []
    for row in records:
        date_text = str(row.get("date") or "").strip()
        close_value = row.get("close")
        if not date_text or close_value in {None, ""}:
            continue
        try:
            normalized_date = pd.to_datetime(date_text)
            normalized.append(
                (normalized_date, {"date": date_text, "close": float(close_value)})
            )
        except (TypeError, ValueError):
            continue
    normalized.sort(key=lambda item: item[0])
    return [item[1] for item in normalized]


def _classify_trend_state_value(
    bias20: float | None, direction5: float | None
) -> str | None:
    if bias20 is None or direction5 is None:
        return None
    if bias20 > 0 and direction5 > 0:
        return "强势上行"
    if bias20 > 0 and direction5 <= 0:
        return "强势回落"
    if bias20 <= 0 and direction5 > 0:
        return "弱势修复"
    return "弱势下行"


def _confirm_transitions(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not records:
        return []

    output = [dict(record) for record in records]
    previous_state: str | None = None
    candidate_state: str | None = None
    candidate_date: str | None = None

    for row in output:
        state = row.get("trend_state")
        if state is None:
            continue
        if previous_state is None:
            previous_state = state
            continue
        if candidate_state is None:
            if state != previous_state:
                row["state_candidate_changed"] = True
                candidate_state = state
                candidate_date = row["date"]
            continue
        if state == candidate_state:
            row["transition_confirmed"] = True
            row["transition_date"] = candidate_date
            previous_state = candidate_state
            candidate_state = None
            candidate_date = None
            continue
        candidate_state = None
        candidate_date = None
        if state != previous_state:
            row["state_candidate_changed"] = True
            candidate_state = state
            candidate_date = row["date"]

    return output


def analyze_trend_series(records: list[dict[str, Any]]) -> dict[str, Any]:
    normalized = _normalize_records(records)
    if not normalized:
        return {
            "records": [],
            "latest_transition_date": None,
            "latest_valid_state": None,
            "latest_valid_date": None,
        }

    frame = pd.DataFrame(normalized)
    frame["ma20"] = frame["close"].rolling(20).mean()
    frame["bias20_raw"] = frame["close"] / frame["ma20"] - 1
    frame["bias20"] = frame["bias20_raw"].rolling(5).mean()
    frame["direction5"] = frame["bias20"] - frame["bias20_raw"].shift(5)
    frame.loc[frame.index < 29, "direction5"] = pd.NA
    frame["state_candidate_changed"] = False
    frame["transition_confirmed"] = False
    frame["transition_date"] = None

    output_records = []
    for row in frame.to_dict(orient="records"):
        bias20 = _optional_float(row["bias20"])
        direction5 = _optional_float(row["direction5"])
        output_records.append(
            {
                "date": str(row["date"]),
                "close": float(row["close"]),
                "ma20": _optional_float(row["ma20"]),
                "bias20_raw": _optional_float(row["bias20_raw"]),
                "bias20": bias20,
                "direction5": direction5,
                "trend_state": _classify_trend_state_value(bias20, direction5),
                "state_candidate_changed": False,
                "transition_confirmed": False,
                "transition_date": row["transition_date"],
            }
        )

    output_records = _confirm_transitions(output_records)
    latest_valid = next(
        (row for row in reversed(output_records) if row["trend_state"] is not None), None
    )
    latest_transition = next(
        (
            row["transition_date"]
            for row in reversed(output_records)
            if row["transition_date"] is not None
        ),
        None,
    )

    return {
        "records": output_records,
        "latest_transition_date": latest_transition,
        "latest_valid_state": None if latest_valid is None else latest_valid["trend_state"],
        "latest_valid_date": None if latest_valid is None else latest_valid["date"],
    }


def build_latest_trend_snapshot(analysis: dict[str, Any]) -> dict[str, Any]:
    records = analysis.get("records") or []
    if not records:
        return {
            "latest_date": None,
            "close": None,
            "bias20_raw": None,
            "bias20": None,
            "direction5": None,
            "trend_state": None,
            "latest_transition_date": None,
        }

    latest = records[-1]
    return {
        "latest_date": latest["date"],
        "close": latest["close"],
        "bias20_raw": latest["bias20_raw"],
        "bias20": latest["bias20"],
        "direction5": latest["direction5"],
        "trend_state": latest["trend_state"],
        "latest_transition_date": analysis.get("latest_transition_date"),
    }
