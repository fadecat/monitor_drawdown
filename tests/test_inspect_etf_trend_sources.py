import json
import shutil
from pathlib import Path

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


def test_build_screenshot_proxy_benchmark_diffs_compares_proxy_fields():
    snapshots = [
        {
            "label": "煤炭ETF",
            "selected_primary": {"kind": "etf", "code": "515220", "name": "煤炭ETF国泰"},
            "screenshot_bias_value": 0.1008,
            "screenshot_trend_state": "确立多头",
            "screenshot_transition_date": "2026-05-29",
        }
    ]
    benchmarks = [
        {
            "label": "煤炭ETF",
            "as_of_date": "2026-06-03",
            "expected_bias20": 0.1009,
            "expected_trend_state": "确立多头",
            "expected_transition_date": "2026-05-29",
        }
    ]

    diffs = module.build_screenshot_proxy_benchmark_diffs(snapshots, benchmarks)

    assert diffs == [
        {
            "label": "煤炭ETF",
            "as_of_date": "2026-06-03",
            "actual_bias20": 0.1008,
            "expected_bias20": 0.1009,
            "bias20_diff": -0.0001,
            "actual_trend_state": "确立多头",
            "expected_trend_state": "确立多头",
            "trend_state_match": True,
            "actual_transition_date": "2026-05-29",
            "expected_transition_date": "2026-05-29",
            "transition_date_match": True,
        }
    ]


def test_build_screenshot_proxy_transition_diagnostics_summarizes_directional_skew():
    diffs = [
        {
            "label": "标普500",
            "actual_trend_state": "确立多头",
            "expected_trend_state": "确立多头",
            "actual_transition_date": "2026-04-09",
            "expected_transition_date": "2026-04-30",
            "transition_date_match": False,
        },
        {
            "label": "黄金ETF",
            "actual_trend_state": "确立空头",
            "expected_trend_state": "确立空头",
            "actual_transition_date": "2026-05-25",
            "expected_transition_date": "2026-04-24",
            "transition_date_match": False,
        },
        {
            "label": "红利低波",
            "actual_trend_state": "震荡中",
            "expected_trend_state": "震荡中",
            "actual_transition_date": "2026-06-01",
            "expected_transition_date": "2026-06-01",
            "transition_date_match": True,
        },
    ]

    diagnostics = module.build_screenshot_proxy_transition_diagnostics(diffs)

    assert diagnostics == {
        "counts": {
            "total": 3,
            "exact": 1,
            "earlier": 1,
            "later": 1,
            "within_3_days": 1,
            "within_10_days": 1,
        },
        "by_state": [
            {
                "state": "确立多头",
                "count": 1,
                "exact": 0,
                "earlier": 1,
                "later": 0,
                "mean_abs_delta_days": 21.0,
            },
            {
                "state": "确立空头",
                "count": 1,
                "exact": 0,
                "earlier": 0,
                "later": 1,
                "mean_abs_delta_days": 31.0,
            },
            {
                "state": "震荡中",
                "count": 1,
                "exact": 1,
                "earlier": 0,
                "later": 0,
                "mean_abs_delta_days": 0.0,
            },
        ],
        "top_outliers": [
            {
                "label": "黄金ETF",
                "state": "确立空头",
                "actual_transition_date": "2026-05-25",
                "expected_transition_date": "2026-04-24",
                "delta_days": 31,
                "abs_delta_days": 31,
            },
            {
                "label": "标普500",
                "state": "确立多头",
                "actual_transition_date": "2026-04-09",
                "expected_transition_date": "2026-04-30",
                "delta_days": -21,
                "abs_delta_days": 21,
            },
            {
                "label": "红利低波",
                "state": "震荡中",
                "actual_transition_date": "2026-06-01",
                "expected_transition_date": "2026-06-01",
                "delta_days": 0,
                "abs_delta_days": 0,
            },
        ],
    }


def test_build_screenshot_transition_regime_benchmark_diffs_compares_regime_fields():
    snapshots = [
        {
            "label": "煤炭ETF",
            "selected_primary": {"kind": "etf", "code": "515220", "name": "煤炭ETF国泰"},
            "screenshot_bias_value": 0.1008,
            "screenshot_transition_regime_state": "确立空头",
            "screenshot_transition_regime_transition_date": "2026-05-28",
        }
    ]
    benchmarks = [
        {
            "label": "煤炭ETF",
            "as_of_date": "2026-06-03",
            "expected_bias20": 0.1009,
            "expected_trend_state": "确立空头",
            "expected_transition_date": "2026-05-29",
        }
    ]

    diffs = module.build_screenshot_transition_regime_benchmark_diffs(
        snapshots, benchmarks
    )

    assert diffs == [
        {
            "label": "煤炭ETF",
            "as_of_date": "2026-06-03",
            "actual_bias20": 0.1008,
            "expected_bias20": 0.1009,
            "bias20_diff": -0.0001,
            "actual_trend_state": "确立空头",
            "expected_trend_state": "确立空头",
            "trend_state_match": True,
            "actual_transition_date": "2026-05-28",
            "expected_transition_date": "2026-05-29",
            "transition_date_match": False,
        }
    ]


def test_build_screenshot_transition_hybrid_benchmark_diffs_keeps_main_state_and_hybrid_date():
    snapshots = [
        {
            "label": "煤炭ETF",
            "selected_primary": {"kind": "etf", "code": "515220", "name": "煤炭ETF国泰"},
            "screenshot_bias_value": 0.1008,
            "screenshot_transition_hybrid_state": "确立多头",
            "screenshot_transition_hybrid_transition_date": "2026-05-28",
        }
    ]
    benchmarks = [
        {
            "label": "煤炭ETF",
            "as_of_date": "2026-06-03",
            "expected_bias20": 0.1009,
            "expected_trend_state": "确立多头",
            "expected_transition_date": "2026-05-29",
        }
    ]

    diffs = module.build_screenshot_transition_hybrid_benchmark_diffs(
        snapshots, benchmarks
    )

    assert diffs == [
        {
            "label": "煤炭ETF",
            "as_of_date": "2026-06-03",
            "actual_bias20": 0.1008,
            "expected_bias20": 0.1009,
            "bias20_diff": -0.0001,
            "actual_trend_state": "确立多头",
            "expected_trend_state": "确立多头",
            "trend_state_match": True,
            "actual_transition_date": "2026-05-28",
            "expected_transition_date": "2026-05-29",
            "transition_date_match": False,
        }
    ]


def test_build_screenshot_transition_bias_sign_benchmark_diffs_keeps_main_state_and_bias_sign_date():
    snapshots = [
        {
            "label": "煤炭ETF",
            "selected_primary": {"kind": "etf", "code": "515220", "name": "煤炭ETF国泰"},
            "screenshot_bias_value": 0.1008,
            "screenshot_transition_bias_sign_state": "确立多头",
            "screenshot_transition_bias_sign_transition_date": "2026-05-27",
        }
    ]
    benchmarks = [
        {
            "label": "煤炭ETF",
            "as_of_date": "2026-06-03",
            "expected_bias20": 0.1009,
            "expected_trend_state": "确立多头",
            "expected_transition_date": "2026-05-29",
        }
    ]

    diffs = module.build_screenshot_transition_bias_sign_benchmark_diffs(
        snapshots, benchmarks
    )

    assert diffs == [
        {
            "label": "煤炭ETF",
            "as_of_date": "2026-06-03",
            "actual_bias20": 0.1008,
            "expected_bias20": 0.1009,
            "bias20_diff": -0.0001,
            "actual_trend_state": "确立多头",
            "expected_trend_state": "确立多头",
            "trend_state_match": True,
            "actual_transition_date": "2026-05-27",
            "expected_transition_date": "2026-05-29",
            "transition_date_match": False,
        }
    ]


def test_build_trend_benchmark_diffs_degrades_bad_expected_bias20_without_crashing():
    snapshots = [
        {
            "label": "煤炭ETF",
            "latest_date": "2026-06-04",
            "bias20": 0.0256,
            "trend_state": "强势回落",
            "latest_transition_date": "2026-05-28",
        }
    ]
    benchmarks = [
        {
            "label": "煤炭ETF",
            "as_of_date": "2026-06-04",
            "expected_bias20": "bad",
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
            "expected_bias20": "bad",
            "bias20_diff": None,
            "actual_trend_state": "强势回落",
            "expected_trend_state": "强势回落",
            "trend_state_match": True,
            "actual_transition_date": "2026-05-28",
            "expected_transition_date": "2026-05-27",
            "transition_date_match": False,
        }
    ]


def test_build_summary_ok_count_reflects_trend_success_not_only_kline_success():
    resolved = [{"label": "煤炭ETF", "status": "ok", "selected_primary": None}]
    kline_results = [{"label": "煤炭ETF", "status": "ok", "selected_primary": None}]
    trend_results = [{"label": "煤炭ETF", "status": "trend_failed", "selected_primary": None}]

    summary = module.build_summary(resolved, kline_results, trend_results)

    assert "- ok: 0" in summary
    assert "- trend_failed: 1" in summary


def test_materialize_trend_analysis_writes_daily_records_to_expected_series_file(monkeypatch):
    output_root = _make_workspace_tmp(
        "materialize_trend_analysis_writes_daily_records_to_expected_series_file"
    )
    monkeypatch.setattr(module, "SERIES_ANALYSIS_DIR", output_root / "series_analysis")

    source_records = [{"date": "2026-06-03", "close": 1.23}]
    analysis_records = [
        {
            "date": "2026-06-03",
            "close": 1.23,
            "ma20": 1.2,
            "bias20_raw": 0.025,
            "bias20": 0.02,
            "direction5": -0.004,
            "trend_state": "强势回落",
            "state_candidate_changed": False,
            "transition_confirmed": False,
            "transition_date": None,
        }
    ]
    analysis_payload = {
        "records": analysis_records,
        "latest_transition_date": None,
        "latest_valid_state": "强势回落",
        "latest_valid_date": "2026-06-03",
    }
    latest_snapshot = {
        "latest_date": "2026-06-03",
        "close": 1.23,
        "bias20_raw": 0.025,
        "bias20": 0.02,
        "direction5": -0.004,
        "trend_state": "强势回落",
        "latest_transition_date": None,
    }

    monkeypatch.setattr(module, "read_json", lambda path: source_records)
    monkeypatch.setattr(
        module.trend_analysis,
        "analyze_trend_series",
        lambda records: analysis_payload,
    )
    monkeypatch.setattr(
        module.trend_analysis,
        "build_latest_trend_snapshot",
        lambda analysis: latest_snapshot,
    )

    result = module.materialize_trend_analysis(
        {
            "label": "煤炭ETF",
            "status": "ok",
            "selected_primary": {"kind": "etf", "code": "515220", "name": "煤炭ETF国泰"},
            "series_file": "series/etf_515220.json",
        }
    )

    expected_path = output_root / "series_analysis" / "etf_515220.json"
    assert result["analysis_file"] == expected_path.as_posix()
    assert json.loads(expected_path.read_text(encoding="utf-8")) == analysis_records
    assert result["latest_snapshot"] == latest_snapshot


def _make_workspace_tmp(name: str) -> Path:
    root = Path(".test_artifacts/test_inspect_etf_trend_sources") / name
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _install_run_stubs(monkeypatch, output_root: Path):
    monkeypatch.setattr(module, "OUTPUT_ROOT", output_root)
    monkeypatch.setattr(module, "SERIES_DIR", output_root / "series")
    monkeypatch.setattr(module, "SERIES_ANALYSIS_DIR", output_root / "series_analysis")
    monkeypatch.setattr(module, "MANUAL_TREND_BENCHMARKS_PATH", output_root / "manual_trend_benchmarks.json")
    monkeypatch.setattr(module, "TREND_METRICS_SUMMARY_PATH", output_root / "trend_metrics_summary.json")
    monkeypatch.setattr(module, "TREND_BENCHMARK_DIFF_PATH", output_root / "trend_benchmark_diff.json")
    monkeypatch.setattr(
        module,
        "SCREENSHOT_PROXY_BENCHMARK_DIFF_PATH",
        output_root / "screenshot_proxy_benchmark_diff.json",
    )
    monkeypatch.setattr(
        module,
        "SCREENSHOT_PROXY_TRANSITION_DIAGNOSTICS_PATH",
        output_root / "screenshot_proxy_transition_diagnostics.json",
    )
    monkeypatch.setattr(
        module,
        "SCREENSHOT_TRANSITION_REGIME_BENCHMARK_DIFF_PATH",
        output_root / "screenshot_transition_regime_benchmark_diff.json",
    )
    monkeypatch.setattr(
        module,
        "SCREENSHOT_TRANSITION_REGIME_DIAGNOSTICS_PATH",
        output_root / "screenshot_transition_regime_diagnostics.json",
    )
    monkeypatch.setattr(
        module,
        "SCREENSHOT_TRANSITION_HYBRID_BENCHMARK_DIFF_PATH",
        output_root / "screenshot_transition_hybrid_benchmark_diff.json",
    )
    monkeypatch.setattr(
        module,
        "SCREENSHOT_TRANSITION_HYBRID_DIAGNOSTICS_PATH",
        output_root / "screenshot_transition_hybrid_diagnostics.json",
    )
    monkeypatch.setattr(
        module,
        "SCREENSHOT_TRANSITION_BIAS_SIGN_BENCHMARK_DIFF_PATH",
        output_root / "screenshot_transition_bias_sign_benchmark_diff.json",
    )
    monkeypatch.setattr(
        module,
        "SCREENSHOT_TRANSITION_BIAS_SIGN_DIAGNOSTICS_PATH",
        output_root / "screenshot_transition_bias_sign_diagnostics.json",
    )
    monkeypatch.setattr(
        module,
        "DEFAULT_TARGETS",
        [{"label": "煤炭ETF", "search_keywords": ["煤炭ETF"], "kline_kind": "auto"}],
    )
    monkeypatch.setattr(module, "today_range_strings", lambda: ("20250101", "20260101"))
    monkeypatch.setattr(
        module,
        "resolve_target",
        lambda target: {
            "label": target["label"],
            "search_keywords": target["search_keywords"],
            "search_attempts": [{"keyword": "煤炭ETF", "success": True}],
            "etf_candidate": None,
            "index_candidate": None,
            "selected_primary": {"kind": "etf", "code": "515220", "name": "煤炭ETF国泰"},
            "status": "ok",
        },
    )
    monkeypatch.setattr(
        module,
        "materialize_kline",
        lambda item: {
            "label": item["label"],
            "status": "ok",
            "selected_primary": item["selected_primary"],
            "series_file": "series/etf_515220.json",
        },
    )
    monkeypatch.setattr(
        module,
        "materialize_trend_analysis",
        lambda item: {
            "label": item["label"],
            "status": "ok",
            "selected_primary": item["selected_primary"],
            "latest_snapshot": {
                "latest_date": "2026-06-04",
                "close": 1.2345,
                "bias20_raw": 0.0312,
                "bias20": 0.0256,
                "direction5": -0.0041,
                "trend_state": "强势回落",
                "latest_transition_date": "2026-05-28",
                "screenshot_bias_value": 0.0248,
                "screenshot_trend_state": "确立多头",
                "screenshot_transition_date": "2026-05-27",
                "screenshot_transition_regime_state": "确立空头",
                "screenshot_transition_regime_transition_date": "2026-05-26",
                "screenshot_transition_bias_sign_state": "确立多头",
                "screenshot_transition_bias_sign_transition_date": "2026-05-27",
                "screenshot_transition_hybrid_state": "确立多头",
                "screenshot_transition_hybrid_transition_date": "2026-05-28",
            },
        },
    )
    return output_root


def test_run_writes_trend_diff_when_manual_benchmarks_present(monkeypatch):
    output_root = _install_run_stubs(
        monkeypatch, _make_workspace_tmp("run_writes_trend_diff_when_manual_benchmarks_present")
    )
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "manual_trend_benchmarks.json").write_text(
        json.dumps(
            [
                {
                    "label": "煤炭ETF",
                    "as_of_date": "2026-06-04",
                    "expected_bias20": 0.0248,
                    "expected_trend_state": "强势回落",
                    "expected_transition_date": "2026-05-27",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    module.run()

    diff_payload = json.loads((output_root / "trend_benchmark_diff.json").read_text(encoding="utf-8"))
    assert diff_payload == [
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
    assert json.loads(
        (output_root / "screenshot_proxy_benchmark_diff.json").read_text(encoding="utf-8")
    ) == [
        {
            "label": "煤炭ETF",
            "as_of_date": "2026-06-04",
            "actual_bias20": 0.0248,
            "expected_bias20": 0.0248,
            "bias20_diff": 0.0,
            "actual_trend_state": "确立多头",
            "expected_trend_state": "强势回落",
            "trend_state_match": False,
            "actual_transition_date": "2026-05-27",
            "expected_transition_date": "2026-05-27",
            "transition_date_match": True,
        }
    ]
    assert json.loads(
        (output_root / "screenshot_proxy_transition_diagnostics.json").read_text(
            encoding="utf-8"
        )
    ) == {
        "counts": {
            "total": 1,
            "exact": 1,
            "earlier": 0,
            "later": 0,
            "within_3_days": 1,
            "within_10_days": 1,
        },
        "by_state": [
            {
                "state": "强势回落",
                "count": 1,
                "exact": 1,
                "earlier": 0,
                "later": 0,
                "mean_abs_delta_days": 0.0,
            }
        ],
        "top_outliers": [
            {
                "label": "煤炭ETF",
                "state": "强势回落",
                "actual_transition_date": "2026-05-27",
                "expected_transition_date": "2026-05-27",
                "delta_days": 0,
                "abs_delta_days": 0,
            }
        ],
    }
    assert json.loads(
        (output_root / "screenshot_transition_regime_benchmark_diff.json").read_text(
            encoding="utf-8"
        )
    ) == [
        {
            "label": "煤炭ETF",
            "as_of_date": "2026-06-04",
            "actual_bias20": 0.0248,
            "expected_bias20": 0.0248,
            "bias20_diff": 0.0,
            "actual_trend_state": "确立空头",
            "expected_trend_state": "强势回落",
            "trend_state_match": False,
            "actual_transition_date": "2026-05-26",
            "expected_transition_date": "2026-05-27",
            "transition_date_match": False,
        }
    ]
    assert json.loads(
        (output_root / "screenshot_transition_regime_diagnostics.json").read_text(
            encoding="utf-8"
        )
    ) == {
        "counts": {
            "total": 1,
            "exact": 0,
            "earlier": 1,
            "later": 0,
            "within_3_days": 1,
            "within_10_days": 1,
        },
        "by_state": [
            {
                "state": "强势回落",
                "count": 1,
                "exact": 0,
                "earlier": 1,
                "later": 0,
                "mean_abs_delta_days": 1.0,
            }
        ],
        "top_outliers": [
            {
                "label": "煤炭ETF",
                "state": "强势回落",
                "actual_transition_date": "2026-05-26",
                "expected_transition_date": "2026-05-27",
                "delta_days": -1,
                "abs_delta_days": 1,
            }
        ],
    }
    assert json.loads(
        (output_root / "screenshot_transition_hybrid_benchmark_diff.json").read_text(
            encoding="utf-8"
        )
    ) == [
        {
            "label": "煤炭ETF",
            "as_of_date": "2026-06-04",
            "actual_bias20": 0.0248,
            "expected_bias20": 0.0248,
            "bias20_diff": 0.0,
            "actual_trend_state": "确立多头",
            "expected_trend_state": "强势回落",
            "trend_state_match": False,
            "actual_transition_date": "2026-05-28",
            "expected_transition_date": "2026-05-27",
            "transition_date_match": False,
        }
    ]
    assert json.loads(
        (output_root / "screenshot_transition_hybrid_diagnostics.json").read_text(
            encoding="utf-8"
        )
    ) == {
        "counts": {
            "total": 1,
            "exact": 0,
            "earlier": 0,
            "later": 1,
            "within_3_days": 1,
            "within_10_days": 1,
        },
        "by_state": [
            {
                "state": "强势回落",
                "count": 1,
                "exact": 0,
                "earlier": 0,
                "later": 1,
                "mean_abs_delta_days": 1.0,
            }
        ],
        "top_outliers": [
            {
                "label": "煤炭ETF",
                "state": "强势回落",
                "actual_transition_date": "2026-05-28",
                "expected_transition_date": "2026-05-27",
                "delta_days": 1,
                "abs_delta_days": 1,
            }
        ],
    }
    assert json.loads(
        (output_root / "screenshot_transition_bias_sign_benchmark_diff.json").read_text(
            encoding="utf-8"
        )
    ) == [
        {
            "label": "煤炭ETF",
            "as_of_date": "2026-06-04",
            "actual_bias20": 0.0248,
            "expected_bias20": 0.0248,
            "bias20_diff": 0.0,
            "actual_trend_state": "确立多头",
            "expected_trend_state": "强势回落",
            "trend_state_match": False,
            "actual_transition_date": "2026-05-27",
            "expected_transition_date": "2026-05-27",
            "transition_date_match": True,
        }
    ]
    assert json.loads(
        (output_root / "screenshot_transition_bias_sign_diagnostics.json").read_text(
            encoding="utf-8"
        )
    ) == {
        "counts": {
            "total": 1,
            "exact": 1,
            "earlier": 0,
            "later": 0,
            "within_3_days": 1,
            "within_10_days": 1,
        },
        "by_state": [
            {
                "state": "强势回落",
                "count": 1,
                "exact": 1,
                "earlier": 0,
                "later": 0,
                "mean_abs_delta_days": 0.0,
            }
        ],
        "top_outliers": [
            {
                "label": "煤炭ETF",
                "state": "强势回落",
                "actual_transition_date": "2026-05-27",
                "expected_transition_date": "2026-05-27",
                "delta_days": 0,
                "abs_delta_days": 0,
            }
        ],
    }


def test_run_removes_stale_trend_diff_when_benchmarks_absent(monkeypatch):
    output_root = _install_run_stubs(
        monkeypatch, _make_workspace_tmp("run_removes_stale_trend_diff_when_benchmarks_absent")
    )
    output_root.mkdir(parents=True, exist_ok=True)
    stale_path = output_root / "trend_benchmark_diff.json"
    stale_proxy_path = output_root / "screenshot_proxy_benchmark_diff.json"
    stale_diag_path = output_root / "screenshot_proxy_transition_diagnostics.json"
    stale_regime_path = output_root / "screenshot_transition_regime_benchmark_diff.json"
    stale_regime_diag_path = output_root / "screenshot_transition_regime_diagnostics.json"
    stale_hybrid_path = output_root / "screenshot_transition_hybrid_benchmark_diff.json"
    stale_hybrid_diag_path = output_root / "screenshot_transition_hybrid_diagnostics.json"
    stale_bias_sign_path = output_root / "screenshot_transition_bias_sign_benchmark_diff.json"
    stale_bias_sign_diag_path = output_root / "screenshot_transition_bias_sign_diagnostics.json"
    stale_path.write_text("stale", encoding="utf-8")
    stale_proxy_path.write_text("stale", encoding="utf-8")
    stale_diag_path.write_text("stale", encoding="utf-8")
    stale_regime_path.write_text("stale", encoding="utf-8")
    stale_regime_diag_path.write_text("stale", encoding="utf-8")
    stale_hybrid_path.write_text("stale", encoding="utf-8")
    stale_hybrid_diag_path.write_text("stale", encoding="utf-8")
    stale_bias_sign_path.write_text("stale", encoding="utf-8")
    stale_bias_sign_diag_path.write_text("stale", encoding="utf-8")

    module.run()

    assert not stale_path.exists()
    assert not stale_proxy_path.exists()
    assert not stale_diag_path.exists()
    assert not stale_regime_path.exists()
    assert not stale_regime_diag_path.exists()
    assert not stale_hybrid_path.exists()
    assert not stale_hybrid_diag_path.exists()
    assert not stale_bias_sign_path.exists()
    assert not stale_bias_sign_diag_path.exists()
    assert json.loads((output_root / "trend_metrics_summary.json").read_text(encoding="utf-8")) == [
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
            "screenshot_bias_value": 0.0248,
            "screenshot_trend_state": "确立多头",
            "screenshot_transition_date": "2026-05-27",
            "screenshot_transition_regime_state": "确立空头",
            "screenshot_transition_regime_transition_date": "2026-05-26",
            "screenshot_transition_bias_sign_state": "确立多头",
            "screenshot_transition_bias_sign_transition_date": "2026-05-27",
            "screenshot_transition_hybrid_state": "确立多头",
            "screenshot_transition_hybrid_transition_date": "2026-05-28",
        }
    ]


def test_run_skips_invalid_benchmarks_and_removes_stale_diff(monkeypatch):
    output_root = _install_run_stubs(
        monkeypatch, _make_workspace_tmp("run_skips_invalid_benchmarks_and_removes_stale_diff")
    )
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "manual_trend_benchmarks.json").write_text('{"bad": true}', encoding="utf-8")
    stale_path = output_root / "trend_benchmark_diff.json"
    stale_proxy_path = output_root / "screenshot_proxy_benchmark_diff.json"
    stale_diag_path = output_root / "screenshot_proxy_transition_diagnostics.json"
    stale_regime_path = output_root / "screenshot_transition_regime_benchmark_diff.json"
    stale_regime_diag_path = output_root / "screenshot_transition_regime_diagnostics.json"
    stale_hybrid_path = output_root / "screenshot_transition_hybrid_benchmark_diff.json"
    stale_hybrid_diag_path = output_root / "screenshot_transition_hybrid_diagnostics.json"
    stale_bias_sign_path = output_root / "screenshot_transition_bias_sign_benchmark_diff.json"
    stale_bias_sign_diag_path = output_root / "screenshot_transition_bias_sign_diagnostics.json"
    stale_path.write_text("stale", encoding="utf-8")
    stale_proxy_path.write_text("stale", encoding="utf-8")
    stale_diag_path.write_text("stale", encoding="utf-8")
    stale_regime_path.write_text("stale", encoding="utf-8")
    stale_regime_diag_path.write_text("stale", encoding="utf-8")
    stale_hybrid_path.write_text("stale", encoding="utf-8")
    stale_hybrid_diag_path.write_text("stale", encoding="utf-8")
    stale_bias_sign_path.write_text("stale", encoding="utf-8")
    stale_bias_sign_diag_path.write_text("stale", encoding="utf-8")

    module.run()

    assert not stale_path.exists()
    assert not stale_proxy_path.exists()
    assert not stale_diag_path.exists()
    assert not stale_regime_path.exists()
    assert not stale_regime_diag_path.exists()
    assert not stale_hybrid_path.exists()
    assert not stale_hybrid_diag_path.exists()
    assert not stale_bias_sign_path.exists()
    assert not stale_bias_sign_diag_path.exists()
    assert (output_root / "trend_analysis_results.json").exists()
    assert (output_root / "trend_metrics_summary.json").exists()


def test_run_skips_bad_benchmark_entry_values_without_crashing(monkeypatch):
    output_root = _install_run_stubs(
        monkeypatch, _make_workspace_tmp("run_skips_bad_benchmark_entry_values_without_crashing")
    )
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "manual_trend_benchmarks.json").write_text(
        json.dumps(
            [
                {
                    "label": "煤炭ETF",
                    "as_of_date": "2026-06-04",
                    "expected_bias20": "bad",
                    "expected_trend_state": "强势回落",
                    "expected_transition_date": "2026-05-27",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    module.run()

    assert (output_root / "trend_analysis_results.json").exists()
    assert json.loads((output_root / "trend_benchmark_diff.json").read_text(encoding="utf-8")) == [
        {
            "label": "煤炭ETF",
            "as_of_date": "2026-06-04",
            "actual_bias20": 0.0256,
            "expected_bias20": "bad",
            "bias20_diff": None,
            "actual_trend_state": "强势回落",
            "expected_trend_state": "强势回落",
            "trend_state_match": True,
            "actual_transition_date": "2026-05-28",
            "expected_transition_date": "2026-05-27",
            "transition_date_match": False,
        }
    ]
    assert json.loads(
        (output_root / "screenshot_proxy_benchmark_diff.json").read_text(encoding="utf-8")
    ) == [
        {
            "label": "煤炭ETF",
            "as_of_date": "2026-06-04",
            "actual_bias20": 0.0248,
            "expected_bias20": "bad",
            "bias20_diff": None,
            "actual_trend_state": "确立多头",
            "expected_trend_state": "强势回落",
            "trend_state_match": False,
            "actual_transition_date": "2026-05-27",
            "expected_transition_date": "2026-05-27",
            "transition_date_match": True,
        }
    ]


def test_load_manual_trend_benchmarks_accepts_fillable_null_entries():
    root = _make_workspace_tmp("load_manual_trend_benchmarks_accepts_fillable_null_entries")
    path = root / "manual_trend_benchmarks.json"
    path.write_text(
        json.dumps(
            [
                {
                    "label": "煤炭ETF",
                    "as_of_date": "2026-06-03",
                    "expected_bias20": None,
                    "expected_trend_state": None,
                    "expected_transition_date": None,
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    assert module.load_manual_trend_benchmarks(path) == [
        {
            "label": "煤炭ETF",
            "as_of_date": "2026-06-03",
            "expected_bias20": None,
            "expected_trend_state": None,
            "expected_transition_date": None,
        }
    ]
