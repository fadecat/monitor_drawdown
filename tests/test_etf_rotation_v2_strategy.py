import math

import etf_rotation_v2_strategy as module


def _make_series(closes):
    return [
        {"date": f"2026-03-{index + 1:02d}", "close": float(close)}
        for index, close in enumerate(closes)
    ]


def test_calculate_weighted_trend_metrics_returns_expected_values_for_perfect_log_linear_uptrend():
    closes = [100.0 * math.exp(0.001 * index) for index in range(25)]

    result = module.calculate_weighted_trend_metrics(closes)

    assert result is not None
    assert round(result["slope"], 6) == 0.001000
    assert round(result["annualized_return"], 6) == round(math.exp(0.25) - 1.0, 6)
    assert round(result["r_squared"], 6) == 1.000000
    assert round(result["score"], 6) == round(math.exp(0.25) - 1.0, 6)


def test_calculate_weighted_trend_metrics_returns_zero_r_squared_for_flat_series():
    result = module.calculate_weighted_trend_metrics([100.0] * 25)

    assert result is not None
    assert result["annualized_return"] == 0.0
    assert result["r_squared"] == 0.0
    assert result["score"] == 0.0


def test_build_rotation_candidate_v2_requires_positive_score_25_and_return_10d():
    candidate = module.build_rotation_candidate(
        latest_snapshot={
            "label": "测试ETF",
            "selected_primary": {"code": "510001", "kind": "etf", "name": "测试ETF"},
        },
        series_records=_make_series(
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
                129.0,
                128.0,
                127.0,
                126.0,
                125.0,
                124.0,
                123.0,
                122.0,
                121.0,
            ]
        ),
        strategy_config={
            "lookback_days": 25,
            "short_lookback_days": 10,
            "annualization_days": 250,
            "weight_start": 1.0,
            "weight_end": 2.0,
        },
    )

    assert candidate is not None
    assert candidate["label"] == "测试ETF"
    assert candidate["score_25"] > 0
    assert candidate["return_10d"] < 0
    assert candidate["qualified"] is False
    assert candidate["rejection_reason"] == "return_10d_not_positive"
