import shutil
from pathlib import Path

import inspect_etf_trend_sources as sources
import run_etf_rotation_strategy as module


def _make_workspace_tmp(name: str) -> Path:
    root = Path(".test_artifacts/test_run_etf_rotation_strategy") / name
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    return root


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


def test_load_rotation_config_reads_targets_and_strategy_params():
    config = module.load_rotation_config(Path("etf_rotation_config.yaml"))

    labels = {item["label"] for item in config["targets"]}
    categories = {item["category"] for item in config["targets"]}

    assert {"权益", "商品", "跨境", "防守"}.issubset(categories)
    assert {
        "国证成长100指数",
        "国证价值100指数",
        "国证石油天然气指数",
        "纳指ETF国泰",
        "黄金ETF易方达",
        "银华日利ETF",
    }.issubset(labels)
    assert all("code" in item for item in config["targets"])
    assert all(item.get("kind") in {"etf", "lof", "index"} for item in config["targets"])
    assert any(item.get("kind") == "index" for item in config["targets"])
    assert config["defensive_targets"] == []
    assert config["strategy"] == {
        "lookback_days": 20,
        "holdings_num": 1,
    }


def test_collect_rotation_inputs_can_use_config_targets_instead_of_only_defaults(monkeypatch):
    observed = {}

    def fake_collect_trend_metrics(targets=None, output_root=None):
        observed["targets"] = targets
        observed["output_root"] = output_root
        return [{"label": "通信ETF"}]

    monkeypatch.setattr(sources, "collect_trend_metrics", fake_collect_trend_metrics)

    config = {
        "targets": [{"label": "自定义ETF", "search_keywords": ["自定义ETF"]}],
        "defensive_targets": [],
        "strategy": {},
    }

    result = module.collect_rotation_inputs(config, output_root=Path("tmp-output"))

    assert result == [{"label": "通信ETF"}]
    assert observed["targets"] == config["targets"]
    assert observed["output_root"] == Path("tmp-output")


def test_run_rotation_strategy_writes_ranked_candidates_and_portfolio_decision(
    monkeypatch,
):
    root = _make_workspace_tmp("writes_ranked_candidates_and_portfolio_decision")
    config_path = root / "rotation.yaml"
    config_path.write_text(
        """
targets:
  - label: A
    search_keywords: [A]
defensive_targets:
  - label: 货币ETF
    code: 511880
    kind: etf
strategy:
  holdings_num: 1
  lookback_days: 25
  short_lookback_days: 10
  short_momentum_threshold: 0.0
  min_score_threshold: 0.0
  max_score_threshold: 5.0
  require_state: 确立多头
  rsi_period: 6
  rsi_threshold: 95
  stop_loss: 0.95
  atr_period: 14
  atr_multiplier: 2.0
  atr_trailing_stop: true
""".strip(),
        encoding="utf-8",
    )
    source_root = root / "source"
    (source_root / "series").mkdir(parents=True, exist_ok=True)
    (source_root / "series" / "etf_510001.json").write_text(
        '[{"date":"2026-01-01","close":100.0},{"date":"2026-01-02","close":101.0},{"date":"2026-01-03","close":102.0},{"date":"2026-01-04","close":103.0},{"date":"2026-01-05","close":104.0},{"date":"2026-01-06","close":105.0},{"date":"2026-01-07","close":106.0},{"date":"2026-01-08","close":107.0},{"date":"2026-01-09","close":108.0},{"date":"2026-01-10","close":109.0},{"date":"2026-01-11","close":110.0},{"date":"2026-01-12","close":111.0},{"date":"2026-01-13","close":112.0},{"date":"2026-01-14","close":113.0},{"date":"2026-01-15","close":114.0},{"date":"2026-01-16","close":115.0},{"date":"2026-01-17","close":116.0},{"date":"2026-01-18","close":117.0},{"date":"2026-01-19","close":118.0},{"date":"2026-01-20","close":119.0},{"date":"2026-01-21","close":120.0},{"date":"2026-01-22","close":121.0},{"date":"2026-01-23","close":120.0},{"date":"2026-01-24","close":122.0},{"date":"2026-01-25","close":123.0},{"date":"2026-01-26","close":124.0}]',
        encoding="utf-8",
    )
    (source_root / "series" / "etf_510002.json").write_text(
        '[{"date":"2026-01-01","close":100.0},{"date":"2026-01-02","close":100.5},{"date":"2026-01-03","close":101.0},{"date":"2026-01-04","close":101.5},{"date":"2026-01-05","close":102.0},{"date":"2026-01-06","close":102.5},{"date":"2026-01-07","close":103.0},{"date":"2026-01-08","close":103.5},{"date":"2026-01-09","close":104.0},{"date":"2026-01-10","close":104.5},{"date":"2026-01-11","close":105.0},{"date":"2026-01-12","close":105.5},{"date":"2026-01-13","close":106.0},{"date":"2026-01-14","close":106.5},{"date":"2026-01-15","close":107.0},{"date":"2026-01-16","close":107.5},{"date":"2026-01-17","close":108.0},{"date":"2026-01-18","close":108.5},{"date":"2026-01-19","close":109.0},{"date":"2026-01-20","close":109.5},{"date":"2026-01-21","close":110.0},{"date":"2026-01-22","close":110.4},{"date":"2026-01-23","close":110.1},{"date":"2026-01-24","close":110.8},{"date":"2026-01-25","close":111.2},{"date":"2026-01-26","close":111.6}]',
        encoding="utf-8",
    )

    monkeypatch.setattr(
        module,
        "collect_rotation_inputs",
        lambda config, output_root=None: [
            {
                "label": "A",
                "selected_primary": {"kind": "etf", "code": "510001", "name": "AETF"},
                "screenshot_trend_state": "确立多头",
            },
            {
                "label": "B",
                "selected_primary": {"kind": "etf", "code": "510002", "name": "BETF"},
                "screenshot_trend_state": "确立多头",
            },
        ],
    )

    result = module.run(
        config_path=config_path,
        output_root=root / "out",
        source_output_root=source_root,
    )

    assert [item["label"] for item in result["ranked_candidates"]] == ["A", "B"]
    assert [item["label"] for item in result["portfolio_decision"]["selected_holdings"]] == ["A"]
    assert (root / "out" / "ranked_candidates.json").exists()
    assert (root / "out" / "portfolio_decision.json").exists()


def test_run_rotation_strategy_writes_summary_markdown(monkeypatch):
    root = _make_workspace_tmp("writes_summary_markdown")
    config_path = root / "rotation.yaml"
    config_path.write_text(
        """
targets: []
defensive_targets:
  - label: 货币ETF
    code: 511880
    kind: etf
strategy:
  holdings_num: 1
  lookback_days: 25
  short_lookback_days: 10
  short_momentum_threshold: 0.0
  min_score_threshold: 0.0
  max_score_threshold: 5.0
  require_state: 确立多头
  rsi_period: 6
  rsi_threshold: 95
  stop_loss: 0.95
  atr_period: 14
  atr_multiplier: 2.0
  atr_trailing_stop: true
""".strip(),
        encoding="utf-8",
    )
    source_root = root / "source"
    (source_root / "series").mkdir(parents=True, exist_ok=True)
    (source_root / "series" / "etf_510001.json").write_text(
        '[{"date":"2026-01-01","close":100.0},{"date":"2026-01-02","close":101.0},{"date":"2026-01-03","close":102.0},{"date":"2026-01-04","close":103.0},{"date":"2026-01-05","close":104.0},{"date":"2026-01-06","close":105.0},{"date":"2026-01-07","close":106.0},{"date":"2026-01-08","close":107.0},{"date":"2026-01-09","close":108.0},{"date":"2026-01-10","close":109.0},{"date":"2026-01-11","close":110.0},{"date":"2026-01-12","close":111.0},{"date":"2026-01-13","close":112.0},{"date":"2026-01-14","close":113.0},{"date":"2026-01-15","close":114.0},{"date":"2026-01-16","close":115.0},{"date":"2026-01-17","close":116.0},{"date":"2026-01-18","close":117.0},{"date":"2026-01-19","close":118.0},{"date":"2026-01-20","close":119.0},{"date":"2026-01-21","close":120.0},{"date":"2026-01-22","close":121.0},{"date":"2026-01-23","close":120.0},{"date":"2026-01-24","close":122.0},{"date":"2026-01-25","close":123.0},{"date":"2026-01-26","close":124.0}]',
        encoding="utf-8",
    )

    monkeypatch.setattr(
        module,
        "collect_rotation_inputs",
        lambda config, output_root=None: [
            {
                "label": "A",
                "selected_primary": {"kind": "etf", "code": "510001", "name": "AETF"},
                "screenshot_trend_state": "确立多头",
            }
        ],
    )

    module.run(
        config_path=config_path,
        output_root=root / "out",
        source_output_root=source_root,
    )

    summary = (root / "out" / "summary.md").read_text(encoding="utf-8")

    assert "# ETF Rotation Strategy" in summary
    assert "selected=A" in summary
    assert "defensive_mode=False" in summary
