from pathlib import Path

import run_etf_rotation_strategy as module


def test_load_rotation_config_reads_simple_20d_strategy():
    config = module.load_rotation_config(Path("etf_rotation_config.yaml"))

    expected_targets = [
        {
            "category": "权益",
            "label": "国证成长100指数",
            "search_keywords": ["国证成长100指数"],
            "code": "980080.CN",
            "kind": "index",
        },
        {
            "category": "权益",
            "label": "国证价值100指数",
            "search_keywords": ["国证价值100指数"],
            "code": "980081.CNI",
            "kind": "index",
        },
        {
            "category": "商品",
            "label": "国证石油天然气指数",
            "search_keywords": ["国证石油天然气指数"],
            "code": "399439.SZ",
            "kind": "index",
        },
        {
            "category": "跨境",
            "label": "纳指ETF国泰",
            "search_keywords": ["纳指ETF国泰"],
            "code": "513100",
            "kind": "etf",
        },
        {
            "category": "商品",
            "label": "黄金ETF易方达",
            "search_keywords": ["黄金ETF易方达"],
            "code": "159934",
            "kind": "etf",
        },
        {
            "category": "防守",
            "label": "银华日利ETF",
            "search_keywords": ["银华日利ETF"],
            "code": "511880",
            "kind": "etf",
        },
    ]

    assert config["targets"] == expected_targets
    assert config.get("defensive_targets") == []
    assert config["strategy"] == {
        "lookback_days": 20,
        "holdings_num": 1,
    }
