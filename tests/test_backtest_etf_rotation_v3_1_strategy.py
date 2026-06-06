import shutil
from pathlib import Path

import backtest_etf_rotation_v3_1_strategy as module


def _make_workspace_tmp(name: str) -> Path:
    root = Path(".test_artifacts/test_backtest_etf_rotation_v3_strategy") / name
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _make_series(label: str, closes: list[float]) -> list[dict[str, float | str]]:
    return [
        {"date": f"2026-04-{index + 1:02d}", "close": float(close), "label": label}
        for index, close in enumerate(closes)
    ]


def test_replay_rotation_v3_1_keeps_single_positive_score_asset_in_risk_mode():
    series_by_label = {
        "A": _make_series(
            "A",
            [
                100.0,
                102.0,
                104.0,
                106.0,
                108.0,
                110.0,
                112.0,
                114.0,
                116.0,
                118.0,
                120.0,
                122.0,
                124.0,
                126.0,
                128.0,
                129.5,
                129.0,
                128.5,
                128.0,
                127.5,
                127.0,
                126.7,
                126.4,
                126.1,
                125.8,
                126.0,
            ],
        ),
        "B": _make_series("B", [100.0 - index for index in range(26)]),
        "银华日利ETF": _make_series("银华日利ETF", [100.0 + index * 0.01 for index in range(26)]),
    }
    metadata_by_label = {
        "A": {"label": "A", "code": "510001", "kind": "etf", "name": "AETF"},
        "B": {"label": "B", "code": "510002", "kind": "etf", "name": "BETF"},
        "银华日利ETF": {
            "label": "银华日利ETF",
            "code": "511880",
            "kind": "etf",
            "name": "银华日利ETF",
        },
    }

    result = module.replay_rotation_strategy(
        series_by_label=series_by_label,
        metadata_by_label=metadata_by_label,
        strategy_config={
            "lookback_days": 25,
            "short_lookback_days": 10,
            "annualization_days": 250,
            "weight_start": 1.0,
            "weight_end": 2.0,
            "short_confirmation_tolerance": 0.0,
            "short_confirmation_absolute_floor": -0.03,
            "holdings_num": 1,
        },
        risk_labels={"A", "B"},
        defensive_labels={"银华日利ETF"},
    )

    assert result["daily_positions"][0]["holding_symbol"] == "510001"
    assert result["daily_positions"][0]["selection_reason"] == "top_ranked_risk_asset"
    assert result["trades"][0]["reason"] == "initial_entry_risk"


def test_replay_rotation_v3_1_switches_to_defensive_when_absolute_floor_rejects_single_positive_score_asset():
    series_by_label = {
        "A": _make_series(
            "A",
            [
                100.0,
                102.0,
                104.0,
                106.0,
                108.0,
                110.0,
                112.0,
                114.0,
                116.0,
                118.0,
                120.0,
                122.0,
                124.0,
                126.0,
                128.0,
                130.0,
                128.0,
                126.0,
                124.0,
                122.0,
                120.0,
                119.0,
                118.0,
                117.0,
                116.0,
                115.5,
            ],
        ),
        "银华日利ETF": _make_series("银华日利ETF", [100.0 + index * 0.01 for index in range(26)]),
    }
    metadata_by_label = {
        "A": {"label": "A", "code": "510001", "kind": "etf", "name": "AETF"},
        "银华日利ETF": {
            "label": "银华日利ETF",
            "code": "511880",
            "kind": "etf",
            "name": "银华日利ETF",
        },
    }

    result = module.replay_rotation_strategy(
        series_by_label=series_by_label,
        metadata_by_label=metadata_by_label,
        strategy_config={
            "lookback_days": 25,
            "short_lookback_days": 10,
            "annualization_days": 250,
            "weight_start": 1.0,
            "weight_end": 2.0,
            "short_confirmation_tolerance": 0.0,
            "short_confirmation_absolute_floor": -0.03,
            "holdings_num": 1,
        },
        risk_labels={"A"},
        defensive_labels={"银华日利ETF"},
    )

    assert result["daily_positions"][0]["holding_symbol"] == "511880"
    assert result["daily_positions"][0]["selection_reason"] == "fallback_defensive_asset"
    assert result["trades"][0]["reason"] == "initial_entry_defensive"
    assert result["daily_candidate_metrics"][0]["rejection_reason"] == "return_10d_below_absolute_floor"


def test_run_backtest_v3_1_writes_required_stage1_outputs():
    root = _make_workspace_tmp("writes_required_outputs")
    source_root = root / "source"
    (source_root / "series").mkdir(parents=True, exist_ok=True)
    for code, scale in [("510001", 1.012), ("510002", 1.006), ("511880", None)]:
        path = source_root / "series" / f"etf_{code}.json"
        if scale is None:
            rows = [
                {"date": f"2026-04-{index + 1:02d}", "close": 100.0 + index * 0.01}
                for index in range(27)
            ]
        else:
            rows = [
                {"date": f"2026-04-{index + 1:02d}", "close": 100.0 * (scale ** index)}
                for index in range(27)
            ]
        path.write_text(__import__("json").dumps(rows, ensure_ascii=False), encoding="utf-8")

    config_path = root / "rotation_v3_1.yaml"
    config_path.write_text(
        """
risk_targets:
  - label: A
    search_keywords: [A]
    code: '510001'
    kind: etf
  - label: B
    search_keywords: [B]
    code: '510002'
    kind: etf
defensive_targets:
  - label: CASH
    search_keywords: [CASH]
    code: '511880'
    kind: etf
strategy:
  lookback_days: 25
  short_lookback_days: 10
  annualization_days: 250
  weight_start: 1.0
  weight_end: 2.0
  short_confirmation_tolerance: 0.0
  short_confirmation_absolute_floor: -0.03
  holdings_num: 1
""".strip(),
        encoding="utf-8",
    )

    result = module.run_backtest(
        config_path=config_path,
        source_output_root=source_root,
        output_root=root / "out",
    )

    assert result["summary"]["final_nav"] > 1.0
    assert (root / "out" / "daily_candidate_metrics.csv").exists()
    assert (root / "out" / "daily_rankings.csv").exists()
    assert (root / "out" / "daily_positions.csv").exists()
    assert (root / "out" / "trades.csv").exists()
    assert (root / "out" / "holding_periods.csv").exists()
    assert (root / "out" / "yearly_returns.csv").exists()
    assert (root / "out" / "symbol_contributions.csv").exists()
    assert (root / "out" / "backtest_summary.md").exists()
