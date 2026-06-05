import shutil
from pathlib import Path

import backtest_etf_rotation_strategy as module


def _make_workspace_tmp(name: str) -> Path:
    root = Path(".test_artifacts/test_backtest_etf_rotation_strategy") / name
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _make_series(label: str, closes: list[float]) -> list[dict[str, float | str]]:
    return [
        {"date": f"2026-02-{index + 1:02d}", "close": float(close), "label": label}
        for index, close in enumerate(closes)
    ]


def _make_dated_series(
    label: str,
    date_and_closes: list[tuple[str, float]],
) -> list[dict[str, float | str]]:
    return [
        {"date": date_text, "close": float(close), "label": label}
        for date_text, close in date_and_closes
    ]


def test_replay_rotation_strategy_switches_when_new_leader_appears():
    series_by_label = {
        "A": _make_series("A", [100 + index for index in range(21)] + [121, 121, 121]),
        "B": _make_series("B", [100 + index * 0.5 for index in range(21)] + [130, 131, 132]),
    }
    metadata_by_label = {
        "A": {"label": "A", "code": "510001", "kind": "etf", "name": "AETF"},
        "B": {"label": "B", "code": "510002", "kind": "etf", "name": "BETF"},
    }

    result = module.replay_rotation_strategy(
        series_by_label=series_by_label,
        metadata_by_label=metadata_by_label,
        strategy_config={"lookback_days": 20, "holdings_num": 1},
    )

    trade_targets = [trade["to_symbol"] for trade in result["trades"]]

    assert trade_targets[:2] == ["510001", "510002"]


def test_replay_rotation_strategy_lets_511880_win_from_unified_pool():
    series_by_label = {
        "风险A": _make_series("风险A", [120 - index for index in range(24)]),
        "银华日利ETF": _make_series("银华日利ETF", [100 + index * 0.02 for index in range(24)]),
    }
    metadata_by_label = {
        "风险A": {"label": "风险A", "code": "510001", "kind": "etf", "name": "风险A"},
        "银华日利ETF": {"label": "银华日利ETF", "code": "511880", "kind": "etf", "name": "银华日利ETF"},
    }

    result = module.replay_rotation_strategy(
        series_by_label=series_by_label,
        metadata_by_label=metadata_by_label,
        strategy_config={"lookback_days": 20, "holdings_num": 1},
    )

    assert result["daily_positions"][0]["holding_symbol"] == "511880"


def test_replay_rotation_strategy_uses_next_day_returns():
    series_by_label = {
        "A": _make_series("A", [100 + index for index in range(21)] + [126, 126]),
        "B": _make_series("B", [100 + index * 0.1 for index in range(23)]),
    }
    metadata_by_label = {
        "A": {"label": "A", "code": "510001", "kind": "etf", "name": "AETF"},
        "B": {"label": "B", "code": "510002", "kind": "etf", "name": "BETF"},
    }

    result = module.replay_rotation_strategy(
        series_by_label=series_by_label,
        metadata_by_label=metadata_by_label,
        strategy_config={"lookback_days": 20, "holdings_num": 1},
    )

    assert round(result["daily_positions"][0]["daily_return"], 4) == 0.0500
    assert round(result["daily_positions"][0]["strategy_nav"], 4) == 1.0500


def test_replay_rotation_strategy_does_not_drop_signal_dates_for_other_symbols():
    series_by_label = {
        "A": _make_series("A", [100 + index for index in range(24)]),
        "B": _make_dated_series(
            "B",
            [
                (f"2026-02-{index:02d}", 100 + (index - 1) * 0.2)
                for index in range(1, 22)
            ]
            + [("2026-02-23", 104.2), ("2026-02-24", 104.4)],
        ),
    }
    metadata_by_label = {
        "A": {"label": "A", "code": "510001", "kind": "etf", "name": "AETF"},
        "B": {"label": "B", "code": "510002", "kind": "etf", "name": "BETF"},
    }

    result = module.replay_rotation_strategy(
        series_by_label=series_by_label,
        metadata_by_label=metadata_by_label,
        strategy_config={"lookback_days": 20, "holdings_num": 1},
    )

    assert any(
        row["signal_date"] == "2026-02-22" and row["holding_symbol"] == "510001"
        for row in result["daily_positions"]
    )


def test_replay_rotation_strategy_ignores_empty_series_without_crashing():
    series_by_label = {
        "A": _make_series("A", [100 + index for index in range(24)]),
        "空仓标的": [],
    }
    metadata_by_label = {
        "A": {"label": "A", "code": "510001", "kind": "etf", "name": "AETF"},
        "空仓标的": {
            "label": "空仓标的",
            "code": "510099",
            "kind": "etf",
            "name": "EmptyETF",
        },
    }

    result = module.replay_rotation_strategy(
        series_by_label=series_by_label,
        metadata_by_label=metadata_by_label,
        strategy_config={"lookback_days": 20, "holdings_num": 1},
    )

    assert result["daily_positions"]
    assert result["daily_positions"][0]["holding_symbol"] == "510001"


def test_replay_rotation_strategy_populates_from_20d_return_on_switch():
    series_by_label = {
        "A": _make_series("A", [100 + index for index in range(21)] + [121, 121, 121]),
        "B": _make_series("B", [100 + index * 0.5 for index in range(21)] + [130, 131, 132]),
    }
    metadata_by_label = {
        "A": {"label": "A", "code": "510001", "kind": "etf", "name": "AETF"},
        "B": {"label": "B", "code": "510002", "kind": "etf", "name": "BETF"},
    }

    result = module.replay_rotation_strategy(
        series_by_label=series_by_label,
        metadata_by_label=metadata_by_label,
        strategy_config={"lookback_days": 20, "holdings_num": 1},
    )

    assert round(float(result["trades"][1]["from_20d_return"]), 4) == 0.1980


def test_replay_rotation_strategy_waits_until_all_non_empty_series_are_mature():
    series_by_label = {
        "A": _make_dated_series(
            "A",
            [(f"2026-02-{index:02d}", 100.0 + index) for index in range(1, 11)],
        ),
        "B": _make_dated_series(
            "B",
            [(f"2026-02-{index:02d}", 200.0 + index) for index in range(5, 11)],
        ),
    }
    metadata_by_label = {
        "A": {"label": "A", "code": "510001", "kind": "etf", "name": "AETF"},
        "B": {"label": "B", "code": "510002", "kind": "etf", "name": "BETF"},
    }

    result = module.replay_rotation_strategy(
        series_by_label=series_by_label,
        metadata_by_label=metadata_by_label,
        strategy_config={"lookback_days": 3, "holdings_num": 1},
    )

    assert result["daily_positions"][0]["signal_date"] == "2026-02-08"
    assert result["daily_positions"][0]["date"] == "2026-02-09"


def test_replay_rotation_strategy_records_explicit_no_candidate_days():
    series_by_label = {
        "A": _make_series("A", [120 - index for index in range(24)]),
    }
    metadata_by_label = {
        "A": {"label": "A", "code": "510001", "kind": "etf", "name": "AETF"},
    }

    result = module.replay_rotation_strategy(
        series_by_label=series_by_label,
        metadata_by_label=metadata_by_label,
        strategy_config={"lookback_days": 20, "holdings_num": 1},
    )

    assert [row["signal_date"] for row in result["daily_positions"]] == [
        "2026-02-21",
        "2026-02-22",
        "2026-02-23",
    ]
    assert all(row["holding_symbol"] == "" for row in result["daily_positions"])
    assert all(row["daily_return"] == 0.0 for row in result["daily_positions"])
    assert all(row["strategy_nav"] == 1.0 for row in result["daily_positions"])


def test_replay_rotation_strategy_keeps_global_position_dates_monotonic():
    series_by_label = {
        "A": _make_dated_series(
            "A",
            [(f"2026-02-{index:02d}", 99 + index) for index in range(1, 23)]
            + [("2026-02-24", 140.0)],
        ),
        "B": _make_dated_series(
            "B",
            [(f"2026-02-{index:02d}", 100.0 + (index - 1) * 0.1) for index in range(1, 25)],
        ),
    }
    metadata_by_label = {
        "A": {"label": "A", "code": "510001", "kind": "etf", "name": "AETF"},
        "B": {"label": "B", "code": "510002", "kind": "etf", "name": "BETF"},
    }

    result = module.replay_rotation_strategy(
        series_by_label=series_by_label,
        metadata_by_label=metadata_by_label,
        strategy_config={"lookback_days": 20, "holdings_num": 1},
    )

    dates = [row["date"] for row in result["daily_positions"]]

    assert dates == ["2026-02-22", "2026-02-23", "2026-02-24"]
    assert result["daily_positions"][1]["holding_symbol"] == "510001"
    assert result["daily_positions"][1]["daily_return"] == 0.0
    assert len(set(dates)) == len(dates)


def test_build_yearly_returns_groups_daily_positions_by_calendar_year():
    rows = [
        {
            "date": "2025-12-30",
            "daily_return": 0.10,
            "strategy_nav": 1.10,
        },
        {
            "date": "2025-12-31",
            "daily_return": 0.0,
            "strategy_nav": 1.10,
        },
        {
            "date": "2026-01-02",
            "daily_return": -0.10,
            "strategy_nav": 0.99,
        },
    ]

    result = module.build_yearly_returns(rows)

    assert result == [
        {
            "year": "2025",
            "trading_days": 2,
            "start_nav": 1.0,
            "end_nav": 1.1,
            "annual_return": 0.1,
        },
        {
            "year": "2026",
            "trading_days": 1,
            "start_nav": 1.1,
            "end_nav": 0.99,
            "annual_return": -0.1,
        },
    ]


def test_build_symbol_contributions_aggregates_holding_periods_by_symbol():
    rows = [
        {
            "start_date": "2026-01-01",
            "end_date": "2026-01-05",
            "symbol": "510001",
            "name": "AETF",
            "holding_days": 3,
            "period_return": 0.10,
            "contribution_to_total_return": 0.10,
        },
        {
            "start_date": "2026-01-06",
            "end_date": "2026-01-10",
            "symbol": "510001",
            "name": "AETF",
            "holding_days": 4,
            "period_return": -0.05,
            "contribution_to_total_return": -0.04,
        },
        {
            "start_date": "2026-01-11",
            "end_date": "2026-01-12",
            "symbol": "",
            "name": "",
            "holding_days": 2,
            "period_return": 0.0,
            "contribution_to_total_return": 0.0,
        },
    ]

    result = module.build_symbol_contributions(rows)

    assert result == [
        {
            "symbol": "510001",
            "name": "AETF",
            "holding_periods": 2,
            "holding_days": 7,
            "total_contribution": 0.06,
            "average_period_return": 0.025,
            "best_period_return": 0.10,
            "best_period_start_date": "2026-01-01",
            "best_period_end_date": "2026-01-05",
            "worst_period_return": -0.05,
            "worst_period_start_date": "2026-01-06",
            "worst_period_end_date": "2026-01-10",
        },
        {
            "symbol": "CASH",
            "name": "空仓",
            "holding_periods": 1,
            "holding_days": 2,
            "total_contribution": 0.0,
            "average_period_return": 0.0,
            "best_period_return": 0.0,
            "best_period_start_date": "2026-01-11",
            "best_period_end_date": "2026-01-12",
            "worst_period_return": 0.0,
            "worst_period_start_date": "2026-01-11",
            "worst_period_end_date": "2026-01-12",
        },
    ]


def test_run_backtest_writes_required_artifacts():
    root = _make_workspace_tmp("writes_required_artifacts")
    config_path = root / "rotation.yaml"
    config_path.write_text(
        """
targets:
  - category: 权益
    label: A
    search_keywords: [A]
    code: "510001"
    kind: etf
  - category: 防守
    label: 银华日利ETF
    search_keywords: [银华日利ETF]
    code: "511880"
    kind: etf
defensive_targets: []
strategy:
  lookback_days: 20
  holdings_num: 1
""".strip(),
        encoding="utf-8",
    )
    source_root = root / "source"
    (source_root / "series").mkdir(parents=True, exist_ok=True)
    (source_root / "series" / "etf_510001.json").write_text(
        '[{"date":"2026-02-01","close":100.0},{"date":"2026-02-02","close":101.0},{"date":"2026-02-03","close":102.0},{"date":"2026-02-04","close":103.0},{"date":"2026-02-05","close":104.0},{"date":"2026-02-06","close":105.0},{"date":"2026-02-07","close":106.0},{"date":"2026-02-08","close":107.0},{"date":"2026-02-09","close":108.0},{"date":"2026-02-10","close":109.0},{"date":"2026-02-11","close":110.0},{"date":"2026-02-12","close":111.0},{"date":"2026-02-13","close":112.0},{"date":"2026-02-14","close":113.0},{"date":"2026-02-15","close":114.0},{"date":"2026-02-16","close":115.0},{"date":"2026-02-17","close":116.0},{"date":"2026-02-18","close":117.0},{"date":"2026-02-19","close":118.0},{"date":"2026-02-20","close":119.0},{"date":"2026-02-21","close":120.0},{"date":"2026-02-22","close":121.0},{"date":"2026-02-23","close":122.0}]',
        encoding="utf-8",
    )
    (source_root / "series" / "etf_511880.json").write_text(
        '[{"date":"2026-02-01","close":100.0},{"date":"2026-02-02","close":100.01},{"date":"2026-02-03","close":100.02},{"date":"2026-02-04","close":100.03},{"date":"2026-02-05","close":100.04},{"date":"2026-02-06","close":100.05},{"date":"2026-02-07","close":100.06},{"date":"2026-02-08","close":100.07},{"date":"2026-02-09","close":100.08},{"date":"2026-02-10","close":100.09},{"date":"2026-02-11","close":100.10},{"date":"2026-02-12","close":100.11},{"date":"2026-02-13","close":100.12},{"date":"2026-02-14","close":100.13},{"date":"2026-02-15","close":100.14},{"date":"2026-02-16","close":100.15},{"date":"2026-02-17","close":100.16},{"date":"2026-02-18","close":100.17},{"date":"2026-02-19","close":100.18},{"date":"2026-02-20","close":100.19},{"date":"2026-02-21","close":100.20},{"date":"2026-02-22","close":100.21},{"date":"2026-02-23","close":100.22}]',
        encoding="utf-8",
    )

    module.run_backtest(
        config_path=config_path,
        source_output_root=source_root,
        output_root=root / "out",
    )

    assert (root / "out" / "trades.csv").exists()
    assert (root / "out" / "daily_positions.csv").exists()
    assert (root / "out" / "daily_rankings.csv").exists()
    assert (root / "out" / "holding_periods.csv").exists()
    assert (root / "out" / "yearly_returns.csv").exists()
    assert (root / "out" / "symbol_contributions.csv").exists()
    assert (root / "out" / "backtest_summary.md").exists()
