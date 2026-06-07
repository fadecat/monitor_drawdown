from __future__ import annotations

from pathlib import Path

import etf_rotation_v2_email_chart as module


def test_normalize_benchmark_nav_rows_uses_adj_unit_nav_and_dedupes_dates():
    rows = [
        {"trdDt": "2026-06-01", "adjUnitNav": "4.00", "unitNav": "3.00"},
        {"trdDt": "2026-06-02", "adjUnitNav": 4.20},
        {"trdDt": "2026-06-02", "adjUnitNav": 4.30},
        {"trdDt": "", "adjUnitNav": 9.99},
        {"trdDt": "2026-06-03", "adjUnitNav": None},
    ]

    assert module.normalize_benchmark_nav_rows(rows) == [
        {"date": "2026-06-01", "benchmark_nav": 4.0},
        {"date": "2026-06-02", "benchmark_nav": 4.3},
    ]


def test_build_relative_return_curve_aligns_strategy_and_benchmark_dates():
    strategy_rows = [
        {"date": "2026-06-01", "strategy_nav": 38.0},
        {"date": "2026-06-02", "strategy_nav": 39.9},
        {"date": "2026-06-03", "strategy_nav": 38.76},
    ]
    benchmark_rows = [
        {"date": "2026-06-01", "benchmark_nav": 4.0},
        {"date": "2026-06-03", "benchmark_nav": 4.4},
    ]

    result = module.build_relative_return_curve(
        strategy_rows=strategy_rows,
        benchmark_rows=benchmark_rows,
        window_days=365,
    )

    assert result["benchmark_label"] == "沪深300ETF"
    assert result["points"] == [
        {
            "date": "2026-06-01",
            "strategy_return": 0.0,
            "benchmark_return": 0.0,
            "strategy_nav": 38.0,
            "benchmark_nav": 4.0,
        },
        {
            "date": "2026-06-03",
            "strategy_return": 0.02,
            "benchmark_return": 0.1,
            "strategy_nav": 38.76,
            "benchmark_nav": 4.4,
        },
    ]
    assert result["summary"]["strategy_period_return"] == 0.02
    assert result["summary"]["benchmark_period_return"] == 0.1
    assert result["summary"]["excess_return"] == -0.08
    assert result["summary"]["strategy_max_drawdown"] == 0.0


def test_write_benchmark_series_uses_etf_nav_loader_and_archives_json(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        module.etf_analysis,
        "load_nav_rows",
        lambda code: [
            {"trdDt": "2026-06-01", "adjUnitNav": 4.0},
            {"trdDt": "2026-06-02", "adjUnitNav": 4.2},
        ],
    )

    rows = module.load_benchmark_series(output_dir=tmp_path)

    assert rows == [
        {"date": "2026-06-01", "benchmark_nav": 4.0},
        {"date": "2026-06-02", "benchmark_nav": 4.2},
    ]
    assert (tmp_path / "benchmark" / "etf_510300.json").exists()
    assert "2026-06-02" in (tmp_path / "benchmark" / "etf_510300.json").read_text(encoding="utf-8")


def test_generate_equity_chart_png_writes_file(tmp_path: Path):
    curve = {
        "benchmark_label": "沪深300ETF",
        "points": [
            {"date": "2026-06-01", "strategy_return": 0.0, "benchmark_return": 0.0},
            {"date": "2026-06-02", "strategy_return": 0.04, "benchmark_return": 0.01},
            {"date": "2026-06-03", "strategy_return": 0.02, "benchmark_return": -0.01},
        ],
        "summary": {
            "strategy_period_return": 0.02,
            "benchmark_period_return": -0.01,
            "excess_return": 0.03,
            "strategy_max_drawdown": -0.019230769231,
        },
    }

    output_path = module.generate_equity_chart_png(curve, output_dir=tmp_path)

    assert output_path == tmp_path / "etf_rotation_v2_equity_chart.png"
    assert output_path.exists()
    assert output_path.stat().st_size > 1000
