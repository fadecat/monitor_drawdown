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


def test_build_rotation_candidate_rejects_non_positive_20d_return():
    candidate = module.build_rotation_candidate(
        latest_snapshot={"label": "测试ETF"},
        series_records=_make_series([120 - index for index in range(21)]),
        strategy_config={"lookback_days": 20},
    )

    assert candidate is None


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
