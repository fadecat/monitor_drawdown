from __future__ import annotations

import math


def build_trailing_stop_state(entry_price: float) -> dict[str, float | bool]:
    entry_price_value = float(entry_price)
    return {
        "entry_price": entry_price_value,
        "trailing_peak": entry_price_value,
        "peak_drawdown": 0.0,
        "stop_triggered": False,
    }


def update_trailing_stop_state(
    state: dict[str, float | bool],
    close_price: float,
    stop_loss_pct: float = 0.08,
) -> dict[str, float | bool]:
    close_price_value = float(close_price)
    previous_peak = float(state.get("trailing_peak") or 0.0)
    trailing_peak = max(previous_peak, close_price_value)
    peak_drawdown = close_price_value / trailing_peak - 1.0 if trailing_peak > 0 else 0.0
    if not math.isfinite(peak_drawdown):
        peak_drawdown = 0.0

    updated = dict(state)
    updated["trailing_peak"] = trailing_peak
    updated["peak_drawdown"] = peak_drawdown
    updated["stop_triggered"] = peak_drawdown <= -float(stop_loss_pct)
    return updated

