import json
import shutil
from pathlib import Path

import backtest_etf_rotation_v4_strategy as module


def _make_workspace_tmp(name: str) -> Path:
    root = Path(".test_artifacts/test_backtest_etf_rotation_v4_strategy") / name
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _make_series(label: str, closes: list[float]) -> list[dict[str, float | str]]:
    return [
        {"date": f"2026-04-{index + 1:03d}", "close": float(close), "label": label}
        for index, close in enumerate(closes)
    ]


def test_replay_rotation_v4_uses_t_plus_1_position_dates_and_risk_priority():
    series_by_label = {
        "A": _make_series(
            "A",
            [100.0 + 0.45 * index + 1.2 * __import__("math").sin(index / 13.0) for index in range(273)],
        ),
        "B": _make_series(
            "B",
            [100.0 + 0.42 * index + 1.2 * __import__("math").sin(index / 13.0) for index in range(273)],
        ),
        "银华日利ETF": _make_series("银华日利ETF", [100.0 + index * 0.01 for index in range(273)]),
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
            "short_confirmation_variant": "v4_a",
            "short_confirmation_history_days": 252,
            "short_confirmation_percentile_threshold": 0.4,
            "short_confirmation_absolute_floor": -0.02,
            "volatility_lookback_days": 20,
            "holdings_num": 1,
        },
        risk_labels={"A", "B"},
        defensive_labels={"银华日利ETF"},
    )

    assert result["daily_positions"][0]["signal_date"] == "2026-04-253"
    assert result["daily_positions"][0]["date"] == "2026-04-254"
    assert result["daily_positions"][0]["holding_symbol"] == "510001"
    assert result["daily_positions"][0]["selection_reason"] == "top_ranked_risk_asset"
    assert result["trades"][0]["reason"] == "initial_entry_risk"
    assert result["daily_candidate_metrics"][0]["short_confirmation_variant"] == "v4_a"
    assert result["daily_candidate_metrics"][0]["short_confirmation_passed"] is True


def test_replay_rotation_v4_writes_short_confirmation_comparison_outputs():
    series_by_label = {
        "A": _make_series(
            "A",
            [100.0 + 0.35 * index + 0.4 * __import__("math").sin(index / 7.0) for index in range(273)],
        ),
        "银华日利ETF": _make_series("银华日利ETF", [100.0 + index * 0.01 for index in range(273)]),
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
            "short_confirmation_variant": "v4_a",
            "short_confirmation_history_days": 252,
            "short_confirmation_percentile_threshold": 0.4,
            "short_confirmation_absolute_floor": -0.02,
            "volatility_lookback_days": 20,
            "holdings_num": 1,
        },
        risk_labels={"A"},
        defensive_labels={"银华日利ETF"},
    )

    assert result["daily_positions"][0]["holding_symbol"] == "511880"
    assert result["daily_positions"][0]["selection_reason"] == "fallback_defensive_asset"
    assert result["trades"][0]["reason"] == "initial_entry_defensive"
    assert result["daily_candidate_metrics"][0]["rejection_reason"] in {
        "short_confirmation_below_threshold",
        "return_10d_not_positive",
    }
    assert result["daily_candidate_metrics"][0]["short_confirmation_threshold"] is not None


def test_run_backtest_v4_writes_required_stage1_outputs():
    root = _make_workspace_tmp("writes_required_stage1_outputs")
    source_root = root / "source"
    (source_root / "series").mkdir(parents=True, exist_ok=True)
    for code, scale in [("510001", 1.012), ("511880", None)]:
        path = source_root / "series" / f"etf_{code}.json"
        if scale is None:
            rows = [
                {"date": f"2026-04-{index + 1:03d}", "close": 100.0 + index * 0.01}
                for index in range(273)
            ]
        else:
            rows = [
                {"date": f"2026-04-{index + 1:03d}", "close": 100.0 * (scale ** index)}
                for index in range(273)
            ]
        path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")

    config_path = root / "rotation_v4.yaml"
    config_path.write_text(
        """
risk_targets:
  - label: A
    search_keywords: [A]
    code: '510001'
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
  holdings_num: 1
  short_confirmation_variant: v4_a
  short_confirmation_history_days: 252
  short_confirmation_percentile_threshold: 0.4
  short_confirmation_absolute_floor: -0.02
  volatility_lookback_days: 20
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
