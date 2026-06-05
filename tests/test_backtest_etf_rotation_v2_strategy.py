import json
import shutil
from pathlib import Path

import backtest_etf_rotation_v2_strategy as module


def _make_workspace_tmp(name: str) -> Path:
    root = Path(".test_artifacts/test_backtest_etf_rotation_v2_strategy") / name
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _make_series(label: str, closes: list[float]) -> list[dict[str, float | str]]:
    return [
        {"date": f"2026-04-{index + 1:02d}", "close": float(close), "label": label}
        for index, close in enumerate(closes)
    ]


def test_replay_rotation_v2_uses_t_plus_1_position_dates_and_defensive_fallback():
    series_by_label = {
        "风险A": _make_series("风险A", [125.0 - index for index in range(26)]),
        "银华日利ETF": _make_series("银华日利ETF", [100.0 + index * 0.01 for index in range(26)]),
    }
    metadata_by_label = {
        "风险A": {"label": "风险A", "code": "510001", "kind": "etf", "name": "风险A"},
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
            "holdings_num": 1,
        },
        risk_labels={"风险A"},
        defensive_labels={"银华日利ETF"},
    )

    assert result["daily_positions"][0]["signal_date"] == "2026-04-25"
    assert result["daily_positions"][0]["date"] == "2026-04-26"
    assert result["daily_positions"][0]["holding_symbol"] == "511880"
    assert result["daily_positions"][0]["selection_reason"] == "fallback_defensive_asset"


def test_replay_rotation_v2_writes_daily_candidate_metrics_and_rankings():
    series_by_label = {
        "A": _make_series("A", [100.0 * (1.012 ** index) for index in range(27)]),
        "B": _make_series("B", [100.0 * (1.006 ** index) for index in range(27)]),
        "银华日利ETF": _make_series("银华日利ETF", [100.0 + index * 0.01 for index in range(27)]),
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
            "holdings_num": 1,
        },
        risk_labels={"A", "B"},
        defensive_labels={"银华日利ETF"},
    )

    candidate_rows = [
        row for row in result["daily_candidate_metrics"] if row["signal_date"] == "2026-04-25"
    ]
    ranking_rows = [row for row in result["daily_rankings"] if row["signal_date"] == "2026-04-25"]

    assert [row["label"] for row in candidate_rows] == ["A", "B"]
    assert all(row["qualified"] is True for row in candidate_rows)
    assert [row["label"] for row in ranking_rows] == ["A", "B"]
    assert ranking_rows[0]["rank"] == 1
    assert ranking_rows[0]["symbol"] == "510001"
    assert result["daily_positions"][0]["selection_reason"] == "top_ranked_risk_asset"


def test_run_backtest_v2_writes_required_stage1_outputs():
    root = _make_workspace_tmp("writes_required_stage1_outputs")
    config_path = root / "rotation_v2.yaml"
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
  holdings_num: 1
""".strip(),
        encoding="utf-8",
    )
    source_root = root / "source"
    (source_root / "series").mkdir(parents=True, exist_ok=True)
    (source_root / "series" / "etf_510001.json").write_text(
        json.dumps(
            [
                {"date": f"2026-04-{index + 1:02d}", "close": 100.0 * (1.012 ** index)}
                for index in range(27)
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (source_root / "series" / "etf_510002.json").write_text(
        json.dumps(
            [
                {"date": f"2026-04-{index + 1:02d}", "close": 100.0 * (1.006 ** index)}
                for index in range(27)
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (source_root / "series" / "etf_511880.json").write_text(
        json.dumps(
            [
                {"date": f"2026-04-{index + 1:02d}", "close": 100.0 + index * 0.01}
                for index in range(27)
            ],
            ensure_ascii=False,
        ),
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
