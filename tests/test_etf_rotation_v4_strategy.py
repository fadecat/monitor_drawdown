import math

import etf_rotation_v4_strategy as module


def _make_series(closes):
    return [
        {"date": f"2026-03-{index + 1:02d}", "close": float(close)}
        for index, close in enumerate(closes)
    ]


def test_calculate_volatility_adjusted_short_strength_uses_252d_history_and_absolute_floor():
    assert module.calculate_volatility_adjusted_short_strength(0.04, 0.02) == 2.0
    assert module.calculate_volatility_adjusted_short_strength(0.04, 0.0) == 0.0
    assert module.calculate_volatility_adjusted_short_strength(0.04, -0.01) == 0.0


def test_calculate_self_relative_short_percentile_uses_symbol_history_not_cross_section():
    percentile = module.calculate_self_relative_short_percentile(
        0.05,
        history_values=[-0.04, -0.01, 0.00, 0.02, 0.03, 0.06, 0.08],
    )

    assert round(percentile, 6) == round(5 / 7, 6)


def test_build_rotation_candidate_v4_records_variant_specific_fields_and_passes_with_clean_uptrend():
    closes = [100.0 + 0.25 * index + 2.0 * math.sin(index / 7.0) for index in range(273)]

    candidate = module.build_rotation_candidate_v4(
        latest_snapshot={
            "label": "测试ETF",
            "selected_primary": {"code": "510001", "kind": "etf", "name": "测试ETF"},
        },
        series_records=_make_series(closes),
        strategy_config={
            "lookback_days": 25,
            "short_lookback_days": 10,
            "annualization_days": 250,
            "weight_start": 1.0,
            "weight_end": 2.0,
            "short_confirmation_variant": "v4_a",
            "short_confirmation_history_days": 252,
            "short_confirmation_percentile_threshold": 0.40,
            "short_confirmation_absolute_floor": -0.02,
            "volatility_lookback_days": 20,
        },
    )

    assert candidate is not None
    assert candidate["label"] == "测试ETF"
    assert candidate["score_25"] > 0
    assert candidate["short_confirmation_variant"] == "v4_a"
    assert candidate["history_window"] == 252
    assert candidate["absolute_floor"] == -0.02
    assert candidate["short_confirmation_threshold"] is not None
    assert candidate["short_confirmation_passed"] is True
    assert candidate["rejection_reason"] == ""
    assert candidate["volatility_20d"] > 0
    assert candidate["volatility_adjusted_return_10d"] > 0
    assert candidate["self_relative_short_percentile"] >= 0.4


def test_build_rotation_candidate_v4_keeps_rejection_reason_when_base_qualification_fails():
    closes = [100.0 * math.exp(-0.001 * index) for index in range(273)]

    candidate = module.build_rotation_candidate_v4(
        latest_snapshot={
            "label": "测试ETF",
            "selected_primary": {"code": "510001", "kind": "etf", "name": "测试ETF"},
        },
        series_records=_make_series(closes),
        strategy_config={
            "lookback_days": 25,
            "short_lookback_days": 10,
            "annualization_days": 250,
            "weight_start": 1.0,
            "weight_end": 2.0,
            "short_confirmation_variant": "v4_a",
            "short_confirmation_history_days": 252,
            "short_confirmation_percentile_threshold": 0.40,
            "short_confirmation_absolute_floor": -0.02,
            "volatility_lookback_days": 20,
        },
    )

    assert candidate is not None
    assert candidate["qualified"] is False
    assert candidate["rejection_reason"] == "score_25_not_positive"


def test_build_rotation_candidate_v4_variant_a_differs_from_variant_b_on_same_series():
    closes = [100.0 + 0.25 * index + 2.0 * math.sin(index / 7.0) for index in range(273)]

    base_config = {
        "lookback_days": 25,
        "short_lookback_days": 10,
        "annualization_days": 250,
        "weight_start": 1.0,
        "weight_end": 2.0,
        "short_confirmation_history_days": 252,
        "short_confirmation_percentile_threshold": 0.40,
        "short_confirmation_absolute_floor": -0.02,
        "volatility_lookback_days": 20,
    }

    v4_a = module.build_rotation_candidate_v4(
        latest_snapshot={
            "label": "测试ETF",
            "selected_primary": {"code": "510001", "kind": "etf", "name": "测试ETF"},
        },
        series_records=_make_series(closes),
        strategy_config={**base_config, "short_confirmation_variant": "v4_a"},
    )
    v4_b = module.build_rotation_candidate_v4(
        latest_snapshot={
            "label": "测试ETF",
            "selected_primary": {"code": "510001", "kind": "etf", "name": "测试ETF"},
        },
        series_records=_make_series(closes),
        strategy_config={**base_config, "short_confirmation_variant": "v4_b"},
    )

    assert v4_a is not None and v4_b is not None
    assert v4_a["short_confirmation_variant"] == "v4_a"
    assert v4_b["short_confirmation_variant"] == "v4_b"
    assert v4_a["qualified"] is True
    assert v4_b["qualified"] is True
    assert v4_a["self_relative_short_percentile"] != v4_b["self_relative_short_percentile"]
    assert v4_a["short_confirmation_threshold"] != v4_b["short_confirmation_threshold"]
