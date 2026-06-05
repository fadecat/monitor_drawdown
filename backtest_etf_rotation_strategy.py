from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any

import etf_rotation_strategy as strategy
import run_etf_rotation_strategy as runner


DEFAULT_OUTPUT_ROOT = Path(".test_artifacts/etf_rotation_backtest")


def _normalize_series_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized_records: list[dict[str, Any]] = []
    for record in records:
        date = str(record.get("date") or "").strip()
        if not date:
            continue
        normalized_record = dict(record)
        normalized_record["date"] = date
        normalized_records.append(normalized_record)
    return sorted(normalized_records, key=lambda item: str(item["date"]))


def _records_to_close_by_date(records: list[dict[str, Any]]) -> dict[str, float]:
    close_by_date: dict[str, float] = {}
    for record in records:
        date = str(record.get("date") or "").strip()
        if not date:
            continue

        raw_close = record.get("close")
        try:
            close_value = float(raw_close)
        except (TypeError, ValueError):
            continue

        if not math.isfinite(close_value):
            continue
        close_by_date[date] = close_value
    return close_by_date


def _calculate_max_drawdown(nav_values: list[float]) -> float:
    peak = None
    max_drawdown = 0.0
    for value in nav_values:
        if not math.isfinite(value):
            continue
        if peak is None or value > peak:
            peak = value
            continue
        if peak <= 0:
            continue
        drawdown = value / peak - 1.0
        if drawdown < max_drawdown:
            max_drawdown = drawdown
    return max_drawdown


def _calculate_history_return(
    records: list[dict[str, Any]],
    lookback_days: int,
) -> float | None:
    if len(records) < lookback_days + 1:
        return None

    closes: list[float] = []
    for row in records[-(lookback_days + 1):]:
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

    return strategy.calculate_lookback_return(
        closes=closes,
        lookback_days=lookback_days,
    )


def _find_next_date(dates: list[str], current_date: str) -> str | None:
    for date_text in dates:
        if date_text > current_date:
            return date_text
    return None


def _build_holding_periods(
    daily_positions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not daily_positions:
        return []

    def finalize_period(period: dict[str, Any], ending_nav: float) -> dict[str, Any]:
        start_nav = float(period["start_nav"])
        period_return = ending_nav / start_nav - 1.0 if start_nav > 0 else 0.0
        return {
            "start_date": period["start_date"],
            "end_date": period["end_date"],
            "symbol": period["symbol"],
            "name": period["name"],
            "holding_days": period["holding_days"],
            "period_return": period_return,
            "contribution_to_total_return": ending_nav - start_nav,
            "max_drawdown_during_holding": period["max_drawdown_during_holding"],
        }

    periods: list[dict[str, Any]] = []
    current_period: dict[str, Any] | None = None
    previous_nav = 1.0

    for row in daily_positions:
        holding_symbol = row.get("holding_symbol")
        holding_name = row.get("holding_name")
        strategy_nav = float(row.get("strategy_nav") or previous_nav)
        drawdown = float(row.get("drawdown") or 0.0)

        if current_period is None or current_period["holding_symbol"] != holding_symbol:
            if current_period is not None:
                periods.append(finalize_period(current_period, previous_nav))

            current_period = {
                "holding_symbol": holding_symbol,
                "symbol": holding_symbol,
                "name": holding_name,
                "start_date": row["date"],
                "end_date": row["date"],
                "start_nav": previous_nav,
                "max_drawdown_during_holding": drawdown,
                "holding_days": 1,
            }
        else:
            current_period["end_date"] = row["date"]
            current_period["holding_days"] = int(current_period["holding_days"]) + 1
            current_period["max_drawdown_during_holding"] = min(
                float(current_period["max_drawdown_during_holding"]),
                drawdown,
            )

        previous_nav = strategy_nav

    if current_period is not None:
        periods.append(finalize_period(current_period, previous_nav))

    return periods


def replay_rotation_strategy(
    series_by_label: dict[str, list[dict[str, Any]]],
    metadata_by_label: dict[str, dict[str, Any]],
    strategy_config: dict[str, Any],
) -> dict[str, Any]:
    lookback_days = int(strategy_config["lookback_days"])
    series_records_by_label = {
        label: _normalize_series_records(records)
        for label, records in series_by_label.items()
    }
    close_by_label_and_date = {
        label: _records_to_close_by_date(records)
        for label, records in series_records_by_label.items()
    }
    signal_dates = sorted(
        {
            str(record["date"])
            for records in series_records_by_label.values()
            if records
            for record in records
        }
    )

    daily_rankings: list[dict[str, Any]] = []
    daily_positions: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    nav_values = [1.0]
    strategy_nav = 1.0
    peak_nav = 1.0
    previous_symbol: str | None = None
    previous_label: str | None = None
    previous_name: str | None = None

    start_signal_date: str | None = None
    for signal_date in signal_dates:
        if any(
            signal_date in close_by_label_and_date.get(label, {})
            and len(
                [
                    record
                    for record in series_records_by_label.get(label, [])
                    if str(record.get("date") or "") <= signal_date
                ]
            )
            >= lookback_days + 1
            for label in series_records_by_label
        ):
            start_signal_date = signal_date
            break

    if start_signal_date is None:
        return {
            "daily_rankings": [],
            "daily_positions": [],
            "trades": [],
            "holding_periods": [],
            "summary": {
                "start_date": None,
                "end_date": None,
                "trading_days": 0,
                "trade_count": 0,
                "final_nav": 1.0,
                "total_return": 0.0,
                "annualized_return": 0.0,
                "max_drawdown": 0.0,
                "win_rate": 0.0,
            },
        }

    start_index = signal_dates.index(start_signal_date)
    for date_index in range(start_index, len(signal_dates) - 1):
        signal_date = signal_dates[date_index]
        default_position_date = signal_dates[date_index + 1]
        candidates: list[dict[str, Any]] = []

        for label, metadata in metadata_by_label.items():
            series_records = series_records_by_label.get(label, [])
            history_records = [
                record
                for record in series_records
                if str(record.get("date") or "").strip() <= signal_date
            ]
            if not history_records:
                continue
            if str(history_records[-1].get("date") or "").strip() != signal_date:
                continue
            if signal_date not in close_by_label_and_date.get(label, {}):
                continue

            latest_snapshot = {
                "label": label,
                "selected_primary": metadata,
                "close": close_by_label_and_date[label][signal_date],
                "date": signal_date,
            }
            candidate = strategy.build_rotation_candidate(
                latest_snapshot=latest_snapshot,
                series_records=history_records,
                strategy_config=strategy_config,
            )
            if candidate is None:
                continue
            candidates.append(candidate)

        ranked_candidates = strategy.rank_candidates(candidates)
        for rank_index, candidate in enumerate(ranked_candidates, start=1):
            selected_primary = candidate.get("latest_snapshot", {}).get("selected_primary") or {}
            daily_rankings.append(
                {
                    "date": signal_date,
                    "rank": rank_index,
                    "label": candidate.get("label"),
                    "symbol": selected_primary.get("code"),
                    "name": selected_primary.get("name"),
                    "return_20d": candidate.get("return_20d"),
                    "is_selected": rank_index <= max(int(strategy_config.get("holdings_num") or 1), 1),
                }
            )

        portfolio_decision = strategy.select_portfolio(
            candidates=ranked_candidates,
            strategy_config=strategy_config,
        )
        selected_holdings = portfolio_decision.get("selected_holdings") or []
        selected = selected_holdings[0] if selected_holdings else None
        selected_snapshot = selected.get("latest_snapshot", {}) if isinstance(selected, dict) else {}
        selected_primary = (
            selected_snapshot.get("selected_primary", {})
            if isinstance(selected_snapshot, dict)
            else {}
        )
        selected_label = (
            str(selected.get("label") or "").strip()
            if isinstance(selected, dict)
            else ""
        )
        selected_symbol = (
            str(selected_primary.get("code") or "").strip()
            if isinstance(selected_primary, dict)
            else ""
        )
        selected_name = (
            str(selected_primary.get("name") or "").strip()
            if isinstance(selected_primary, dict)
            else ""
        )

        previous_return = ""
        if previous_label:
            previous_history = [
                record
                for record in series_records_by_label.get(previous_label, [])
                if str(record.get("date") or "").strip() <= signal_date
            ]
            if (
                previous_history
                and str(previous_history[-1].get("date") or "").strip() == signal_date
            ):
                computed_return = _calculate_history_return(
                    previous_history,
                    lookback_days=lookback_days,
                )
                if computed_return is not None:
                    previous_return = computed_return

        if not selected_label or not selected_symbol:
            if previous_symbol:
                trades.append(
                    {
                        "signal_date": signal_date,
                        "from_symbol": previous_symbol or "",
                        "from_name": previous_name or "",
                        "to_symbol": "",
                        "to_name": "",
                        "reason": "no_qualified_candidate",
                        "from_20d_return": previous_return,
                        "to_20d_return": "",
                        "rank_1_symbol": "",
                    }
                )

            nav_values.append(strategy_nav)
            peak_nav = max(peak_nav, strategy_nav)
            drawdown = strategy_nav / peak_nav - 1.0 if peak_nav > 0 else 0.0
            daily_positions.append(
                {
                    "date": default_position_date,
                    "signal_date": signal_date,
                    "holding_label": "",
                    "holding_symbol": "",
                    "holding_name": "",
                    "daily_return": 0.0,
                    "strategy_nav": strategy_nav,
                    "drawdown": drawdown,
                    "selected_20d_return": "",
                    "selection_reason": portfolio_decision.get("selection_reason"),
                }
            )
            previous_symbol = None
            previous_label = None
            previous_name = None
            continue

        if selected_symbol != previous_symbol:
            trades.append(
                {
                    "signal_date": signal_date,
                    "from_symbol": previous_symbol or "",
                    "from_name": previous_name or "",
                    "to_symbol": selected_symbol,
                    "to_name": selected_name,
                    "reason": "initial_entry" if previous_symbol is None else "top_rank_changed",
                    "from_20d_return": previous_return,
                    "to_20d_return": selected.get("return_20d"),
                    "rank_1_symbol": selected_symbol,
                }
            )

        symbol_dates = sorted(close_by_label_and_date.get(selected_label, {}))
        position_date = _find_next_date(symbol_dates, signal_date) or default_position_date
        daily_return = 0.0
        signal_close = close_by_label_and_date.get(selected_label, {}).get(signal_date)
        next_close = close_by_label_and_date.get(selected_label, {}).get(position_date)
        if signal_close is not None and next_close is not None and signal_close > 0:
            daily_return = next_close / signal_close - 1.0

        strategy_nav *= 1.0 + daily_return
        nav_values.append(strategy_nav)
        peak_nav = max(peak_nav, strategy_nav)
        drawdown = strategy_nav / peak_nav - 1.0 if peak_nav > 0 else 0.0

        daily_positions.append(
            {
                "date": position_date,
                "signal_date": signal_date,
                "holding_label": selected_label,
                "holding_symbol": selected_symbol,
                "holding_name": selected_name,
                "daily_return": daily_return,
                "strategy_nav": strategy_nav,
                "drawdown": drawdown,
                "selected_20d_return": selected.get("return_20d") if isinstance(selected, dict) else None,
                "selection_reason": portfolio_decision.get("selection_reason"),
            }
        )
        previous_symbol = selected_symbol
        previous_label = selected_label
        previous_name = selected_name

    holding_periods = _build_holding_periods(daily_positions)
    trading_days = len(daily_positions)
    annualized_return = strategy_nav ** (252 / trading_days) - 1.0 if trading_days else 0.0
    win_rate = (
        sum(1 for row in holding_periods if float(row.get("period_return") or 0.0) > 0)
        / len(holding_periods)
        if holding_periods
        else 0.0
    )
    summary = {
        "start_date": daily_positions[0]["date"] if daily_positions else None,
        "end_date": daily_positions[-1]["date"] if daily_positions else None,
        "trading_days": trading_days,
        "trade_count": len(trades),
        "final_nav": strategy_nav,
        "total_return": strategy_nav - 1.0,
        "annualized_return": annualized_return,
        "max_drawdown": _calculate_max_drawdown(nav_values),
        "win_rate": win_rate,
    }

    return {
        "daily_rankings": daily_rankings,
        "daily_positions": daily_positions,
        "trades": trades,
        "holding_periods": holding_periods,
        "summary": summary,
    }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return

    fieldnames: list[str] = list(rows[0].keys())
    for row in rows[1:]:
        for key in row.keys():
            if key not in fieldnames:
                fieldnames.append(key)

    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def run_backtest(
    config_path: Path | str = runner.DEFAULT_CONFIG_PATH,
    source_output_root: Path | str = runner.SOURCE_OUTPUT_ROOT,
    output_root: Path | str = DEFAULT_OUTPUT_ROOT,
) -> dict[str, Any]:
    config = runner.load_rotation_config(config_path)
    resolved_source_root = Path(source_output_root)
    resolved_output_root = Path(output_root)
    resolved_output_root.mkdir(parents=True, exist_ok=True)

    targets = list(config.get("targets") or []) + list(config.get("defensive_targets") or [])
    metadata_by_label: dict[str, dict[str, Any]] = {}
    series_by_label: dict[str, list[dict[str, Any]]] = {}

    for target in targets:
        label = str(target.get("label") or "").strip()
        if not label:
            continue
        metadata = {
            "label": label,
            "code": str(target.get("code") or "").strip(),
            "kind": str(target.get("kind") or "").strip(),
            "name": str(target.get("name") or target.get("label") or "").strip(),
        }
        metadata_by_label[label] = metadata
        series_by_label[label] = runner.load_series_records(
            selected_primary=metadata,
            source_output_root=resolved_source_root,
        )

    result = replay_rotation_strategy(
        series_by_label=series_by_label,
        metadata_by_label=metadata_by_label,
        strategy_config=dict(config.get("strategy") or {}),
    )

    _write_csv(resolved_output_root / "trades.csv", result["trades"])
    _write_csv(resolved_output_root / "daily_positions.csv", result["daily_positions"])
    _write_csv(resolved_output_root / "daily_rankings.csv", result["daily_rankings"])
    _write_csv(resolved_output_root / "holding_periods.csv", result["holding_periods"])

    summary_payload = result["summary"]
    summary_lines = [
        "# ETF Rotation Backtest",
        "",
        f"- start_date={summary_payload['start_date'] or 'none'}",
        f"- end_date={summary_payload['end_date'] or 'none'}",
        f"- trading_days={summary_payload['trading_days']}",
        f"- trade_count={summary_payload['trade_count']}",
        f"- final_nav={float(summary_payload['final_nav']):.6f}",
        f"- total_return={float(summary_payload['total_return']):.6f}",
        f"- annualized_return={float(summary_payload['annualized_return']):.6f}",
        f"- max_drawdown={float(summary_payload['max_drawdown']):.6f}",
        f"- win_rate={float(summary_payload['win_rate']):.6f}",
        "",
    ]
    (resolved_output_root / "backtest_summary.md").write_text(
        "\n".join(summary_lines),
        encoding="utf-8",
    )

    return {
        "config": config,
        **result,
    }


if __name__ == "__main__":
    run_backtest()
