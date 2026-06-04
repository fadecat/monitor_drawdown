import etf_trend_analysis as module


def _make_records(closes):
    return [
        {"date": f"2026-01-{index + 1:02d}", "close": float(close)}
        for index, close in enumerate(closes)
    ]


def test_analyze_trend_series_computes_ma20_bias20_and_direction5():
    closes = list(range(100, 130))
    analysis = module.analyze_trend_series(_make_records(closes))

    latest = analysis["records"][-1]

    expected_ma20 = sum(closes[-20:]) / 20
    expected_bias20_raw = closes[-1] / expected_ma20 - 1

    bias20_raw_series = []
    for end_index in range(19, len(closes)):
        window = closes[end_index - 19 : end_index + 1]
        ma20 = sum(window) / 20
        bias20_raw_series.append(closes[end_index] / ma20 - 1)
    expected_bias20 = sum(bias20_raw_series[-5:]) / 5
    expected_direction5 = expected_bias20 - bias20_raw_series[-6]

    assert latest["ma20"] == expected_ma20
    assert latest["bias20_raw"] == expected_bias20_raw
    assert latest["bias20"] == expected_bias20
    assert latest["direction5"] == expected_direction5


def test_analyze_trend_series_keeps_trend_fields_empty_during_warm_up():
    analysis = module.analyze_trend_series(_make_records(range(100, 128)))

    latest = analysis["records"][-1]

    assert latest["ma20"] is not None
    assert latest["bias20_raw"] is not None
    assert latest["bias20"] is not None
    assert latest["direction5"] is None
    assert latest["trend_state"] is None
    assert latest["transition_confirmed"] is False
    assert latest["transition_date"] is None


def test_analyze_trend_series_orders_records_by_parsed_date():
    analysis = module.analyze_trend_series(
        [
            {"date": "2026-01-10", "close": 110.0},
            {"date": "2026-01-2", "close": 102.0},
            {"date": "2026-01-01", "close": 101.0},
        ]
    )

    assert [record["date"] for record in analysis["records"]] == [
        "2026-01-01",
        "2026-01-2",
        "2026-01-10",
    ]


def test_classify_trend_state_maps_bias20_and_direction5_to_four_quadrants():
    assert module._classify_trend_state_value(0.01, 0.02) == "强势上行"
    assert module._classify_trend_state_value(0.01, 0.0) == "强势回落"
    assert module._classify_trend_state_value(-0.01, 0.02) == "弱势修复"
    assert module._classify_trend_state_value(-0.01, -0.02) == "弱势下行"
    assert module._classify_trend_state_value(None, 0.02) is None


def test_confirm_transitions_marks_first_new_state_after_two_day_confirmation():
    records = [
        {
            "date": "2026-06-01",
            "close": 1.0,
            "ma20": 1.0,
            "bias20_raw": -0.02,
            "bias20": -0.01,
            "direction5": -0.01,
            "trend_state": "弱势下行",
            "state_candidate_changed": False,
            "transition_confirmed": False,
            "transition_date": None,
        },
        {
            "date": "2026-06-02",
            "close": 1.0,
            "ma20": 1.0,
            "bias20_raw": -0.01,
            "bias20": -0.005,
            "direction5": 0.01,
            "trend_state": "弱势修复",
            "state_candidate_changed": False,
            "transition_confirmed": False,
            "transition_date": None,
        },
        {
            "date": "2026-06-03",
            "close": 1.0,
            "ma20": 1.0,
            "bias20_raw": -0.005,
            "bias20": -0.002,
            "direction5": 0.02,
            "trend_state": "弱势修复",
            "state_candidate_changed": False,
            "transition_confirmed": False,
            "transition_date": None,
        },
    ]

    confirmed = module._confirm_transitions(records)

    assert confirmed[1]["state_candidate_changed"] is True
    assert confirmed[1]["transition_confirmed"] is False
    assert confirmed[2]["transition_confirmed"] is True
    assert confirmed[2]["transition_date"] == "2026-06-02"


def test_confirm_transitions_drops_candidate_when_state_reverts_next_day():
    records = [
        {
            "date": "2026-06-01",
            "close": 1.0,
            "ma20": 1.0,
            "bias20_raw": -0.02,
            "bias20": -0.01,
            "direction5": -0.01,
            "trend_state": "弱势下行",
            "state_candidate_changed": False,
            "transition_confirmed": False,
            "transition_date": None,
        },
        {
            "date": "2026-06-02",
            "close": 1.0,
            "ma20": 1.0,
            "bias20_raw": -0.01,
            "bias20": -0.005,
            "direction5": 0.01,
            "trend_state": "弱势修复",
            "state_candidate_changed": False,
            "transition_confirmed": False,
            "transition_date": None,
        },
        {
            "date": "2026-06-03",
            "close": 1.0,
            "ma20": 1.0,
            "bias20_raw": -0.015,
            "bias20": -0.008,
            "direction5": -0.01,
            "trend_state": "弱势下行",
            "state_candidate_changed": False,
            "transition_confirmed": False,
            "transition_date": None,
        },
    ]

    confirmed = module._confirm_transitions(records)

    assert confirmed[1]["state_candidate_changed"] is True
    assert confirmed[2]["transition_confirmed"] is False
    assert confirmed[2]["transition_date"] is None


def test_confirm_transitions_starts_new_candidate_after_rejected_false_start():
    records = [
        {
            "date": "2026-06-01",
            "close": 1.0,
            "ma20": 1.0,
            "bias20_raw": -0.02,
            "bias20": -0.01,
            "direction5": -0.01,
            "trend_state": "弱势下行",
            "state_candidate_changed": False,
            "transition_confirmed": False,
            "transition_date": None,
        },
        {
            "date": "2026-06-02",
            "close": 1.0,
            "ma20": 1.0,
            "bias20_raw": -0.01,
            "bias20": -0.005,
            "direction5": 0.01,
            "trend_state": "弱势修复",
            "state_candidate_changed": False,
            "transition_confirmed": False,
            "transition_date": None,
        },
        {
            "date": "2026-06-03",
            "close": 1.0,
            "ma20": 1.0,
            "bias20_raw": 0.01,
            "bias20": 0.01,
            "direction5": 0.01,
            "trend_state": "强势上行",
            "state_candidate_changed": False,
            "transition_confirmed": False,
            "transition_date": None,
        },
        {
            "date": "2026-06-04",
            "close": 1.0,
            "ma20": 1.0,
            "bias20_raw": 0.012,
            "bias20": 0.011,
            "direction5": 0.02,
            "trend_state": "强势上行",
            "state_candidate_changed": False,
            "transition_confirmed": False,
            "transition_date": None,
        },
    ]

    confirmed = module._confirm_transitions(records)

    assert confirmed[2]["state_candidate_changed"] is True
    assert confirmed[2]["transition_confirmed"] is False
    assert confirmed[3]["transition_confirmed"] is True
    assert confirmed[3]["transition_date"] == "2026-06-03"


def test_analyze_trend_series_populates_latest_summary_fields():
    closes = list(range(100, 130)) + [80, 82, 84, 86, 88, 90]
    records = [
        {"date": f"2026-01-{index + 1:02d}", "close": float(close)}
        for index, close in enumerate(closes[:31])
    ]
    records.extend(
        {"date": f"2026-02-{index - 30:02d}", "close": float(close)}
        for index, close in enumerate(closes[31:], start=31)
    )

    analysis = module.analyze_trend_series(records)

    assert analysis["latest_transition_date"] == "2026-02-01"
    assert analysis["latest_valid_state"] == "弱势修复"
    assert analysis["latest_valid_date"] == "2026-02-05"


def test_classify_screenshot_proxy_state_value_maps_three_state_proxy():
    assert module._classify_screenshot_proxy_state_value(0.0080, 0.0010) == "确立多头"
    assert module._classify_screenshot_proxy_state_value(0.0050, 0.0010) == "震荡中"
    assert module._classify_screenshot_proxy_state_value(0.0030, -0.0050) == "确立多头"
    assert module._classify_screenshot_proxy_state_value(-0.0030, -0.0400) == "确立多头"
    assert module._classify_screenshot_proxy_state_value(-0.0200, 0.0020) == "确立空头"
    assert module._classify_screenshot_proxy_state_value(-0.0200, -0.0050) == "震荡中"
    assert module._classify_screenshot_proxy_state_value(None, 0.01) is None


def test_classify_screenshot_transition_regime_value_uses_raw_and_smoothed_bias():
    assert module._classify_screenshot_transition_regime_value(0.0110, 0.0000) == "确立多头"
    assert module._classify_screenshot_transition_regime_value(0.0110, -0.0010) == "震荡中"
    assert (
        module._classify_screenshot_transition_regime_value(-0.0150, -0.0100)
        == "确立空头"
    )
    assert (
        module._classify_screenshot_transition_regime_value(-0.0140, -0.0200)
        == "震荡中"
    )
    assert module._classify_screenshot_transition_regime_value(None, 0.0) is None


def test_analyze_trend_series_populates_screenshot_proxy_state_after_warm_up():
    analysis = module.analyze_trend_series(_make_records(range(100, 130)))

    latest = analysis["records"][-1]

    assert latest["screenshot_proxy_state"] == "确立多头"


def test_apply_screenshot_transition_regime_requires_asymmetric_confirmation():
    records = module._apply_screenshot_transition_regime(
        [
            {
                "date": "2026-06-01",
                "screenshot_transition_regime_signal": "确立多头",
            },
            {
                "date": "2026-06-02",
                "screenshot_transition_regime_signal": "震荡中",
            },
            {
                "date": "2026-06-03",
                "screenshot_transition_regime_signal": "震荡中",
            },
            {
                "date": "2026-06-04",
                "screenshot_transition_regime_signal": "确立空头",
            },
            {
                "date": "2026-06-05",
                "screenshot_transition_regime_signal": "确立空头",
            },
            {
                "date": "2026-06-06",
                "screenshot_transition_regime_signal": "确立空头",
            },
        ]
    )

    assert [
        (
            row["screenshot_transition_regime_state"],
            row["screenshot_transition_regime_start_date"],
        )
        for row in records
    ] == [
        ("确立多头", "2026-06-01"),
        ("确立多头", "2026-06-01"),
        ("震荡中", "2026-06-02"),
        ("震荡中", "2026-06-02"),
        ("震荡中", "2026-06-02"),
        ("确立空头", "2026-06-04"),
    ]


def test_build_latest_screenshot_proxy_snapshot_uses_current_state_run_start():
    snapshot = module.build_latest_screenshot_proxy_snapshot(
        {
            "records": [
                {
                    "date": "2026-06-01",
                    "bias20_raw": 0.0100,
                    "bias20": 0.0030,
                    "direction5": 0.0100,
                    "screenshot_proxy_state": "确立多头",
                },
                {
                    "date": "2026-06-02",
                    "bias20_raw": -0.0100,
                    "bias20": -0.0100,
                    "direction5": -0.0030,
                    "screenshot_proxy_state": "震荡中",
                },
                {
                    "date": "2026-06-03",
                    "bias20_raw": -0.0110,
                    "bias20": -0.0090,
                    "direction5": -0.0020,
                    "screenshot_proxy_state": "震荡中",
                },
            ]
        }
    )

    assert snapshot == {
        "screenshot_bias_value": -0.0110,
        "screenshot_trend_state": "震荡中",
        "screenshot_transition_date": "2026-06-02",
    }


def test_build_latest_screenshot_proxy_snapshot_keeps_trend_through_one_day_neutral():
    snapshot = module.build_latest_screenshot_proxy_snapshot(
        {
            "records": [
                {
                    "date": "2026-06-01",
                    "bias20_raw": 0.0200,
                    "bias20": 0.0100,
                    "direction5": 0.0100,
                    "screenshot_proxy_state": "确立多头",
                },
                {
                    "date": "2026-06-02",
                    "bias20_raw": 0.0180,
                    "bias20": 0.0090,
                    "direction5": 0.0080,
                    "screenshot_proxy_state": "确立多头",
                },
                {
                    "date": "2026-06-03",
                    "bias20_raw": 0.0020,
                    "bias20": 0.0010,
                    "direction5": 0.0100,
                    "screenshot_proxy_state": "震荡中",
                },
            ]
        }
    )

    assert snapshot == {
        "screenshot_bias_value": 0.0020,
        "screenshot_trend_state": "确立多头",
        "screenshot_transition_date": "2026-06-01",
    }


def test_build_latest_screenshot_transition_regime_snapshot_uses_confirmed_history():
    records = module._apply_screenshot_transition_regime(
        [
            {
                "date": "2026-06-01",
                "screenshot_transition_regime_signal": "确立多头",
            },
            {
                "date": "2026-06-02",
                "screenshot_transition_regime_signal": "震荡中",
            },
            {
                "date": "2026-06-03",
                "screenshot_transition_regime_signal": "震荡中",
            },
            {
                "date": "2026-06-04",
                "screenshot_transition_regime_signal": "确立空头",
            },
            {
                "date": "2026-06-05",
                "screenshot_transition_regime_signal": "确立空头",
            },
            {
                "date": "2026-06-06",
                "screenshot_transition_regime_signal": "确立空头",
            },
        ]
    )

    snapshot = module.build_latest_screenshot_transition_regime_snapshot(
        {"records": records}
    )

    assert snapshot == {
        "screenshot_transition_regime_state": "确立空头",
        "screenshot_transition_regime_transition_date": "2026-06-04",
    }


def test_find_latest_bias_sign_transition_date_uses_start_of_current_positive_run():
    assert module._find_latest_bias_sign_transition_date(
        [
            {"date": "2026-06-01", "bias20": None},
            {"date": "2026-06-02", "bias20": -0.0100},
            {"date": "2026-06-03", "bias20": -0.0020},
            {"date": "2026-06-04", "bias20": 0.0010},
            {"date": "2026-06-05", "bias20": 0.0040},
        ]
    ) == "2026-06-04"


def test_find_latest_bias_sign_transition_date_treats_zero_as_non_positive():
    assert module._find_latest_bias_sign_transition_date(
        [
            {"date": "2026-06-01", "bias20": 0.0040},
            {"date": "2026-06-02", "bias20": 0.0},
            {"date": "2026-06-03", "bias20": -0.0030},
        ]
    ) == "2026-06-02"


def test_build_latest_screenshot_transition_bias_sign_snapshot_keeps_proxy_state():
    snapshot = module.build_latest_screenshot_transition_bias_sign_snapshot(
        {
            "records": [
                {
                    "date": "2026-06-01",
                    "bias20_raw": 0.0200,
                    "bias20": 0.0100,
                    "direction5": 0.0100,
                    "screenshot_proxy_state": "确立多头",
                },
                {
                    "date": "2026-06-02",
                    "bias20_raw": 0.0000,
                    "bias20": 0.0,
                    "direction5": -0.0100,
                    "screenshot_proxy_state": "震荡中",
                },
                {
                    "date": "2026-06-03",
                    "bias20_raw": -0.0200,
                    "bias20": -0.0050,
                    "direction5": -0.0200,
                    "screenshot_proxy_state": "确立空头",
                },
            ]
        }
    )

    assert snapshot == {
        "screenshot_transition_bias_sign_state": "确立空头",
        "screenshot_transition_bias_sign_transition_date": "2026-06-02",
    }


def test_build_latest_screenshot_transition_hybrid_snapshot_mixes_dates_by_state():
    analysis = {
        "records": [
            {
                "date": "2026-06-01",
                "bias20_raw": 0.0100,
                "bias20": 0.0030,
                "direction5": 0.0100,
                "screenshot_proxy_state": "确立多头",
                "screenshot_transition_regime_state": "震荡中",
                "screenshot_transition_regime_start_date": "2026-05-28",
            },
            {
                "date": "2026-06-02",
                "bias20_raw": 0.0110,
                "bias20": 0.0050,
                "direction5": 0.0080,
                "screenshot_proxy_state": "确立多头",
                "screenshot_transition_regime_state": "震荡中",
                "screenshot_transition_regime_start_date": "2026-05-28",
            },
            {
                "date": "2026-06-03",
                "bias20_raw": 0.0120,
                "bias20": 0.0060,
                "direction5": 0.0060,
                "screenshot_proxy_state": "确立多头",
                "screenshot_transition_regime_state": "确立多头",
                "screenshot_transition_regime_start_date": "2026-06-02",
            },
        ]
    }

    snapshot = module.build_latest_screenshot_transition_hybrid_snapshot(analysis)

    assert snapshot == {
        "screenshot_transition_hybrid_state": "确立多头",
        "screenshot_transition_hybrid_transition_date": "2026-06-01",
    }


def test_build_latest_screenshot_transition_hybrid_snapshot_uses_earlier_bear_date():
    analysis = {
        "records": [
            {
                "date": "2026-06-01",
                "bias20_raw": -0.0200,
                "bias20": -0.0200,
                "direction5": 0.0020,
                "screenshot_proxy_state": "确立空头",
                "screenshot_transition_regime_state": "确立空头",
                "screenshot_transition_regime_start_date": "2026-05-29",
            },
            {
                "date": "2026-06-02",
                "bias20_raw": -0.0210,
                "bias20": -0.0210,
                "direction5": 0.0030,
                "screenshot_proxy_state": "确立空头",
                "screenshot_transition_regime_state": "确立空头",
                "screenshot_transition_regime_start_date": "2026-05-29",
            },
            {
                "date": "2026-06-03",
                "bias20_raw": -0.0220,
                "bias20": -0.0220,
                "direction5": 0.0040,
                "screenshot_proxy_state": "确立空头",
                "screenshot_transition_regime_state": "确立空头",
                "screenshot_transition_regime_start_date": "2026-05-29",
            },
        ]
    }

    snapshot = module.build_latest_screenshot_transition_hybrid_snapshot(analysis)

    assert snapshot == {
        "screenshot_transition_hybrid_state": "确立空头",
        "screenshot_transition_hybrid_transition_date": "2026-06-01",
    }


def test_build_latest_screenshot_transition_hybrid_snapshot_uses_regime_when_bull_momentum_is_weak():
    analysis = {
        "records": [
            {
                "date": "2026-06-01",
                "bias20_raw": 0.0100,
                "bias20": 0.0020,
                "direction5": -0.0400,
                "screenshot_proxy_state": "确立多头",
                "screenshot_transition_regime_state": "震荡中",
                "screenshot_transition_regime_start_date": "2026-05-28",
            },
            {
                "date": "2026-06-02",
                "bias20_raw": 0.0090,
                "bias20": 0.0010,
                "direction5": -0.0350,
                "screenshot_proxy_state": "确立多头",
                "screenshot_transition_regime_state": "震荡中",
                "screenshot_transition_regime_start_date": "2026-05-28",
            },
        ]
    }

    snapshot = module.build_latest_screenshot_transition_hybrid_snapshot(analysis)

    assert snapshot == {
        "screenshot_transition_hybrid_state": "确立多头",
        "screenshot_transition_hybrid_transition_date": "2026-05-28",
    }


def test_build_latest_screenshot_transition_hybrid_snapshot_uses_proxy_when_bear_rebound_is_strong():
    analysis = {
        "records": [
            {
                "date": "2026-06-01",
                "bias20_raw": -0.0200,
                "bias20": -0.0120,
                "direction5": 0.0100,
                "screenshot_proxy_state": "确立空头",
                "screenshot_transition_regime_state": "确立空头",
                "screenshot_transition_regime_start_date": "2026-05-29",
            },
            {
                "date": "2026-06-02",
                "bias20_raw": -0.0210,
                "bias20": -0.0110,
                "direction5": 0.0080,
                "screenshot_proxy_state": "确立空头",
                "screenshot_transition_regime_state": "确立空头",
                "screenshot_transition_regime_start_date": "2026-05-29",
            },
            {
                "date": "2026-06-03",
                "bias20_raw": -0.0220,
                "bias20": -0.0110,
                "direction5": 0.0060,
                "screenshot_proxy_state": "确立空头",
                "screenshot_transition_regime_state": "确立空头",
                "screenshot_transition_regime_start_date": "2026-05-29",
            },
        ]
    }

    snapshot = module.build_latest_screenshot_transition_hybrid_snapshot(analysis)

    assert snapshot == {
        "screenshot_transition_hybrid_state": "确立空头",
        "screenshot_transition_hybrid_transition_date": "2026-06-01",
    }
