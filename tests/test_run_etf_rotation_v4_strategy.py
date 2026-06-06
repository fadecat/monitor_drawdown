import json
import math
import shutil
from pathlib import Path

import run_etf_rotation_v4_strategy as module


def _make_workspace_tmp(name: str) -> Path:
    root = Path("tests") / ".tmp" / name
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    return root


def test_load_rotation_v4_config_reads_separate_risk_and_defensive_targets():
    config = module.load_rotation_config(Path("etf_rotation_v4_config.yaml"))

    assert config == {
        "risk_targets": [
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
        ],
        "defensive_targets": [
            {
                "category": "防守",
                "label": "银华日利ETF",
                "search_keywords": ["银华日利ETF"],
                "code": "511880",
                "kind": "etf",
            }
        ],
        "strategy": {
            "lookback_days": 25,
            "short_lookback_days": 10,
            "annualization_days": 250,
            "weight_start": 1.0,
            "weight_end": 2.0,
            "holdings_num": 1,
            "short_confirmation_variant": "v4_a",
            "short_confirmation_history_days": 252,
            "short_confirmation_percentile_threshold": 0.4,
            "short_confirmation_absolute_floor": -0.02,
            "volatility_lookback_days": 20,
        },
    }


def test_run_rotation_v4_strategy_writes_candidate_metrics_rankings_and_decision(monkeypatch):
    root = _make_workspace_tmp("writes_rotation_v4_outputs")
    config_path = root / "rotation_v4.yaml"
    config_path.write_text(
        """
risk_targets:
  - label: A
    search_keywords: [A]
  - label: B
    search_keywords: [B]
defensive_targets:
  - label: CASH
    search_keywords: [CASH]
strategy:
  lookback_days: 25
  short_lookback_days: 10
  annualization_days: 250
  weight_start: 1.0
  weight_end: 2.0
  holdings_num: 1
  short_confirmation_variant: v4_a
  short_confirmation_history_days: 252
  short_confirmation_percentile_threshold: 0.4
  short_confirmation_absolute_floor: -0.02
  volatility_lookback_days: 20
""".strip(),
        encoding="utf-8",
    )
    source_root = root / "source"
    (source_root / "series").mkdir(parents=True, exist_ok=True)
    (source_root / "series" / "etf_510001.json").write_text(
        json.dumps(
            [
                {
                    "date": f"2026-03-{index + 1:02d}",
                    "close": 100.0 + 0.35 * index + 0.4 * math.sin(index / 7.0),
                }
                for index in range(273)
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (source_root / "series" / "etf_510002.json").write_text(
        json.dumps(
            [
                {
                    "date": f"2026-03-{index + 1:02d}",
                    "close": 100.0 + 0.32 * index + 0.4 * math.sin(index / 7.0),
                }
                for index in range(273)
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (source_root / "series" / "etf_511880.json").write_text(
        json.dumps(
            [
                {"date": f"2026-03-{index + 1:02d}", "close": 100.0 + index * 0.01}
                for index in range(273)
            ],
            ensure_ascii=False,
        ),
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
            {
                "label": "CASH",
                "selected_primary": {"kind": "etf", "code": "511880", "name": "CASHEFT"},
            },
        ],
    )

    result = module.run(
        config_path=config_path,
        output_root=root / "out",
        source_output_root=source_root,
    )

    assert [item["label"] for item in result["candidate_metrics"]] == ["A", "B"]
    assert all(item["qualified"] is True for item in result["candidate_metrics"])
    assert [item["label"] for item in result["ranked_candidates"]] == ["A", "B"]
    assert result["portfolio_decision"]["selection_reason"] == "top_ranked_risk_asset"
    assert [item["label"] for item in result["portfolio_decision"]["selected_holdings"]] == ["A"]

    candidate_metrics_payload = json.loads(
        (root / "out" / "candidate_metrics.json").read_text(encoding="utf-8")
    )
    ranked_candidates_payload = json.loads(
        (root / "out" / "ranked_candidates.json").read_text(encoding="utf-8")
    )
    portfolio_decision_payload = json.loads(
        (root / "out" / "portfolio_decision.json").read_text(encoding="utf-8")
    )
    summary_text = (root / "out" / "summary.md").read_text(encoding="utf-8")

    assert [item["label"] for item in candidate_metrics_payload] == ["A", "B"]
    assert [item["label"] for item in ranked_candidates_payload] == ["A", "B"]
    assert candidate_metrics_payload[0]["score_25"] > candidate_metrics_payload[1]["score_25"]
    assert portfolio_decision_payload["selection_reason"] == "top_ranked_risk_asset"
    assert [item["label"] for item in portfolio_decision_payload["selected_holdings"]] == ["A"]
    assert "# ETF Rotation Strategy V4" in summary_text
    assert "risk_candidates=2" in summary_text
    assert "selection_reason=top_ranked_risk_asset" in summary_text
