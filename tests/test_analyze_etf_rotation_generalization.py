import analyze_etf_rotation_generalization as module


def test_build_segment_summary_normalizes_nav_inside_segment():
    rows = [
        {
            "date": "2024-01-02",
            "signal_date": "2024-01-01",
            "holding_symbol": "511880",
            "strategy_nav": "2.0",
            "daily_return": "0.0",
        },
        {
            "date": "2024-01-03",
            "signal_date": "2024-01-02",
            "holding_symbol": "510001",
            "strategy_nav": "2.2",
            "daily_return": "0.10",
        },
        {
            "date": "2024-01-04",
            "signal_date": "2024-01-03",
            "holding_symbol": "510001",
            "strategy_nav": "1.98",
            "daily_return": "-0.10",
        },
    ]

    summary = module.build_segment_summary(
        version="TEST",
        rows=rows,
        start_date="2024-01-02",
        end_date="2024-01-04",
        defensive_symbol="511880",
    )

    assert summary["version"] == "TEST"
    assert summary["start_date"] == "2024-01-02"
    assert summary["end_date"] == "2024-01-04"
    assert summary["trading_days"] == 3
    assert summary["defensive_days"] == 1
    assert summary["risk_days"] == 2
    assert summary["segment_final_nav"] == 0.99
    assert summary["segment_total_return"] == -0.01
    assert summary["segment_max_drawdown"] == -0.1


def test_build_segment_summary_returns_empty_metrics_when_no_rows_match():
    summary = module.build_segment_summary(
        version="TEST",
        rows=[],
        start_date="2024-01-02",
        end_date="2024-01-04",
        defensive_symbol="511880",
    )

    assert summary["version"] == "TEST"
    assert summary["trading_days"] == 0
    assert summary["segment_final_nav"] == 1.0
    assert summary["segment_total_return"] == 0.0
    assert summary["segment_max_drawdown"] == 0.0

