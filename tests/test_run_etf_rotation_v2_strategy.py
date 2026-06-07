import json
import shutil
from pathlib import Path

import run_etf_rotation_v2_strategy as module


def _make_workspace_tmp(name: str) -> Path:
    root = Path("tests") / ".tmp" / name
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    return root


def test_load_rotation_v2_config_reads_separate_risk_and_defensive_targets():
    config = module.load_rotation_config(Path("etf_rotation_v2_config.yaml"))

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
        },
    }


def test_collect_rotation_inputs_prefers_configured_code_and_kind_without_search(
    monkeypatch,
):
    resolved = []

    def _unexpected_resolve(target):
        resolved.append(target)
        raise AssertionError("resolve_target should not be called")

    monkeypatch.setattr(module.data_sources, "resolve_target", _unexpected_resolve)

    result = module.collect_rotation_inputs(
        {
            "risk_targets": [
                {
                    "label": "A",
                    "search_keywords": ["A"],
                    "code": "510001",
                    "kind": "etf",
                }
            ],
            "defensive_targets": [
                {
                    "label": "CASH",
                    "search_keywords": ["CASH"],
                    "code": "511880",
                    "kind": "etf",
                }
            ],
        }
    )

    assert resolved == []
    assert result == [
        {
            "label": "A",
            "status": "ok",
            "selected_primary": {
                "kind": "etf",
                "code": "510001",
                "name": "A",
                "reason": "config_primary",
            },
        },
        {
            "label": "CASH",
            "status": "ok",
            "selected_primary": {
                "kind": "etf",
                "code": "511880",
                "name": "CASH",
                "reason": "config_primary",
            },
        },
    ]


def test_run_rotation_v2_strategy_writes_candidate_metrics_rankings_and_decision(
    monkeypatch,
):
    root = _make_workspace_tmp("writes_rotation_v2_outputs")
    config_path = root / "rotation_v2.yaml"
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
""".strip(),
        encoding="utf-8",
    )
    source_root = root / "source"
    (source_root / "series").mkdir(parents=True, exist_ok=True)
    (source_root / "series" / "etf_510001.json").write_text(
        json.dumps(
            [
                {"date": f"2026-03-{index + 1:02d}", "close": 100.0 * (1.012 ** index)}
                for index in range(25)
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (source_root / "series" / "etf_510002.json").write_text(
        json.dumps(
            [
                {"date": f"2026-03-{index + 1:02d}", "close": 100.0 * (1.006 ** index)}
                for index in range(25)
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (source_root / "series" / "etf_511880.json").write_text(
        json.dumps(
            [
                {"date": f"2026-03-{index + 1:02d}", "close": 100.0 + index * 0.01}
                for index in range(25)
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
    assert "# ETF Rotation Strategy V2" in summary_text
    assert "risk_candidates=2" in summary_text
    assert "selection_reason=top_ranked_risk_asset" in summary_text


def test_run_rotation_v2_uses_common_signal_date_when_target_dates_are_not_aligned(
    monkeypatch,
):
    root = _make_workspace_tmp("uses_common_signal_date")
    config_path = root / "rotation_v2.yaml"
    config_path.write_text(
        """
risk_targets:
  - label: A
    search_keywords: [A]
    code: '510001'
    kind: etf
  - label: B
    search_keywords: [B]
    code: '510002'
    kind: etf
defensive_targets:
  - label: CASH
    search_keywords: [CASH]
    code: '511880'
    kind: etf
strategy:
  lookback_days: 25
  short_lookback_days: 10
  annualization_days: 250
  weight_start: 1.0
  weight_end: 2.0
  holdings_num: 1
""".strip(),
        encoding="utf-8",
    )
    source_root = root / "source"
    (source_root / "series").mkdir(parents=True, exist_ok=True)

    def write_series(code: str, length: int, growth: float):
        (source_root / "series" / f"etf_{code}.json").write_text(
            json.dumps(
                [
                    {
                        "date": f"2026-03-{index + 1:02d}",
                        "close": 100.0 * (growth**index),
                    }
                    for index in range(length)
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    write_series("510001", 26, 1.012)
    write_series("510002", 25, 1.006)
    write_series("511880", 26, 1.0001)

    result = module.run(
        config_path=config_path,
        output_root=root / "out",
        source_output_root=source_root,
    )

    assert result["data_status"]["signal_date"] == "2026-03-25"
    assert result["data_status"]["all_targets_aligned"] is False
    assert result["data_status"]["status"] == "ready"
    assert result["data_status"]["latest_dates_by_label"] == {
        "A": "2026-03-26",
        "B": "2026-03-25",
        "CASH": "2026-03-26",
    }
    assert result["data_status"]["lagging_labels"] == ["B"]
    assert all(item["data_date"] == "2026-03-25" for item in result["candidate_metrics"])
    data_status_payload = json.loads((root / "out" / "data_status.json").read_text(encoding="utf-8"))
    assert data_status_payload == result["data_status"]
