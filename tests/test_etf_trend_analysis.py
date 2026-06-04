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
