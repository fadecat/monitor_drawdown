import etf_rotation_strategy as module


def _make_series(closes):
    return [
        {"date": f"2026-01-{index + 1:02d}", "close": float(close)}
        for index, close in enumerate(closes)
    ]


def test_calculate_lookback_return_uses_latest_close_against_lookback_close():
    closes = [float(100 + index) for index in range(21)]

    result = module.calculate_lookback_return(closes, lookback_days=20)

    assert result is not None
    assert round(result, 4) == 0.2000


def test_calculate_lookback_return_returns_none_with_insufficient_history():
    result = module.calculate_lookback_return(
        [float(100 + index) for index in range(20)],
        lookback_days=20,
    )

    assert result is None


def test_calculate_lookback_return_rejects_non_finite_latest_close():
    closes = [float(100 + index) for index in range(20)] + [float("inf")]

    result = module.calculate_lookback_return(closes, lookback_days=20)

    assert result is None


def test_build_rotation_candidate_rejects_non_positive_20d_return():
    candidate = module.build_rotation_candidate(
        latest_snapshot={"label": "测试ETF"},
        series_records=_make_series([120 - index for index in range(21)]),
        strategy_config={"lookback_days": 20},
    )

    assert candidate is None


def test_build_rotation_candidate_returns_none_with_insufficient_history():
    candidate = module.build_rotation_candidate(
        latest_snapshot={"label": "测试ETF"},
        series_records=_make_series([float(100 + index) for index in range(20)]),
        strategy_config={"lookback_days": 20},
    )

    assert candidate is None


def test_build_rotation_candidate_rejects_non_finite_close_data():
    candidate = module.build_rotation_candidate(
        latest_snapshot={"label": "测试ETF"},
        series_records=_make_series(
            [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0,
             float("nan"), 111.0, 112.0, 113.0, 114.0, 115.0, 116.0, 117.0, 118.0,
             119.0, 120.0]
        ),
        strategy_config={"lookback_days": 20},
    )

    assert candidate is None


def test_build_rotation_candidate_rejects_invalid_close_data():
    candidate = module.build_rotation_candidate(
        latest_snapshot={"label": "测试ETF"},
        series_records=[
            {"date": "2026-01-01", "close": 100.0},
            {"date": "2026-01-02", "close": 101.0},
            {"date": "2026-01-03", "close": 102.0},
            {"date": "2026-01-04", "close": 103.0},
            {"date": "2026-01-05", "close": 104.0},
            {"date": "2026-01-06", "close": 105.0},
            {"date": "2026-01-07", "close": 106.0},
            {"date": "2026-01-08", "close": 107.0},
            {"date": "2026-01-09", "close": 108.0},
            {"date": "2026-01-10", "close": 109.0},
            {"date": "2026-01-11", "close": "bad"},
            {"date": "2026-01-12", "close": 111.0},
            {"date": "2026-01-13", "close": 112.0},
            {"date": "2026-01-14", "close": 113.0},
            {"date": "2026-01-15", "close": 114.0},
            {"date": "2026-01-16", "close": 115.0},
            {"date": "2026-01-17", "close": 116.0},
            {"date": "2026-01-18", "close": 117.0},
            {"date": "2026-01-19", "close": 118.0},
            {"date": "2026-01-20", "close": 119.0},
            {"date": "2026-01-21", "close": 120.0},
        ],
        strategy_config={"lookback_days": 20},
    )

    assert candidate is None


def test_build_rotation_candidate_rejects_gap_inside_latest_lookback_window():
    candidate = module.build_rotation_candidate(
        latest_snapshot={"label": "测试ETF"},
        series_records=[
            {"date": "2025-12-31", "close": 99.0},
            {"date": "2026-01-01", "close": 100.0},
            {"date": "2026-01-02", "close": 101.0},
            {"date": "2026-01-03", "close": 102.0},
            {"date": "2026-01-04", "close": 103.0},
            {"date": "2026-01-05", "close": 104.0},
            {"date": "2026-01-06", "close": 105.0},
            {"date": "2026-01-07", "close": 106.0},
            {"date": "2026-01-08", "close": 107.0},
            {"date": "2026-01-09", "close": 108.0},
            {"date": "2026-01-10", "close": ""},
            {"date": "2026-01-11", "close": 110.0},
            {"date": "2026-01-12", "close": 111.0},
            {"date": "2026-01-13", "close": 112.0},
            {"date": "2026-01-14", "close": 113.0},
            {"date": "2026-01-15", "close": 114.0},
            {"date": "2026-01-16", "close": 115.0},
            {"date": "2026-01-17", "close": 116.0},
            {"date": "2026-01-18", "close": 117.0},
            {"date": "2026-01-19", "close": 118.0},
            {"date": "2026-01-20", "close": 119.0},
            {"date": "2026-01-21", "close": 120.0},
        ],
        strategy_config={"lookback_days": 20},
    )

    assert candidate is None


def test_build_rotation_candidate_ignores_invalid_rows_outside_latest_lookback_window():
    candidate = module.build_rotation_candidate(
        latest_snapshot={"label": "测试ETF"},
        series_records=[
            {"date": "2025-12-30", "close": "bad"},
            {"date": "2026-01-01", "close": 100.0},
            {"date": "2026-01-02", "close": 101.0},
            {"date": "2026-01-03", "close": 102.0},
            {"date": "2026-01-04", "close": 103.0},
            {"date": "2026-01-05", "close": 104.0},
            {"date": "2026-01-06", "close": 105.0},
            {"date": "2026-01-07", "close": 106.0},
            {"date": "2026-01-08", "close": 107.0},
            {"date": "2026-01-09", "close": 108.0},
            {"date": "2026-01-10", "close": 109.0},
            {"date": "2026-01-11", "close": 110.0},
            {"date": "2026-01-12", "close": 111.0},
            {"date": "2026-01-13", "close": 112.0},
            {"date": "2026-01-14", "close": 113.0},
            {"date": "2026-01-15", "close": 114.0},
            {"date": "2026-01-16", "close": 115.0},
            {"date": "2026-01-17", "close": 116.0},
            {"date": "2026-01-18", "close": 117.0},
            {"date": "2026-01-19", "close": 118.0},
            {"date": "2026-01-20", "close": 119.0},
            {"date": "2026-01-21", "close": 120.0},
        ],
        strategy_config={"lookback_days": 20},
    )

    assert candidate is not None
    assert round(candidate["return_20d"], 4) == 0.2000


def test_build_rotation_candidate_returns_label_and_20d_return():
    candidate = module.build_rotation_candidate(
        latest_snapshot={"label": "测试ETF"},
        series_records=_make_series([float(100 + index) for index in range(21)]),
        strategy_config={"lookback_days": 20},
    )

    assert candidate is not None
    assert candidate["label"] == "测试ETF"
    assert round(candidate["return_20d"], 4) == 0.2000


def test_select_portfolio_picks_top_1_by_20d_return():
    decision = module.select_portfolio(
        candidates=[
            {"label": "B", "return_20d": 0.08},
            {"label": "A", "return_20d": 0.12},
        ],
        strategy_config={"holdings_num": 1},
    )

    assert [item["label"] for item in decision["selected_holdings"]] == ["A"]
    assert [item["label"] for item in decision["rejected_candidates"]] == ["B"]
    assert decision["selection_reason"] == "top_ranked_candidate"
