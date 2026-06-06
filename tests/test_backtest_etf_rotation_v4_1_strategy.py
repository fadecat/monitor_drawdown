from __future__ import annotations

import backtest_etf_rotation_v4_1_strategy as module


def _make_series(label: str, closes: list[float]) -> list[dict[str, float | str]]:
    return [
        {"date": f"2026-04-{index + 1:03d}", "close": float(close), "label": label}
        for index, close in enumerate(closes)
    ]


def _base_strategy_config(stop_loss_pct: float = 0.10) -> dict[str, float | int]:
    return {
        "lookback_days": 25,
        "short_lookback_days": 10,
        "annualization_days": 250,
        "weight_start": 1.0,
        "weight_end": 2.0,
        "holdings_num": 1,
        "stop_loss_pct": stop_loss_pct,
    }


def _sample_replay_result() -> dict:
    risk_a_closes = [100.0 + index for index in range(25)] + [
        130.0,
        135.0,
        140.0,
        125.0,
        126.0,
        127.0,
        128.0,
        129.0,
        130.0,
        131.0,
    ]
    risk_b_closes = [90.0 + 0.8 * index for index in range(35)]
    defensive_closes = [100.0 + 0.01 * index for index in range(35)]

    return module.replay_rotation_strategy_v4_1(
        series_by_label={
            "A": _make_series("A", risk_a_closes),
            "B": _make_series("B", risk_b_closes),
            "银华日利ETF": _make_series("银华日利ETF", defensive_closes),
        },
        metadata_by_label={
            "A": {"label": "A", "code": "510001", "kind": "etf", "name": "AETF"},
            "B": {"label": "B", "code": "510002", "kind": "etf", "name": "BETF"},
            "银华日利ETF": {
                "label": "银华日利ETF",
                "code": "511880",
                "kind": "etf",
                "name": "银华日利ETF",
            },
        },
        strategy_config=_base_strategy_config(stop_loss_pct=0.10),
        risk_labels={"A", "B"},
        defensive_labels={"银华日利ETF"},
    )


def test_replay_rotation_v4_1_switches_to_defense_after_trailing_stop():
    result = _sample_replay_result()

    stopped_row = next(row for row in result["daily_positions"] if row["signal_date"] == "2026-04-029")

    assert result["daily_positions"][0]["holding_symbol"] == "510001"
    assert stopped_row["holding_symbol"] == "511880"
    assert stopped_row["selection_reason"] == "trailing_stop_defensive_asset"
    assert result["trailing_stop_events"][0]["reason"] == "trailing_stop_triggered"
    assert result["trailing_stop_events"][0]["signal_date"] == "2026-04-029"
    assert result["trailing_stop_events"][0]["action"] == "force_defensive_next_day"


def test_replay_rotation_v4_1_resets_trailing_peak_on_new_position():
    result = _sample_replay_result()
    risk_periods = [period for period in result["holding_periods"] if period["symbol"] == "510001"]

    assert len(risk_periods) >= 2
    assert risk_periods[0]["entry_price"] == 130.0
    assert risk_periods[0]["trailing_peak"] == 140.0
    assert risk_periods[1]["entry_price"] == 127.0
    assert risk_periods[1]["trailing_peak"] == 128.0
    assert risk_periods[1]["entry_price"] != 140.0


def test_replay_rotation_v4_1_trigger_day_skips_same_day_rerank_and_forces_defense_next_day():
    result = _sample_replay_result()
    stopped_row = next(row for row in result["daily_positions"] if row["signal_date"] == "2026-04-029")
    stopped_ranking_rows = [
        row for row in result["daily_rankings"] if row["signal_date"] == "2026-04-029"
    ]

    assert stopped_ranking_rows
    assert stopped_ranking_rows[0]["symbol"] != "511880"
    assert stopped_row["holding_symbol"] == "511880"
    assert stopped_row["selection_reason"] == "trailing_stop_defensive_asset"
