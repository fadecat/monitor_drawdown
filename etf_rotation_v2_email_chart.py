from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import analyze_etf_com_cn_period_returns as etf_analysis


BENCHMARK_CODE = "510300"
BENCHMARK_LABEL = "沪深300ETF"
BENCHMARK_CHART_CID = "etf_rotation_v2_equity_chart"


def normalize_benchmark_nav_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for row in rows:
        date_text = str(row.get("trdDt") or "").strip()
        raw_nav = row.get("adjUnitNav")
        if not date_text or raw_nav in {None, ""}:
            continue
        try:
            nav = float(raw_nav)
        except (TypeError, ValueError):
            continue
        deduped[date_text] = {"date": date_text, "benchmark_nav": nav}
    return [deduped[key] for key in sorted(deduped)]


def load_benchmark_series(output_dir: Path, code: str = BENCHMARK_CODE) -> list[dict[str, Any]]:
    rows = etf_analysis.load_nav_rows(code)
    normalized = normalize_benchmark_nav_rows([row for row in rows if isinstance(row, dict)])
    benchmark_dir = output_dir / "benchmark"
    benchmark_dir.mkdir(parents=True, exist_ok=True)
    (benchmark_dir / f"etf_{code}.json").write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return normalized


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _clean_float(value: float) -> float:
    return round(float(value), 12)


def _max_drawdown(values: list[float]) -> float:
    if not values:
        return 0.0
    peak = values[0]
    max_drawdown = 0.0
    for value in values:
        if value > peak:
            peak = value
        if peak > 0:
            max_drawdown = min(max_drawdown, value / peak - 1.0)
    return _clean_float(max_drawdown)


def build_relative_return_curve(
    *,
    strategy_rows: list[dict[str, Any]],
    benchmark_rows: list[dict[str, Any]],
    window_days: int = 365,
) -> dict[str, Any]:
    strategy_by_date = {
        str(row.get("date") or "").strip(): float(row["strategy_nav"])
        for row in strategy_rows
        if str(row.get("date") or "").strip() and row.get("strategy_nav") not in {None, ""}
    }
    benchmark_by_date = {
        str(row.get("date") or "").strip(): float(row["benchmark_nav"])
        for row in benchmark_rows
        if str(row.get("date") or "").strip() and row.get("benchmark_nav") not in {None, ""}
    }
    common_dates = sorted(set(strategy_by_date) & set(benchmark_by_date))
    if not common_dates:
        return {"benchmark_label": BENCHMARK_LABEL, "points": [], "summary": {}}

    end_date = _parse_date(common_dates[-1])
    start_cutoff = end_date - timedelta(days=window_days)
    window_dates = [item for item in common_dates if _parse_date(item) >= start_cutoff]
    if not window_dates:
        window_dates = common_dates

    base_strategy = strategy_by_date[window_dates[0]]
    base_benchmark = benchmark_by_date[window_dates[0]]
    points = []
    for item in window_dates:
        strategy_nav = strategy_by_date[item]
        benchmark_nav = benchmark_by_date[item]
        points.append(
            {
                "date": item,
                "strategy_return": _clean_float(strategy_nav / base_strategy - 1.0),
                "benchmark_return": _clean_float(benchmark_nav / base_benchmark - 1.0),
                "strategy_nav": strategy_nav,
                "benchmark_nav": benchmark_nav,
            }
        )

    strategy_returns = [float(point["strategy_return"]) for point in points]
    summary = {
        "start_date": points[0]["date"],
        "end_date": points[-1]["date"],
        "strategy_period_return": _clean_float(points[-1]["strategy_return"]),
        "benchmark_period_return": _clean_float(points[-1]["benchmark_return"]),
        "excess_return": _clean_float(points[-1]["strategy_return"] - points[-1]["benchmark_return"]),
        "strategy_max_drawdown": _max_drawdown([1.0 + value for value in strategy_returns]),
    }
    return {"benchmark_label": BENCHMARK_LABEL, "points": points, "summary": summary}
