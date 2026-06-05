import shutil
from pathlib import Path
import json

import pytest

import run_etf_rotation_strategy as module


def _make_workspace_tmp(name: str) -> Path:
    root = Path("tests") / ".tmp" / name
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    return root


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
    expected_config = {
        "targets": expected_targets,
        "defensive_targets": [],
        "strategy": {
            "lookback_days": 20,
            "holdings_num": 1,
        },
    }

    assert config == expected_config


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
  - label: B
    search_keywords: [B]
defensive_targets: []
strategy:
  lookback_days: 20
  holdings_num: 1
""".strip(),
        encoding="utf-8",
    )
    source_root = root / "source"
    (source_root / "series").mkdir(parents=True, exist_ok=True)
    (source_root / "series" / "etf_510001.json").write_text(
        '[{"date":"2026-01-01","close":100.0},{"date":"2026-01-02","close":101.0},{"date":"2026-01-03","close":102.0},{"date":"2026-01-04","close":103.0},{"date":"2026-01-05","close":104.0},{"date":"2026-01-06","close":105.0},{"date":"2026-01-07","close":106.0},{"date":"2026-01-08","close":107.0},{"date":"2026-01-09","close":108.0},{"date":"2026-01-10","close":109.0},{"date":"2026-01-11","close":110.0},{"date":"2026-01-12","close":111.0},{"date":"2026-01-13","close":112.0},{"date":"2026-01-14","close":113.0},{"date":"2026-01-15","close":114.0},{"date":"2026-01-16","close":115.0},{"date":"2026-01-17","close":116.0},{"date":"2026-01-18","close":117.0},{"date":"2026-01-19","close":118.0},{"date":"2026-01-20","close":119.0},{"date":"2026-01-21","close":120.0}]',
        encoding="utf-8",
    )
    (source_root / "series" / "etf_510002.json").write_text(
        '[{"date":"2026-01-01","close":100.0},{"date":"2026-01-02","close":100.2},{"date":"2026-01-03","close":100.4},{"date":"2026-01-04","close":100.6},{"date":"2026-01-05","close":100.8},{"date":"2026-01-06","close":101.0},{"date":"2026-01-07","close":101.2},{"date":"2026-01-08","close":101.4},{"date":"2026-01-09","close":101.6},{"date":"2026-01-10","close":101.8},{"date":"2026-01-11","close":102.0},{"date":"2026-01-12","close":102.2},{"date":"2026-01-13","close":102.4},{"date":"2026-01-14","close":102.6},{"date":"2026-01-15","close":102.8},{"date":"2026-01-16","close":103.0},{"date":"2026-01-17","close":103.2},{"date":"2026-01-18","close":103.4},{"date":"2026-01-19","close":103.6},{"date":"2026-01-20","close":103.8},{"date":"2026-01-21","close":104.0}]',
        encoding="utf-8",
    )

    monkeypatch.setattr(
        module,
        "collect_rotation_inputs",
        lambda config, output_root=None: [
            {
                "label": "A",
                "selected_primary": {"kind": "etf", "code": "510001", "name": "AETF"},
            },
            {
                "label": "B",
                "selected_primary": {"kind": "etf", "code": "510002", "name": "BETF"},
            },
        ],
    )

    result = module.run(
        config_path=config_path,
        output_root=root / "out",
        source_output_root=source_root,
    )

    assert [item["label"] for item in result["ranked_candidates"]] == ["A", "B"]
    assert round(result["ranked_candidates"][0]["return_20d"], 4) == 0.2000
    assert [item["label"] for item in result["portfolio_decision"]["selected_holdings"]] == [
        "A"
    ]
    assert result["portfolio_decision"]["selection_reason"] == "top_ranked_candidate"
    assert (root / "out" / "ranked_candidates.json").exists()
    assert (root / "out" / "portfolio_decision.json").exists()
    ranked_candidates_payload = json.loads(
        (root / "out" / "ranked_candidates.json").read_text(encoding="utf-8")
    )
    portfolio_decision_payload = json.loads(
        (root / "out" / "portfolio_decision.json").read_text(encoding="utf-8")
    )
    summary_text = (root / "out" / "summary.md").read_text(encoding="utf-8")

    assert [item["label"] for item in ranked_candidates_payload] == ["A", "B"]
    assert round(ranked_candidates_payload[0]["return_20d"], 4) == 0.2
    assert round(ranked_candidates_payload[1]["return_20d"], 4) == 0.04
    assert ranked_candidates_payload[0]["selected_primary"] == {
        "kind": "etf",
        "code": "510001",
        "name": "AETF",
    }
    assert ranked_candidates_payload[1]["selected_primary"] == {
        "kind": "etf",
        "code": "510002",
        "name": "BETF",
    }
    assert "latest_snapshot" not in ranked_candidates_payload[0]
    assert "latest_snapshot" not in ranked_candidates_payload[1]
    assert portfolio_decision_payload["selection_reason"] == "top_ranked_candidate"
    assert [item["label"] for item in portfolio_decision_payload["selected_holdings"]] == [
        "A"
    ]
    assert round(portfolio_decision_payload["selected_holdings"][0]["return_20d"], 4) == 0.2
    assert "# ETF Rotation Strategy" in summary_text
    assert "selected=A" in summary_text
    assert "selection_reason=top_ranked_candidate" in summary_text
    assert "- A: return_20d=0.2000" in summary_text


def test_run_rotation_strategy_rejects_missing_configured_target_snapshots(
    monkeypatch,
):
    root = _make_workspace_tmp("rejects_missing_configured_target_snapshots")
    config_path = root / "rotation.yaml"
    config_path.write_text(
        """
targets:
  - label: A
    search_keywords: [A]
  - label: B
    search_keywords: [B]
defensive_targets: []
strategy:
  lookback_days: 20
  holdings_num: 1
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        module,
        "collect_rotation_inputs",
        lambda config, output_root=None: [
            {
                "label": "A",
                "selected_primary": {"kind": "etf", "code": "510001", "name": "AETF"},
            }
        ],
    )

    with pytest.raises(ValueError, match="B"):
        module.run(
            config_path=config_path,
            output_root=root / "out",
            source_output_root=root / "source",
        )


def test_build_summary_includes_v1_rankings_and_selection_reason():
    summary = module.build_summary(
        ranked_candidates=[
            {"label": "A", "return_20d": 0.2},
            {"label": "B", "return_20d": 0.04},
        ],
        portfolio_decision={
            "selected_holdings": [{"label": "A", "return_20d": 0.2}],
            "selection_reason": "top_ranked_candidate",
            "rejected_candidates": [{"label": "B", "return_20d": 0.04}],
        },
    )

    assert "# ETF Rotation Strategy" in summary
    assert "selected=A" in summary
    assert "selection_reason=top_ranked_candidate" in summary
    assert "return_20d=0.2000" in summary
