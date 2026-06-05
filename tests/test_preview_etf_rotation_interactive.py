import csv
import json
import shutil
from pathlib import Path

import preview_etf_rotation_interactive as module


def _make_workspace_tmp(name: str) -> Path:
    root = Path(".test_artifacts/test_preview_etf_rotation_interactive") / name
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    return root


def test_build_aligned_normalized_series_forward_fills_latest_close():
    values = module.build_aligned_normalized_series(
        plot_dates=["2026-02-01", "2026-02-02", "2026-02-03"],
        series_records=[
            {"date": "2026-01-31", "close": 100.0},
            {"date": "2026-02-03", "close": 110.0},
        ],
        start_date="2026-02-01",
    )

    assert values == [1.0, 1.0, 1.1]


def test_load_interactive_rotation_payload_reads_backtest_and_assets():
    root = _make_workspace_tmp("load_interactive_rotation_payload")
    config_path = root / "rotation.yaml"
    config_path.write_text(
        """
targets:
  - category: 权益
    label: A
    search_keywords: [A]
    code: "510001"
    kind: etf
  - category: 防守
    label: 银华日利ETF
    search_keywords: [银华日利ETF]
    code: "511880"
    kind: etf
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
        json.dumps(
            [
                {"date": "2026-01-31", "close": 100.0},
                {"date": "2026-02-02", "close": 105.0},
                {"date": "2026-02-03", "close": 110.0},
            ]
        ),
        encoding="utf-8",
    )
    (source_root / "series" / "etf_511880.json").write_text(
        json.dumps(
            [
                {"date": "2026-01-31", "close": 100.0},
                {"date": "2026-02-03", "close": 100.1},
            ]
        ),
        encoding="utf-8",
    )

    backtest_root = root / "backtest"
    backtest_root.mkdir(parents=True, exist_ok=True)
    with (backtest_root / "daily_positions.csv").open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["date", "signal_date", "strategy_nav", "daily_return"],
        )
        writer.writeheader()
        writer.writerows(
            [
                {
                    "date": "2026-02-02",
                    "signal_date": "2026-02-01",
                    "strategy_nav": 1.02,
                    "daily_return": 0.02,
                },
                {
                    "date": "2026-02-03",
                    "signal_date": "2026-02-02",
                    "strategy_nav": 1.03,
                    "daily_return": 0.00980392156862745,
                },
            ]
        )
    with (backtest_root / "trades.csv").open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "signal_date",
                "from_symbol",
                "from_name",
                "to_symbol",
                "to_name",
                "reason",
                "from_20d_return",
                "to_20d_return",
                "rank_1_symbol",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "signal_date": "2026-02-02",
                "from_symbol": "511880",
                "from_name": "银华日利ETF",
                "to_symbol": "510001",
                "to_name": "A",
                "reason": "top_rank_changed",
                "from_20d_return": 0.001,
                "to_20d_return": 0.05,
                "rank_1_symbol": "510001",
            }
        )
    with (backtest_root / "holding_periods.csv").open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "start_date",
                "end_date",
                "symbol",
                "name",
                "holding_days",
                "period_return",
                "contribution_to_total_return",
                "max_drawdown_during_holding",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "start_date": "2026-02-02",
                "end_date": "2026-02-03",
                "symbol": "510001",
                "name": "A",
                "holding_days": 2,
                "period_return": 0.03,
                "contribution_to_total_return": 0.03,
                "max_drawdown_during_holding": -0.01,
            }
        )

    payload = module.load_interactive_rotation_payload(
        config_path=config_path,
        source_output_root=source_root,
        backtest_output_root=backtest_root,
    )

    assert payload["meta"]["start_date"] == "2026-02-02"
    assert payload["meta"]["end_date"] == "2026-02-03"
    assert payload["dates"] == ["2026-02-02", "2026-02-03"]
    assert [item["name"] for item in payload["series"][:2]] == ["策略净值", "静止线"]
    assert payload["series"][2]["name"] == "A"
    assert payload["series"][2]["values"] == [1.0, 1.047619047619]
    assert payload["series"][3]["name"] == "银华日利ETF"
    assert payload["series"][3]["values"] == [1.0, 1.001]
    assert payload["trades"][0]["reason"] == "top_rank_changed"
    assert payload["holding_periods"][0]["symbol"] == "510001"


def test_render_interactive_rotation_html_includes_controls_and_series():
    html = module.render_interactive_rotation_html(
        {
            "meta": {
                "title": "ETF轮动策略交互预览",
                "start_date": "2026-02-02",
                "end_date": "2026-02-03",
                "notes": ["note-a", "note-b"],
            },
            "dates": ["2026-02-02", "2026-02-03"],
            "series": [
                {"id": "strategy_nav", "name": "策略净值", "values": [1.0, 1.1], "color": "#111111"},
                {"id": "baseline", "name": "静止线", "values": [1.0, 1.0], "color": "#999999"},
            ],
            "trades": [
                {
                    "signal_date": "2026-02-02",
                    "from_symbol": "511880",
                    "to_symbol": "510001",
                    "reason": "top_rank_changed",
                }
            ],
            "holding_periods": [
                {
                    "start_date": "2026-02-02",
                    "end_date": "2026-02-03",
                    "symbol": "510001",
                    "name": "A",
                    "holding_days": 2,
                    "period_return": 0.03,
                    "contribution_to_total_return": 0.03,
                }
            ],
        }
    )

    assert "ETF轮动策略交互预览" in html
    assert "window-start" in html
    assert "window-end" in html
    assert "drag to pan" in html
    assert "holding-band" in html
    assert "phase-layer" in html
    assert "phase-label" in html
    assert "state.focusSymbol" in html
    assert "legend-item.focused" in html
    assert "series-item dimmed" in html
    assert "阶段收益标签展示完整持仓段收益" in html
    assert "策略净值" in html
    assert "静止线" in html
    assert "top_rank_changed" in html
    assert "const payload =" in html


def test_write_interactive_rotation_preview_writes_html_file():
    root = _make_workspace_tmp("write_interactive_rotation_preview")
    output_path = module.write_interactive_rotation_preview(
        payload={
            "meta": {
                "title": "ETF轮动策略交互预览",
                "start_date": "2026-02-02",
                "end_date": "2026-02-03",
                "notes": [],
            },
            "dates": ["2026-02-02", "2026-02-03"],
            "series": [
                {"id": "strategy_nav", "name": "策略净值", "values": [1.0, 1.1], "color": "#111111"},
            ],
            "trades": [],
            "holding_periods": [],
        },
        output_path=root / "interactive.html",
    )

    assert output_path.exists()
    html = output_path.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in html
    assert "ETF轮动策略交互预览" in html
