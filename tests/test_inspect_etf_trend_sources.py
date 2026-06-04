import inspect_etf_trend_sources as module
import monitor_drawdown as md


def _make_attempt(etf_candidates=None, index_candidates=None):
    return {
        "keyword": "dummy",
        "success": True,
        "message": "成功",
        "etf_candidates": etf_candidates or [],
        "index_candidates": index_candidates or [],
        "out_index_debug": [],
    }


def test_resolve_target_prefers_exact_index_for_non_etf_label(monkeypatch):
    target = {
        "label": "沪深300",
        "search_keywords": ["沪深300"],
        "kline_kind": "auto",
    }

    def fake_collect(keyword):
        assert keyword == "沪深300"
        return _make_attempt(
            etf_candidates=[
                {
                    "kind": "etf",
                    "keyword": keyword,
                    "code": "510310",
                    "name": "沪深300ETF易方达",
                    "fund_name": "易方达沪深300ETF",
                    "theme_hits": ["沪深300"],
                }
            ],
            index_candidates=[
                {
                    "kind": "index",
                    "keyword": keyword,
                    "code": "000300",
                    "name": "沪深300",
                    "index_name": "沪深300指数",
                    "theme_hits": ["沪深300"],
                }
            ],
        )

    monkeypatch.setattr(module, "collect_candidates_for_keyword", fake_collect)

    result = module.resolve_target(target)

    assert result["selected_primary"]["kind"] == "index"
    assert result["selected_primary"]["code"] == "000300"


def test_resolve_target_falls_back_to_etf_when_index_is_only_fuzzy_subtheme(monkeypatch):
    target = {
        "label": "标普500",
        "search_keywords": ["标普500"],
        "kline_kind": "auto",
    }

    def fake_collect(keyword):
        assert keyword == "标普500"
        return _make_attempt(
            etf_candidates=[
                {
                    "kind": "etf",
                    "keyword": keyword,
                    "code": "513500",
                    "name": "标普500ETF博时",
                    "fund_name": "博时标普500ETF",
                    "theme_hits": ["标普500"],
                }
            ],
            index_candidates=[
                {
                    "kind": "index",
                    "keyword": keyword,
                    "code": "S35",
                    "name": "标普500医疗保健等权重指数",
                    "index_name": "标普500医疗保健等权重指数",
                    "theme_hits": ["医疗", "标普500"],
                }
            ],
        )

    monkeypatch.setattr(module, "collect_candidates_for_keyword", fake_collect)

    result = module.resolve_target(target)

    assert result["selected_primary"]["kind"] == "etf"
    assert result["selected_primary"]["code"] == "513500"


def test_resolve_target_ignores_irrelevant_index_theme_match(monkeypatch):
    target = {
        "label": "30年国债",
        "search_keywords": ["30年国债"],
        "kline_kind": "auto",
    }

    def fake_collect(keyword):
        assert keyword == "30年国债"
        return _make_attempt(
            etf_candidates=[
                {
                    "kind": "etf",
                    "keyword": keyword,
                    "code": "511090",
                    "name": "30年国债ETF鹏扬",
                    "fund_name": "鹏扬中债-30年期国债ETF",
                    "theme_hits": ["30年国债"],
                }
            ],
            index_candidates=[
                {
                    "kind": "index",
                    "keyword": keyword,
                    "code": "931798",
                    "name": "光伏龙头30",
                    "index_name": "中证光伏龙头30指数",
                    "theme_hits": ["光伏"],
                }
            ],
        )

    monkeypatch.setattr(module, "collect_candidates_for_keyword", fake_collect)

    result = module.resolve_target(target)

    assert result["selected_primary"]["kind"] == "etf"
    assert result["selected_primary"]["code"] == "511090"


def test_resolve_target_accepts_etf_keyword_contains_without_manual_theme_token(monkeypatch):
    target = {
        "label": "豆粕ETF",
        "search_keywords": ["豆粕", "豆粕ETF"],
        "kline_kind": "auto",
    }

    def fake_collect(keyword):
        return _make_attempt(
            etf_candidates=[
                {
                    "kind": "etf",
                    "keyword": keyword,
                    "code": "159985",
                    "name": "豆粕ETF华夏",
                    "fund_name": "华夏饲料豆粕期货ETF",
                    "theme_hits": [],
                }
            ],
            index_candidates=[],
        )

    monkeypatch.setattr(module, "collect_candidates_for_keyword", fake_collect)

    result = module.resolve_target(target)

    assert result["selected_primary"]["kind"] == "etf"
    assert result["selected_primary"]["code"] == "159985"


def test_resolve_target_prefers_etf_label_even_when_index_exact_keyword_scores_higher(monkeypatch):
    target = {
        "label": "半导体ETF",
        "search_keywords": ["半导体", "半导体ETF"],
        "kline_kind": "auto",
    }

    def fake_collect(keyword):
        return _make_attempt(
            etf_candidates=[
                {
                    "kind": "etf",
                    "keyword": keyword,
                    "code": "513310",
                    "name": "中韩半导体ETF华泰柏瑞",
                    "fund_name": "华泰柏瑞中证韩交所中韩半导体ETF(QDII)",
                    "theme_hits": ["半导体"],
                }
            ],
            index_candidates=[
                {
                    "kind": "index",
                    "keyword": keyword,
                    "code": "h30184",
                    "name": "半导体",
                    "index_name": "中证全指半导体产品与设备指数",
                    "theme_hits": ["半导体"],
                }
            ],
        )

    monkeypatch.setattr(module, "collect_candidates_for_keyword", fake_collect)

    result = module.resolve_target(target)

    assert result["selected_primary"]["kind"] == "etf"
    assert result["selected_primary"]["code"] == "513310"


def test_build_index_eod_price_url_preserves_non_numeric_prefixes():
    assert md.build_index_eod_price_url("h30269").endswith("index_eod_price_h30269.json")
    assert md.build_index_eod_price_url("SPX").endswith("index_eod_price_SPX.json")


def test_build_summary_includes_trend_state_bias20_and_transition_date():
    resolved = [
        {
            "label": "煤炭ETF",
            "status": "ok",
            "selected_primary": {"kind": "etf", "code": "515220", "name": "煤炭ETF国泰"},
        }
    ]
    kline_results = [
        {
            "label": "煤炭ETF",
            "status": "ok",
            "selected_primary": {"kind": "etf", "code": "515220", "name": "煤炭ETF国泰"},
        }
    ]
    trend_results = [
        {
            "label": "煤炭ETF",
            "status": "ok",
            "latest_snapshot": {
                "bias20": 0.0256,
                "trend_state": "强势回落",
                "latest_transition_date": "2026-05-28",
            },
        }
    ]

    summary = module.build_summary(resolved, kline_results, trend_results)

    assert "trend=强势回落" in summary
    assert "bias20=0.0256" in summary
    assert "transition=2026-05-28" in summary


def test_build_trend_benchmark_diffs_compares_bias_state_and_transition():
    snapshots = [
        {
            "label": "煤炭ETF",
            "selected_primary": {"kind": "etf", "code": "515220", "name": "煤炭ETF国泰"},
            "latest_date": "2026-06-04",
            "close": 1.2345,
            "bias20_raw": 0.0312,
            "bias20": 0.0256,
            "direction5": -0.0041,
            "trend_state": "强势回落",
            "latest_transition_date": "2026-05-28",
        }
    ]
    benchmarks = [
        {
            "label": "煤炭ETF",
            "as_of_date": "2026-06-04",
            "expected_bias20": 0.0248,
            "expected_trend_state": "强势回落",
            "expected_transition_date": "2026-05-27",
        }
    ]

    diffs = module.build_trend_benchmark_diffs(snapshots, benchmarks)

    assert diffs == [
        {
            "label": "煤炭ETF",
            "as_of_date": "2026-06-04",
            "actual_bias20": 0.0256,
            "expected_bias20": 0.0248,
            "bias20_diff": 0.0008,
            "actual_trend_state": "强势回落",
            "expected_trend_state": "强势回落",
            "trend_state_match": True,
            "actual_transition_date": "2026-05-28",
            "expected_transition_date": "2026-05-27",
            "transition_date_match": False,
        }
    ]
