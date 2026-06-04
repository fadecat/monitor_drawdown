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
