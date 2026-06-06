from __future__ import annotations

import math
from statistics import median
from typing import Any, Iterable


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


def calculate_volatility_adjusted_short_strength(
    return_10d: float,
    volatility_20d: float,
) -> float:
    if volatility_20d <= 0:
        return 0.0
    short_strength = return_10d / volatility_20d
    if not math.isfinite(short_strength):
        return 0.0
    return short_strength


def calculate_self_relative_short_percentile(
    current_value: float,
    history_values: Iterable[float],
) -> float:
    values = [float(value) for value in history_values if value is not None and math.isfinite(float(value))]
    if not values:
        return 0.0
    below_or_equal = sum(1 for value in values if value <= current_value)
    percentile = below_or_equal / len(values)
    if not math.isfinite(percentile):
        return 0.0
    return percentile


def _calculate_volatility(closes: list[float], lookback_days: int) -> float | None:
    if len(closes) < lookback_days + 1:
        return None

    returns: list[float] = []
    for index in range(len(closes) - lookback_days, len(closes)):
        previous_close = float(closes[index - 1])
        current_close = float(closes[index])
        if previous_close <= 0 or current_close <= 0:
            return None
        daily_return = current_close / previous_close - 1.0
        if not math.isfinite(daily_return):
            return None
        returns.append(daily_return)

    if len(returns) < 2:
        return None

    mean_return = sum(returns) / len(returns)
    variance = sum((value - mean_return) ** 2 for value in returns) / len(returns)
    if not math.isfinite(variance) or variance <= 0:
        return 0.0
    volatility = math.sqrt(variance)
    if not math.isfinite(volatility):
        return None
    return volatility


def _calculate_short_strength_history(
    closes: list[float],
    lookback_days: int,
) -> list[float]:
    if len(closes) < lookback_days + 1:
        return []

    history_values: list[float] = []
    for end_index in range(lookback_days, len(closes) - 1):
        window = closes[end_index - lookback_days : end_index + 1]
        if len(window) < lookback_days + 1:
            continue
        window_volatility = _calculate_volatility(window, lookback_days)
        if window_volatility is None or window_volatility <= 0:
            continue
        historical_return = calculate_lookback_return(window, lookback_days)
        if historical_return is None:
            continue
        history_values.append(
            calculate_volatility_adjusted_short_strength(historical_return, window_volatility)
        )
    return history_values


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


def build_rotation_candidate_v2(
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
    qualified = True
    rejection_reason = ""
    if score_25 <= 0:
        qualified = False
        rejection_reason = "score_25_not_positive"
    elif return_10d <= 0:
        qualified = False
        rejection_reason = "return_10d_not_positive"

    return {
        "label": latest_snapshot.get("label"),
        "latest_snapshot": latest_snapshot,
        "score_25": score_25,
        "annualized_return_25": float(trend_metrics["annualized_return"]),
        "r_squared_25": float(trend_metrics["r_squared"]),
        "return_10d": return_10d,
        "qualified": qualified,
        "rejection_reason": rejection_reason,
    }


def build_rotation_candidate_v4(
    latest_snapshot: dict[str, Any],
    series_records: list[dict[str, Any]],
    strategy_config: dict[str, Any],
) -> dict[str, Any] | None:
    candidate = build_rotation_candidate_v2(
        latest_snapshot=latest_snapshot,
        series_records=series_records,
        strategy_config=strategy_config,
    )
    if candidate is None:
        return None

    short_confirmation_variant = str(strategy_config.get("short_confirmation_variant") or "v4_a")
    history_days = int(strategy_config.get("short_confirmation_history_days") or 252)
    percentile_threshold = float(strategy_config.get("short_confirmation_percentile_threshold") or 0.4)
    absolute_floor = float(strategy_config.get("short_confirmation_absolute_floor") or -0.02)
    volatility_lookback_days = int(strategy_config.get("volatility_lookback_days") or 20)
    base_qualified = bool(candidate.get("qualified"))
    base_rejection_reason = str(candidate.get("rejection_reason") or "").strip()

    closes = [float(row["close"]) for row in series_records if row.get("close") not in {None, ""}]
    if len(closes) < 2:
        candidate.update(
            {
                "short_confirmation_variant": short_confirmation_variant,
                "volatility_20d": None,
                "volatility_adjusted_return_10d": None,
                "self_relative_short_percentile": None,
                "short_confirmation_passed": False,
                "short_confirmation_threshold": None,
                "absolute_floor": absolute_floor,
                "history_window": history_days,
                "rejection_reason": "insufficient_short_confirmation_history",
            }
        )
        candidate["qualified"] = False
        return candidate

    history_start_index = max(0, len(closes) - (history_days + 1))
    history_closes = closes[history_start_index:-1]
    if not history_closes:
        candidate.update(
            {
                "short_confirmation_variant": short_confirmation_variant,
                "volatility_20d": None,
                "volatility_adjusted_return_10d": None,
                "self_relative_short_percentile": None,
                "short_confirmation_passed": False,
                "short_confirmation_threshold": None,
                "absolute_floor": absolute_floor,
                "history_window": history_days,
                "rejection_reason": "insufficient_short_confirmation_history",
            }
        )
        candidate["qualified"] = False
        return candidate

    current_close = closes[-1]
    current_return_10d = float(candidate["return_10d"])
    volatility_20d = _calculate_volatility(closes=closes, lookback_days=volatility_lookback_days)
    if volatility_20d is None:
        volatility_20d = 0.0
    short_strength = calculate_volatility_adjusted_short_strength(current_return_10d, volatility_20d)
    history_returns: list[float] = []
    for index in range(1, len(history_closes)):
        previous_close = history_closes[index - 1]
        current_history_close = history_closes[index]
        if previous_close <= 0 or current_history_close <= 0:
            continue
        history_return = current_history_close / previous_close - 1.0
        if math.isfinite(history_return):
            history_returns.append(history_return)
    history_short_strengths = _calculate_short_strength_history(
        closes=history_closes,
        lookback_days=volatility_lookback_days,
    )

    if short_confirmation_variant == "v4_a":
        percentile_history_values = history_short_strengths
        short_confirmation_value = short_strength
    else:
        percentile_history_values = history_returns
        short_confirmation_value = current_return_10d

    short_confirmation_threshold = None
    if percentile_history_values:
        sorted_history = sorted(percentile_history_values)
        threshold_index = max(int(math.ceil(len(sorted_history) * percentile_threshold)) - 1, 0)
        short_confirmation_threshold = sorted_history[threshold_index]

    self_relative_short_percentile = calculate_self_relative_short_percentile(
        short_confirmation_value,
        percentile_history_values,
    )
    short_confirmation_passed = (
        short_confirmation_threshold is not None
        and short_confirmation_value >= short_confirmation_threshold
        and current_return_10d >= absolute_floor
    )
    short_rejection_reason = ""
    if not short_confirmation_passed:
        short_rejection_reason = (
            "return_10d_below_absolute_floor"
            if current_return_10d < absolute_floor
            else "short_confirmation_below_threshold"
        )

    final_qualified = base_qualified and short_confirmation_passed
    if final_qualified:
        final_rejection_reason = ""
    elif not base_qualified:
        final_rejection_reason = base_rejection_reason or "base_qualification_failed"
    else:
        final_rejection_reason = short_rejection_reason or "short_confirmation_failed"

    candidate.update(
        {
            "short_confirmation_variant": short_confirmation_variant,
            "volatility_20d": volatility_20d,
            "volatility_adjusted_return_10d": short_strength,
            "self_relative_short_percentile": self_relative_short_percentile,
            "short_confirmation_passed": short_confirmation_passed,
            "short_confirmation_threshold": short_confirmation_threshold,
            "absolute_floor": absolute_floor,
            "history_window": history_days,
            "rejection_reason": final_rejection_reason,
        }
    )
    candidate["qualified"] = final_qualified
    return candidate


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
