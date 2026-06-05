from pathlib import Path

import run_etf_rotation_strategy as module


def test_load_rotation_config_reads_simple_20d_strategy():
    config = module.load_rotation_config(Path("etf_rotation_config.yaml"))

    labels = {item["label"] for item in config["targets"]}

    assert "银华日利ETF" in labels
    assert all("code" in item for item in config["targets"])
    assert all(item.get("kind") in {"etf", "lof", "index"} for item in config["targets"])
    assert config.get("defensive_targets") == []
    assert config["strategy"] == {
        "lookback_days": 20,
        "holdings_num": 1,
    }
