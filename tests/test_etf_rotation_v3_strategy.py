import math

import etf_rotation_v3_strategy as module


def _make_series(closes):
    return [
        {"date": f"2026-03-{index + 1:02d}", "close": float(close)}
        for index, close in enumerate(closes)
    ]


def test_build_rotation_candidate_v3_keeps_positive_score_without_applying_short_filter():
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
    assert candidate["score_25"] > 0
    assert candidate["return_10d"] < 0
    assert candidate["score_25_positive"] is True
    assert candidate["qualified"] is None
    assert candidate["rejection_reason"] == ""


def test_apply_relative_median_short_confirmation_uses_greater_than_or_equal_to_median():
    candidates = [
        {
            "label": "A",
            "score_25": 1.5,
            "annualized_return_25": 2.0,
            "r_squared_25": 0.75,
            "return_10d": -0.03,
            "score_25_positive": True,
            "qualified": None,
            "rejection_reason": "",
        },
        {
            "label": "B",
            "score_25": 1.2,
            "annualized_return_25": 1.8,
            "r_squared_25": 0.67,
            "return_10d": -0.01,
            "score_25_positive": True,
            "qualified": None,
            "rejection_reason": "",
        },
        {
            "label": "C",
            "score_25": -0.2,
            "annualized_return_25": -0.3,
            "r_squared_25": 0.66,
            "return_10d": 0.05,
            "score_25_positive": False,
            "qualified": None,
            "rejection_reason": "",
        },
    ]

    result = module.apply_relative_median_short_confirmation(
        candidates=candidates,
        strategy_config={"short_confirmation_tolerance": 0.0},
    )

    qualified_by_label = {item["label"]: item["qualified"] for item in result}
    rejection_reason_by_label = {item["label"]: item["rejection_reason"] for item in result}

    assert qualified_by_label == {"A": False, "B": True, "C": False}
    assert rejection_reason_by_label["A"] == "return_10d_below_cross_section_median"
    assert rejection_reason_by_label["B"] == ""
    assert rejection_reason_by_label["C"] == "score_25_not_positive"


def test_apply_relative_median_short_confirmation_keeps_single_score_positive_asset():
    result = module.apply_relative_median_short_confirmation(
        candidates=[
            {
                "label": "A",
                "score_25": 1.0,
                "annualized_return_25": 1.5,
                "r_squared_25": 0.66,
                "return_10d": -0.02,
                "score_25_positive": True,
                "qualified": None,
                "rejection_reason": "",
            }
        ],
        strategy_config={"short_confirmation_tolerance": 0.0},
    )

    assert len(result) == 1
    assert result[0]["qualified"] is True
    assert result[0]["rejection_reason"] == ""
    assert result[0]["short_confirmation_threshold"] == -0.02


def test_calculate_weighted_trend_metrics_v3_matches_v2_math():
    closes = [100.0 * math.exp(0.001 * index) for index in range(25)]

    result = module.calculate_weighted_trend_metrics(closes)

    assert result is not None
    assert round(result["slope"], 6) == 0.001000
    assert round(result["annualized_return"], 6) == round(math.exp(0.25) - 1.0, 6)
    assert round(result["r_squared"], 6) == 1.000000
    assert round(result["score"], 6) == round(math.exp(0.25) - 1.0, 6)
