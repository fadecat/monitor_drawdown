from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any

import etf_rotation_v2_strategy as strategy
import etf_rotation_v4_1_strategy as trailing_stop
import run_etf_rotation_v2_strategy as runner


DEFAULT_OUTPUT_ROOT = Path(".test_artifacts/etf_rotation_v4_1_backtest")


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
        try:
            close_value = float(record.get("close"))
        except (TypeError, ValueError):
            continue
        if math.isfinite(close_value):
            close_by_date[date] = close_value
    return close_by_date


def _count_history_records_through_date(records: list[dict[str, Any]], signal_date: str) -> int:
    return sum(1 for record in records if str(record.get("date") or "").strip() <= signal_date)


def _clean_float(value: float) -> float:
    return round(float(value), 12)


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


def _build_defensive_holding(
    metadata_by_label: dict[str, dict[str, Any]],
    defensive_labels: set[str],
) -> dict[str, Any] | None:
    for label in defensive_labels:
        metadata = metadata_by_label.get(label)
        if not metadata:
            continue
        return {
            "label": label,
            "latest_snapshot": {"selected_primary": metadata},
            "score_25": None,
            "annualized_return_25": None,
            "r_squared_25": None,
            "return_10d": None,
            "qualified": True,
            "rejection_reason": "",
        }
    return None


def determine_trade_reason(
    previous_label: str | None,
    selected_label: str | None,
    defensive_labels: set[str],
    forced_by_trailing_stop: bool = False,
) -> str:
    if forced_by_trailing_stop:
        return "risk_to_defensive_trailing_stop"
    previous_is_defensive = bool(previous_label) and previous_label in defensive_labels
    selected_is_defensive = bool(selected_label) and selected_label in defensive_labels

    if previous_label is None:
        return "initial_entry_defensive" if selected_is_defensive else "initial_entry_risk"
    if previous_is_defensive and not selected_is_defensive:
        return "defensive_to_risk_reentry"
    if not previous_is_defensive and selected_is_defensive:
        return "risk_to_defensive_fallback"
    return "risk_to_risk_rotation"


def _build_holding_periods(daily_positions: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
            "entry_price": period["entry_price"],
            "trailing_peak": period["trailing_peak"],
            "exit_reason": period["exit_reason"],
        }

    periods: list[dict[str, Any]] = []
    current_period: dict[str, Any] | None = None
    previous_nav = 1.0

    for row in daily_positions:
        holding_symbol = str(row.get("holding_symbol") or "").strip()
        holding_name = str(row.get("holding_name") or "").strip()
        strategy_nav = float(row.get("strategy_nav") or previous_nav)
        drawdown = float(row.get("drawdown") or 0.0)

        if current_period is None or current_period["symbol"] != holding_symbol:
            if current_period is not None:
                current_period["exit_reason"] = row.get("trade_reason") or ""
                periods.append(finalize_period(current_period, previous_nav))

            current_period = {
                "symbol": holding_symbol,
                "name": holding_name,
                "start_date": row["date"],
                "end_date": row["date"],
                "start_nav": previous_nav,
                "max_drawdown_during_holding": drawdown,
                "holding_days": 1,
                "entry_price": row.get("entry_price"),
                "trailing_peak": row.get("trailing_peak"),
                "exit_reason": "",
            }
        else:
            current_period["end_date"] = row["date"]
            current_period["holding_days"] = int(current_period["holding_days"]) + 1
            current_period["max_drawdown_during_holding"] = min(
                float(current_period["max_drawdown_during_holding"]),
                drawdown,
            )
            if row.get("trailing_peak") not in {None, ""}:
                current_period["trailing_peak"] = row.get("trailing_peak")

        previous_nav = strategy_nav

    if current_period is not None:
        periods.append(finalize_period(current_period, previous_nav))

    return periods


def build_yearly_returns(daily_positions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    yearly_returns: list[dict[str, Any]] = []
    current_year: dict[str, Any] | None = None
    previous_nav = 1.0

    for row in daily_positions:
        year = str(row.get("date") or "")[:4]
        if not year:
            continue
        strategy_nav = float(row.get("strategy_nav") or previous_nav)
        if current_year is None or current_year["year"] != year:
            if current_year is not None:
                start_nav = float(current_year["start_nav"])
                end_nav = float(current_year["end_nav"])
                current_year["annual_return"] = _clean_float(end_nav / start_nav - 1.0 if start_nav > 0 else 0.0)
                yearly_returns.append(current_year)
            current_year = {
                "year": year,
                "trading_days": 0,
                "start_nav": _clean_float(previous_nav),
                "end_nav": _clean_float(strategy_nav),
            }
        current_year["trading_days"] = int(current_year["trading_days"]) + 1
        current_year["end_nav"] = _clean_float(strategy_nav)
        previous_nav = strategy_nav

    if current_year is not None:
        start_nav = float(current_year["start_nav"])
        end_nav = float(current_year["end_nav"])
        current_year["annual_return"] = _clean_float(end_nav / start_nav - 1.0 if start_nav > 0 else 0.0)
        yearly_returns.append(current_year)
    return yearly_returns


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


def replay_rotation_strategy_v4_1(
    series_by_label: dict[str, list[dict[str, Any]]],
    metadata_by_label: dict[str, dict[str, Any]],
    strategy_config: dict[str, Any],
    risk_labels: set[str],
    defensive_labels: set[str],
) -> dict[str, Any]:
    lookback_days = int(strategy_config["lookback_days"])
    short_lookback_days = int(strategy_config["short_lookback_days"])
    stop_loss_pct = float(strategy_config.get("stop_loss_pct") or 0.08)
    required_records = max(lookback_days, short_lookback_days + 1)

    series_records_by_label = {
        label: _normalize_series_records(records) for label, records in series_by_label.items()
    }
    close_by_label_and_date = {
        label: _records_to_close_by_date(records) for label, records in series_records_by_label.items()
    }
    signal_dates = sorted(
        {
            str(record["date"])
            for records in series_records_by_label.values()
            if records
            for record in records
        }
    )

    active_labels = [label for label, records in series_records_by_label.items() if records]
    start_signal_date = None
    for signal_date in signal_dates:
        if active_labels and all(
            _count_history_records_through_date(series_records_by_label.get(label, []), signal_date)
            >= required_records
            for label in active_labels
        ):
            start_signal_date = signal_date
            break
    if start_signal_date is None:
        return {
            "daily_candidate_metrics": [],
            "daily_rankings": [],
            "daily_positions": [],
            "trades": [],
            "holding_periods": [],
            "trailing_stop_events": [],
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
                "trailing_stop_count": 0,
            },
        }

    daily_candidate_metrics: list[dict[str, Any]] = []
    daily_rankings: list[dict[str, Any]] = []
    daily_positions: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    trailing_stop_events: list[dict[str, Any]] = []
    nav_values = [1.0]
    strategy_nav = 1.0
    peak_nav = 1.0
    previous_symbol: str | None = None
    previous_label: str | None = None
    previous_name: str | None = None
    trailing_stop_state: dict[str, float | bool] | None = None

    defensive_holding = _build_defensive_holding(metadata_by_label, defensive_labels)
    start_index = signal_dates.index(start_signal_date)
    for date_index in range(start_index, len(signal_dates) - 1):
        signal_date = signal_dates[date_index]
        position_date = signal_dates[date_index + 1]
        force_defensive = False

        if previous_label and previous_label not in defensive_labels and trailing_stop_state is not None:
            current_close = close_by_label_and_date.get(previous_label, {}).get(signal_date)
            if current_close is not None:
                trailing_stop_state = trailing_stop.update_trailing_stop_state(
                    trailing_stop_state,
                    close_price=current_close,
                    stop_loss_pct=stop_loss_pct,
                )
                if bool(trailing_stop_state.get("stop_triggered")):
                    force_defensive = True
                    trailing_stop_events.append(
                        {
                            "signal_date": signal_date,
                            "holding_label": previous_label,
                            "holding_symbol": previous_symbol,
                            "close": current_close,
                            "trailing_peak": trailing_stop_state.get("trailing_peak"),
                            "peak_drawdown": trailing_stop_state.get("peak_drawdown"),
                            "stop_loss_pct": stop_loss_pct,
                            "reason": "trailing_stop_triggered",
                            "action": "force_defensive_next_day",
                        }
                    )

        evaluated_candidates: list[dict[str, Any]] = []
        for label, metadata in metadata_by_label.items():
            if label not in risk_labels:
                continue
            history_records = [
                record
                for record in series_records_by_label.get(label, [])
                if str(record.get("date") or "").strip() <= signal_date
            ]
            if not history_records or str(history_records[-1].get("date") or "").strip() != signal_date:
                daily_candidate_metrics.append(
                    {
                        "signal_date": signal_date,
                        "label": label,
                        "symbol": metadata.get("code"),
                        "name": metadata.get("name"),
                        "kind": metadata.get("kind"),
                        "score_25": None,
                        "annualized_return_25": None,
                        "r_squared_25": None,
                        "return_10d": None,
                        "qualified": False,
                        "rejection_reason": "no_signal_date_close",
                    }
                )
                continue
            latest_snapshot = {
                "label": label,
                "selected_primary": metadata,
                "date": signal_date,
                "close": close_by_label_and_date.get(label, {}).get(signal_date),
            }
            candidate = strategy.build_rotation_candidate(
                latest_snapshot=latest_snapshot,
                series_records=history_records,
                strategy_config=strategy_config,
            )
            if candidate is None:
                daily_candidate_metrics.append(
                    {
                        "signal_date": signal_date,
                        "label": label,
                        "symbol": metadata.get("code"),
                        "name": metadata.get("name"),
                        "kind": metadata.get("kind"),
                        "score_25": None,
                        "annualized_return_25": None,
                        "r_squared_25": None,
                        "return_10d": None,
                        "qualified": False,
                        "rejection_reason": "insufficient_history_or_invalid_series",
                    }
                )
                continue
            evaluated_candidates.append(candidate)
            daily_candidate_metrics.append(
                {
                    "signal_date": signal_date,
                    "label": label,
                    "symbol": metadata.get("code"),
                    "name": metadata.get("name"),
                    "kind": metadata.get("kind"),
                    "score_25": candidate.get("score_25"),
                    "annualized_return_25": candidate.get("annualized_return_25"),
                    "r_squared_25": candidate.get("r_squared_25"),
                    "return_10d": candidate.get("return_10d"),
                    "qualified": candidate.get("qualified"),
                    "rejection_reason": candidate.get("rejection_reason"),
                }
            )

        ranked_candidates = strategy.rank_candidates(evaluated_candidates)
        for rank_index, candidate in enumerate(ranked_candidates, start=1):
            selected_primary = candidate.get("latest_snapshot", {}).get("selected_primary") or {}
            daily_rankings.append(
                {
                    "signal_date": signal_date,
                    "rank": rank_index,
                    "label": candidate.get("label"),
                    "symbol": selected_primary.get("code"),
                    "name": selected_primary.get("name"),
                    "score_25": candidate.get("score_25"),
                    "annualized_return_25": candidate.get("annualized_return_25"),
                    "r_squared_25": candidate.get("r_squared_25"),
                    "return_10d": candidate.get("return_10d"),
                    "is_selected": rank_index == 1 and not force_defensive,
                }
            )

        if force_defensive:
            portfolio_decision = {
                "selected_holdings": [defensive_holding] if defensive_holding else [],
                "selection_reason": "trailing_stop_defensive_asset",
                "rejected_candidates": ranked_candidates,
                "fallback_holding": defensive_holding,
            }
        else:
            portfolio_decision = strategy.select_portfolio(
                candidates=evaluated_candidates,
                strategy_config=strategy_config,
                defensive_candidate=defensive_holding,
            )

        selected_holdings = portfolio_decision.get("selected_holdings") or []
        selected = selected_holdings[0] if selected_holdings else None
        selected_snapshot = selected.get("latest_snapshot", {}) if isinstance(selected, dict) else {}
        selected_primary = selected_snapshot.get("selected_primary", {}) if isinstance(selected_snapshot, dict) else {}
        selected_label = str(selected.get("label") or "").strip() if isinstance(selected, dict) else ""
        selected_symbol = str(selected_primary.get("code") or "").strip() if isinstance(selected_primary, dict) else ""
        selected_name = str(selected_primary.get("name") or "").strip() if isinstance(selected_primary, dict) else ""

        selected_changed = selected_symbol != previous_symbol
        trade_reason = ""
        if selected_changed:
            trade_reason = determine_trade_reason(
                previous_label=previous_label,
                selected_label=selected_label,
                defensive_labels=defensive_labels,
                forced_by_trailing_stop=force_defensive,
            )
            trades.append(
                {
                    "signal_date": signal_date,
                    "from_symbol": previous_symbol or "",
                    "from_name": previous_name or "",
                    "to_symbol": selected_symbol,
                    "to_name": selected_name,
                    "reason": trade_reason,
                    "selection_reason": portfolio_decision.get("selection_reason"),
                    "rank_1_symbol": (
                        ranked_candidates[0].get("latest_snapshot", {}).get("selected_primary", {}).get("code")
                        if ranked_candidates
                        else ""
                    ),
                }
            )

        daily_return = 0.0
        signal_close = close_by_label_and_date.get(selected_label, {}).get(signal_date)
        next_close = close_by_label_and_date.get(selected_label, {}).get(position_date)
        if signal_close is not None and next_close is not None and signal_close > 0:
            daily_return = next_close / signal_close - 1.0

        if selected_changed:
            if selected_label and selected_label not in defensive_labels and next_close is not None:
                trailing_stop_state = trailing_stop.build_trailing_stop_state(entry_price=next_close)
            else:
                trailing_stop_state = None

        strategy_nav *= 1.0 + daily_return
        nav_values.append(strategy_nav)
        peak_nav = max(peak_nav, strategy_nav)
        drawdown = strategy_nav / peak_nav - 1.0 if peak_nav > 0 else 0.0
        entry_price = trailing_stop_state.get("entry_price") if trailing_stop_state is not None else None
        trailing_peak = trailing_stop_state.get("trailing_peak") if trailing_stop_state is not None else None
        peak_drawdown = trailing_stop_state.get("peak_drawdown") if trailing_stop_state is not None else None

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
                "score_25": selected.get("score_25") if isinstance(selected, dict) else None,
                "annualized_return_25": selected.get("annualized_return_25") if isinstance(selected, dict) else None,
                "r_squared_25": selected.get("r_squared_25") if isinstance(selected, dict) else None,
                "return_10d": selected.get("return_10d") if isinstance(selected, dict) else None,
                "selection_reason": portfolio_decision.get("selection_reason"),
                "trade_reason": trade_reason,
                "entry_price": entry_price,
                "trailing_peak": trailing_peak,
                "peak_drawdown": peak_drawdown,
            }
        )
        previous_symbol = selected_symbol
        previous_label = selected_label
        previous_name = selected_name

    holding_periods = _build_holding_periods(daily_positions)
    trading_days = len(daily_positions)
    annualized_return = strategy_nav ** (252 / trading_days) - 1.0 if trading_days else 0.0
    win_rate = (
        sum(1 for row in holding_periods if float(row.get("period_return") or 0.0) > 0) / len(holding_periods)
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
        "trailing_stop_count": len(trailing_stop_events),
    }

    return {
        "daily_candidate_metrics": daily_candidate_metrics,
        "daily_rankings": daily_rankings,
        "daily_positions": daily_positions,
        "trades": trades,
        "holding_periods": holding_periods,
        "trailing_stop_events": trailing_stop_events,
        "summary": summary,
    }


def build_symbol_contributions(holding_periods: list[dict[str, Any]]) -> list[dict[str, Any]]:
    aggregated: dict[tuple[str, str], dict[str, Any]] = {}
    for row in holding_periods:
        symbol = str(row.get("symbol") or "").strip() or "CASH"
        name = str(row.get("name") or "").strip() or "空仓"
        key = (symbol, name)
        contribution = float(row.get("contribution_to_total_return") or 0.0)
        holding_days = int(row.get("holding_days") or 0)
        if key not in aggregated:
            aggregated[key] = {
                "symbol": symbol,
                "name": name,
                "holding_periods": 0,
                "holding_days": 0,
                "total_contribution": 0.0,
            }
        aggregated[key]["holding_periods"] = int(aggregated[key]["holding_periods"]) + 1
        aggregated[key]["holding_days"] = int(aggregated[key]["holding_days"]) + holding_days
        aggregated[key]["total_contribution"] = float(aggregated[key]["total_contribution"]) + contribution
    return sorted(aggregated.values(), key=lambda item: (-float(item["total_contribution"]), str(item["symbol"])))


def run_backtest(
    config_path: Path | str = runner.DEFAULT_CONFIG_PATH,
    source_output_root: Path | str = runner.SOURCE_OUTPUT_ROOT,
    output_root: Path | str = DEFAULT_OUTPUT_ROOT,
    stop_loss_pct: float | None = None,
) -> dict[str, Any]:
    config = runner.load_rotation_config(config_path)
    strategy_config = dict(config.get("strategy") or {})
    if stop_loss_pct is not None:
        strategy_config["stop_loss_pct"] = float(stop_loss_pct)
    else:
        strategy_config["stop_loss_pct"] = float(strategy_config.get("stop_loss_pct") or 0.08)

    resolved_source_root = Path(source_output_root)
    resolved_output_root = Path(output_root)
    resolved_output_root.mkdir(parents=True, exist_ok=True)
    risk_targets = list(config.get("risk_targets") or [])
    defensive_targets = list(config.get("defensive_targets") or [])
    risk_labels = {str(target.get("label") or "").strip() for target in risk_targets if str(target.get("label") or "").strip()}
    defensive_labels = {
        str(target.get("label") or "").strip()
        for target in defensive_targets
        if str(target.get("label") or "").strip()
    }
    metadata_by_label: dict[str, dict[str, Any]] = {}
    series_by_label: dict[str, list[dict[str, Any]]] = {}
    for target in risk_targets + defensive_targets:
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
        series_by_label[label] = runner.load_series_records(metadata, resolved_source_root)

    result = replay_rotation_strategy_v4_1(
        series_by_label=series_by_label,
        metadata_by_label=metadata_by_label,
        strategy_config=strategy_config,
        risk_labels=risk_labels,
        defensive_labels=defensive_labels,
    )
    yearly_returns = build_yearly_returns(result["daily_positions"])
    symbol_contributions = build_symbol_contributions(result["holding_periods"])
    _write_csv(resolved_output_root / "daily_candidate_metrics.csv", result["daily_candidate_metrics"])
    _write_csv(resolved_output_root / "daily_rankings.csv", result["daily_rankings"])
    _write_csv(resolved_output_root / "daily_positions.csv", result["daily_positions"])
    _write_csv(resolved_output_root / "trades.csv", result["trades"])
    _write_csv(resolved_output_root / "holding_periods.csv", result["holding_periods"])
    _write_csv(resolved_output_root / "trailing_stop_events.csv", result["trailing_stop_events"])
    _write_csv(resolved_output_root / "yearly_returns.csv", yearly_returns)
    _write_csv(resolved_output_root / "symbol_contributions.csv", symbol_contributions)

    summary_payload = result["summary"]
    summary_lines = [
        "# ETF Rotation Backtest V4.1",
        "",
        f"- stop_loss_pct={float(strategy_config['stop_loss_pct']):.4f}",
        f"- start_date={summary_payload['start_date'] or 'none'}",
        f"- end_date={summary_payload['end_date'] or 'none'}",
        f"- trading_days={summary_payload['trading_days']}",
        f"- trade_count={summary_payload['trade_count']}",
        f"- trailing_stop_count={summary_payload['trailing_stop_count']}",
        f"- final_nav={float(summary_payload['final_nav']):.6f}",
        f"- total_return={float(summary_payload['total_return']):.6f}",
        f"- annualized_return={float(summary_payload['annualized_return']):.6f}",
        f"- max_drawdown={float(summary_payload['max_drawdown']):.6f}",
        f"- win_rate={float(summary_payload['win_rate']):.6f}",
        "",
    ]
    (resolved_output_root / "backtest_summary.md").write_text("\n".join(summary_lines), encoding="utf-8")
    return {
        "config": config,
        "yearly_returns": yearly_returns,
        "symbol_contributions": symbol_contributions,
        **result,
    }


if __name__ == "__main__":
    run_backtest()

