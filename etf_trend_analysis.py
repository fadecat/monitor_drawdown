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


def _classify_screenshot_proxy_state_value(
    bias20: float | None, direction5: float | None
) -> str | None:
    if bias20 is None or direction5 is None:
        return None
    if bias20 >= 0.006:
        return "确立多头"
    if 0.002 <= bias20 < 0.006 and direction5 <= 0:
        return "确立多头"
    if -0.007 <= bias20 < 0.002 and direction5 <= -0.03:
        return "确立多头"
    if -0.04 < bias20 <= -0.016 and direction5 > -0.001:
        return "确立空头"
    if bias20 <= -0.04 and direction5 > -0.015:
        return "确立空头"
    if bias20 <= -0.07:
        return "确立空头"
    return "震荡中"


def _classify_screenshot_transition_regime_value(
    bias20_raw: float | None, bias20: float | None
) -> str | None:
    if bias20_raw is None or bias20 is None:
        return None
    if bias20_raw >= 0.01 and bias20 >= 0:
        return "确立多头"
    if bias20_raw <= -0.015 and bias20 <= -0.01:
        return "确立空头"
    return "震荡中"


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


def _find_latest_state_run_start(
    records: list[dict[str, Any]], state_field: str
) -> tuple[str | None, str | None]:
    latest_state: str | None = None
    latest_date: str | None = None
    for row in reversed(records):
        state = row.get(state_field)
        if state is None:
            continue
        latest_state = str(state)
        latest_date = str(row["date"])
        break

    if latest_state is None or latest_date is None:
        return None, None

    run_start = latest_date
    for row in reversed(records):
        state = row.get(state_field)
        if state is None:
            continue
        if str(row["date"]) == latest_date:
            continue
        if state != latest_state:
            break
        run_start = str(row["date"])

    return latest_state, run_start


def _apply_screenshot_transition_regime(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    output = [dict(record) for record in records]
    current_state: str | None = None
    current_start: str | None = None
    candidate_state: str | None = None
    candidate_start: str | None = None
    candidate_streak = 0
    confirm_days = {"确立多头": 1, "震荡中": 2, "确立空头": 3}

    for row in output:
        signal = row.get("screenshot_transition_regime_signal")
        if signal is None:
            row["screenshot_transition_regime_state"] = current_state
            row["screenshot_transition_regime_start_date"] = current_start
            continue

        if signal == candidate_state:
            candidate_streak += 1
        else:
            candidate_state = str(signal)
            candidate_start = str(row["date"])
            candidate_streak = 1

        needed = confirm_days.get(str(signal), 1)
        if candidate_streak >= needed and signal != current_state:
            current_state = str(signal)
            current_start = candidate_start

        row["screenshot_transition_regime_state"] = current_state
        row["screenshot_transition_regime_start_date"] = current_start

    return output


def _build_screenshot_proxy_hidden_regime(
    records: list[dict[str, Any]],
) -> tuple[str | None, str | None]:
    hidden_state: str | None = None
    hidden_start: str | None = None
    candidate_state: str | None = None
    candidate_start: str | None = None
    candidate_streak = 0

    for row in records:
        state = row.get("screenshot_proxy_state")
        if state is None:
            continue
        if state == candidate_state:
            candidate_streak += 1
        else:
            candidate_state = str(state)
            candidate_start = str(row["date"])
            candidate_streak = 1

        target_state: str | None = None
        if state == "震荡中":
            if candidate_streak >= 2:
                target_state = "震荡中"
        else:
            target_state = str(state)

        if target_state is not None and target_state != hidden_state:
            hidden_state = target_state
            hidden_start = candidate_start

    if hidden_state is None:
        return None, None
    return hidden_state, hidden_start


def _find_latest_bias_sign_transition_date(
    records: list[dict[str, Any]],
) -> str | None:
    latest_sign: bool | None = None
    latest_date: str | None = None
    for row in reversed(records):
        bias20 = _optional_float(row.get("bias20"))
        if bias20 is None:
            continue
        latest_sign = bias20 > 0
        latest_date = str(row["date"])
        break

    if latest_sign is None or latest_date is None:
        return None

    run_start = latest_date
    for row in reversed(records):
        bias20 = _optional_float(row.get("bias20"))
        if bias20 is None:
            continue
        if str(row["date"]) == latest_date:
            continue
        if (bias20 > 0) != latest_sign:
            break
        run_start = str(row["date"])
    return run_start


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
                "screenshot_proxy_state": _classify_screenshot_proxy_state_value(
                    bias20, direction5
                ),
                "screenshot_transition_regime_signal": _classify_screenshot_transition_regime_value(
                    _optional_float(row["bias20_raw"]),
                    bias20,
                ),
                "screenshot_transition_regime_state": None,
                "screenshot_transition_regime_start_date": None,
                "state_candidate_changed": False,
                "transition_confirmed": False,
                "transition_date": row["transition_date"],
            }
        )

    output_records = _confirm_transitions(output_records)
    output_records = _apply_screenshot_transition_regime(output_records)
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


def build_latest_screenshot_proxy_snapshot(analysis: dict[str, Any]) -> dict[str, Any]:
    records = analysis.get("records") or []
    if not records:
        return {
            "screenshot_bias_value": None,
            "screenshot_trend_state": None,
            "screenshot_transition_date": None,
        }

    latest = records[-1]
    latest_state, run_start = _build_screenshot_proxy_hidden_regime(records)
    return {
        "screenshot_bias_value": latest.get("bias20_raw"),
        "screenshot_trend_state": latest_state,
        "screenshot_transition_date": run_start,
    }


def build_latest_screenshot_transition_regime_snapshot(
    analysis: dict[str, Any],
) -> dict[str, Any]:
    records = analysis.get("records") or []
    if not records:
        return {
            "screenshot_transition_regime_state": None,
            "screenshot_transition_regime_transition_date": None,
        }

    latest_state = None
    latest_start = None
    for row in reversed(records):
        state = row.get("screenshot_transition_regime_state")
        if state is None:
            continue
        latest_state = str(state)
        latest_start = row.get("screenshot_transition_regime_start_date")
        break

    return {
        "screenshot_transition_regime_state": latest_state,
        "screenshot_transition_regime_transition_date": latest_start,
    }


def build_latest_screenshot_transition_bias_sign_snapshot(
    analysis: dict[str, Any],
) -> dict[str, Any]:
    proxy_snapshot = build_latest_screenshot_proxy_snapshot(analysis)
    return {
        "screenshot_transition_bias_sign_state": proxy_snapshot.get(
            "screenshot_trend_state"
        ),
        "screenshot_transition_bias_sign_transition_date": _find_latest_bias_sign_transition_date(
            analysis.get("records") or []
        ),
    }


def _pick_hybrid_transition_date(
    screenshot_trend_state: str | None,
    proxy_transition_date: str | None,
    regime_transition_date: str | None,
    bias20_raw: float | None,
    bias20: float | None,
    direction5: float | None,
) -> str | None:
    if proxy_transition_date is None:
        return regime_transition_date
    if regime_transition_date is None:
        return proxy_transition_date
    if screenshot_trend_state == "确立多头":
        if direction5 is not None and direction5 <= -0.02:
            return regime_transition_date
        if bias20_raw is not None and bias20_raw <= 0.01:
            return regime_transition_date
        return proxy_transition_date
    if screenshot_trend_state == "确立空头":
        if direction5 is not None and direction5 >= 0:
            return proxy_transition_date
        if bias20 is not None and bias20 >= -0.02:
            return proxy_transition_date
        return regime_transition_date
    if direction5 is not None and direction5 <= -0.05:
        return proxy_transition_date
    return regime_transition_date


def build_latest_screenshot_transition_hybrid_snapshot(
    analysis: dict[str, Any],
) -> dict[str, Any]:
    records = analysis.get("records") or []
    proxy_snapshot = build_latest_screenshot_proxy_snapshot(analysis)
    regime_snapshot = build_latest_screenshot_transition_regime_snapshot(analysis)
    latest = records[-1] if records else {}
    screenshot_trend_state = proxy_snapshot.get("screenshot_trend_state")
    proxy_transition_date = proxy_snapshot.get("screenshot_transition_date")
    regime_transition_date = regime_snapshot.get(
        "screenshot_transition_regime_transition_date"
    )
    return {
        "screenshot_transition_hybrid_state": screenshot_trend_state,
        "screenshot_transition_hybrid_transition_date": _pick_hybrid_transition_date(
            None if screenshot_trend_state is None else str(screenshot_trend_state),
            None if proxy_transition_date is None else str(proxy_transition_date),
            None if regime_transition_date is None else str(regime_transition_date),
            _optional_float(latest.get("bias20_raw")),
            _optional_float(latest.get("bias20")),
            _optional_float(latest.get("direction5")),
        ),
    }
