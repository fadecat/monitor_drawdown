from __future__ import annotations

import math
from typing import Any


def calculate_lookback_return(
    closes: list[float],
    lookback_days: int,
) -> float | None:
    if len(closes) <= lookback_days:
        return None

    base_close = float(closes[-lookback_days - 1])
    latest_close = float(closes[-1])
    if not math.isfinite(base_close) or not math.isfinite(latest_close) or base_close <= 0:
        return None

    lookback_return = latest_close / base_close - 1.0
    if not math.isfinite(lookback_return):
        return None
    return lookback_return


def build_rotation_candidate(
    latest_snapshot: dict[str, Any],
    series_records: list[dict[str, Any]],
    strategy_config: dict[str, Any],
) -> dict[str, Any] | None:
    lookback_days = int(strategy_config["lookback_days"])
    window_records = series_records[-(lookback_days + 1):]
    if len(window_records) < lookback_days + 1:
        return None

    closes: list[float] = []
    for row in window_records:
        raw_close = row.get("close")
        if raw_close in {None, ""}:
            return None
        try:
            close_value = float(raw_close)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(close_value):
            return None
        closes.append(close_value)

    return_20d = calculate_lookback_return(
        closes=closes,
        lookback_days=lookback_days,
    )
    if return_20d is None or return_20d <= 0:
        return None

    return {
        "label": latest_snapshot.get("label"),
        "return_20d": return_20d,
        "latest_snapshot": latest_snapshot,
    }


def rank_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        candidates,
        key=lambda item: float(item.get("return_20d") or 0.0),
        reverse=True,
    )


def select_portfolio(
    candidates: list[dict[str, Any]],
    strategy_config: dict[str, Any],
) -> dict[str, Any]:
    ranked_candidates = rank_candidates(candidates)
    holdings_num = max(int(strategy_config.get("holdings_num") or 1), 1)

    return {
        "selected_holdings": ranked_candidates[:holdings_num],
        "selection_reason": (
            "top_ranked_candidate" if ranked_candidates else "no_qualified_candidate"
        ),
        "rejected_candidates": ranked_candidates[holdings_num:],
    }
