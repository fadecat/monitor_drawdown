from __future__ import annotations

import math
from statistics import median
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


def calculate_weighted_trend_metrics(
    closes: list[float],
    annualization_days: int = 250,
    weight_start: float = 1.0,
    weight_end: float = 2.0,
) -> dict[str, float] | None:
    if len(closes) < 2:
        return None

    numeric_closes: list[float] = []
    for raw_close in closes:
        close_value = float(raw_close)
        if not math.isfinite(close_value) or close_value <= 0:
            return None
        numeric_closes.append(close_value)

    points_count = len(numeric_closes)
    x_values = [float(index) for index in range(points_count)]
    y_values = [math.log(close_value) for close_value in numeric_closes]
    if points_count == 1:
        weights = [float(weight_end)]
    else:
        step = (float(weight_end) - float(weight_start)) / float(points_count - 1)
        weights = [float(weight_start) + step * index for index in range(points_count)]

    sum_weights = sum(weights)
    if not math.isfinite(sum_weights) or sum_weights <= 0:
        return None

    weighted_mean_x = sum(weight * value for weight, value in zip(weights, x_values)) / sum_weights
    weighted_mean_y = sum(weight * value for weight, value in zip(weights, y_values)) / sum_weights
    weighted_var_x = (
        sum(weight * (value - weighted_mean_x) ** 2 for weight, value in zip(weights, x_values))
        / sum_weights
    )
    if not math.isfinite(weighted_var_x) or weighted_var_x <= 0:
        return None

    weighted_cov_xy = (
        sum(
            weight * (x_value - weighted_mean_x) * (y_value - weighted_mean_y)
            for weight, x_value, y_value in zip(weights, x_values, y_values)
        )
        / sum_weights
    )
    slope = weighted_cov_xy / weighted_var_x
    intercept = weighted_mean_y - slope * weighted_mean_x
    y_hat = [slope * x_value + intercept for x_value in x_values]

    annualized_return = math.exp(slope * float(annualization_days)) - 1.0
    weighted_mean_plain = sum(y_values) / float(points_count)
    ss_res = sum(weight * (actual - fitted) ** 2 for weight, actual, fitted in zip(weights, y_values, y_hat))
    ss_tot = sum(weight * (actual - weighted_mean_plain) ** 2 for weight, actual in zip(weights, y_values))

    if not math.isfinite(ss_res) or not math.isfinite(ss_tot) or ss_tot <= 0:
        r_squared = 0.0
    else:
        r_squared = 1.0 - ss_res / ss_tot
        if not math.isfinite(r_squared) or r_squared < 0:
            r_squared = 0.0

    score = annualized_return * r_squared
    if not math.isfinite(score):
        return None

    return {
        "slope": slope,
        "intercept": intercept,
        "annualized_return": annualized_return,
        "r_squared": r_squared,
        "score": score,
    }


def build_rotation_candidate(
    latest_snapshot: dict[str, Any],
    series_records: list[dict[str, Any]],
    strategy_config: dict[str, Any],
) -> dict[str, Any] | None:
    lookback_days = int(strategy_config["lookback_days"])
    short_lookback_days = int(strategy_config["short_lookback_days"])
    annualization_days = int(strategy_config.get("annualization_days") or 250)
    weight_start = float(strategy_config.get("weight_start") or 1.0)
    weight_end = float(strategy_config.get("weight_end") or 2.0)

    required_window = max(lookback_days, short_lookback_days + 1)
    window_records = series_records[-required_window:]
    if len(window_records) < required_window:
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
        if not math.isfinite(close_value) or close_value <= 0:
            return None
        closes.append(close_value)

    score_window_closes = closes[-lookback_days:]
    trend_metrics = calculate_weighted_trend_metrics(
        closes=score_window_closes,
        annualization_days=annualization_days,
        weight_start=weight_start,
        weight_end=weight_end,
    )
    if trend_metrics is None:
        return None

    return_10d = calculate_lookback_return(closes=closes, lookback_days=short_lookback_days)
    if return_10d is None:
        return None

    score_25 = float(trend_metrics["score"])

    return {
        "label": latest_snapshot.get("label"),
        "latest_snapshot": latest_snapshot,
        "score_25": score_25,
        "annualized_return_25": float(trend_metrics["annualized_return"]),
        "r_squared_25": float(trend_metrics["r_squared"]),
        "return_10d": return_10d,
        "score_25_positive": score_25 > 0,
        "qualified": None,
        "rejection_reason": "",
        "short_confirmation_threshold": None,
    }


def apply_relative_median_short_confirmation(
    candidates: list[dict[str, Any]],
    strategy_config: dict[str, Any],
) -> list[dict[str, Any]]:
    tolerance = float(strategy_config.get("short_confirmation_tolerance", 0.0))
    absolute_floor = float(strategy_config.get("short_confirmation_absolute_floor", -0.03))
    score_positive_candidates = [
        candidate for candidate in candidates if bool(candidate.get("score_25_positive"))
    ]
    relative_threshold = (
        median(float(candidate["return_10d"]) for candidate in score_positive_candidates) - tolerance
        if score_positive_candidates
        else None
    )
    effective_threshold = (
        max(float(relative_threshold), absolute_floor)
        if relative_threshold is not None
        else None
    )

    updated_candidates: list[dict[str, Any]] = []
    for candidate in candidates:
        updated_candidate = dict(candidate)
        updated_candidate["short_confirmation_threshold"] = effective_threshold
        if not bool(updated_candidate.get("score_25_positive")):
            updated_candidate["qualified"] = False
            updated_candidate["rejection_reason"] = "score_25_not_positive"
        elif float(updated_candidate["return_10d"]) < absolute_floor:
            updated_candidate["qualified"] = False
            updated_candidate["rejection_reason"] = "return_10d_below_absolute_floor"
        elif (
            relative_threshold is None
            or float(updated_candidate["return_10d"]) >= float(relative_threshold)
        ):
            updated_candidate["qualified"] = True
            updated_candidate["rejection_reason"] = ""
        else:
            updated_candidate["qualified"] = False
            updated_candidate["rejection_reason"] = "return_10d_below_cross_section_median"
        updated_candidates.append(updated_candidate)

    return updated_candidates


def rank_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    qualified_candidates = [candidate for candidate in candidates if bool(candidate.get("qualified"))]
    return sorted(
        qualified_candidates,
        key=lambda item: (
            float(item.get("score_25") or 0.0),
            float(item.get("return_10d") or 0.0),
            str(item.get("label") or ""),
        ),
        reverse=True,
    )


def select_portfolio(
    candidates: list[dict[str, Any]],
    strategy_config: dict[str, Any],
    defensive_candidate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ranked_candidates = rank_candidates(candidates)
    holdings_num = max(int(strategy_config.get("holdings_num") or 1), 1)
    if ranked_candidates:
        return {
            "selected_holdings": ranked_candidates[:holdings_num],
            "selection_reason": "top_ranked_risk_asset",
            "rejected_candidates": ranked_candidates[holdings_num:],
            "fallback_holding": None,
        }

    fallback_holdings = [defensive_candidate] if defensive_candidate else []
    return {
        "selected_holdings": fallback_holdings,
        "selection_reason": "fallback_defensive_asset",
        "rejected_candidates": [],
        "fallback_holding": defensive_candidate,
    }
