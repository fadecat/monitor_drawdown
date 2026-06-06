import json
import shutil
from pathlib import Path

import run_etf_rotation_v3_strategy as module


def _make_workspace_tmp(name: str) -> Path:
    root = Path("tests") / ".tmp" / name
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    return root


def test_run_rotation_v3_strategy_keeps_single_positive_score_asset_out_of_defensive_fallback(
    monkeypatch,
):
    root = _make_workspace_tmp("run_rotation_v3_single_positive_score_asset")
    config_path = root / "rotation_v3.yaml"
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
  short_confirmation_tolerance: 0.0
  holdings_num: 1
""".strip(),
        encoding="utf-8",
    )
    source_root = root / "source"
    (source_root / "series").mkdir(parents=True, exist_ok=True)
    (source_root / "series" / "etf_510001.json").write_text(
        json.dumps(
            [
                {"date": f"2026-03-{index + 1:02d}", "close": close}
                for index, close in enumerate(
                    [
                        100.0,
                        102.0,
                        104.0,
                        106.0,
                        108.0,
                        110.0,
                        112.0,
                        114.0,
                        116.0,
                        118.0,
                        120.0,
                        122.0,
                        124.0,
                        126.0,
                        128.0,
                        130.0,
                        129.0,
                        128.0,
                        127.0,
                        126.0,
                        125.0,
                        124.0,
                        123.0,
                        122.0,
                        121.0,
                    ]
                )
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (source_root / "series" / "etf_510002.json").write_text(
        json.dumps(
            [
                {"date": f"2026-03-{index + 1:02d}", "close": 100.0 - index}
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

    assert len(result["candidate_metrics"]) == 2
    assert [item["label"] for item in result["ranked_candidates"]] == ["A"]
    assert result["portfolio_decision"]["selection_reason"] == "top_ranked_risk_asset"
    assert [item["label"] for item in result["portfolio_decision"]["selected_holdings"]] == ["A"]
    assert result["candidate_metrics"][0]["short_confirmation_threshold"] == result["candidate_metrics"][0]["return_10d"]
