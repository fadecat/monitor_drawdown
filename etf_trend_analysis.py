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
    frame["trend_state"] = None
    frame["state_candidate_changed"] = False
    frame["transition_confirmed"] = False
    frame["transition_date"] = None

    output_records = []
    for row in frame.to_dict(orient="records"):
        output_records.append(
            {
                "date": str(row["date"]),
                "close": float(row["close"]),
                "ma20": _optional_float(row["ma20"]),
                "bias20_raw": _optional_float(row["bias20_raw"]),
                "bias20": _optional_float(row["bias20"]),
                "direction5": _optional_float(row["direction5"]),
                "trend_state": row["trend_state"],
                "state_candidate_changed": bool(row["state_candidate_changed"]),
                "transition_confirmed": bool(row["transition_confirmed"]),
                "transition_date": row["transition_date"],
            }
        )

    return {
        "records": output_records,
        "latest_transition_date": None,
        "latest_valid_state": None,
        "latest_valid_date": None,
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
