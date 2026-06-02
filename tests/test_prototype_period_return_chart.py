from pathlib import Path
from unittest.mock import Mock

import prototype_period_return_chart as module


def test_build_one_month_chart_series_sorts_by_last_return():
    table_rows = [
        {"name": "A", "code": "001", "return_1m": "-2.52%"},
        {"name": "B", "code": "002", "return_1m": "11.18%"},
    ]
    curve_payloads = {
        "001": [{"date": "2026-04-29", "return_pct": 0.0}, {"date": "2026-05-29", "return_pct": -2.52}],
        "002": [{"date": "2026-04-28", "return_pct": 0.0}, {"date": "2026-05-28", "return_pct": 11.18}],
    }

    series = module.build_one_month_chart_series(table_rows, curve_payloads)

    assert [item["code"] for item in series] == ["001", "002"]
    assert series[0]["last_return_pct"] == -2.52
    assert series[1]["last_return_pct"] == 11.18


def test_build_one_month_chart_series_prefers_target_key_when_present():
    table_rows = [
        {"target_key": "etf_com_cn:001", "name": "A", "code": "001", "return_1m": "-2.52%"},
        {"target_key": "jisilu_cb_index:001", "name": "B", "code": "001", "return_1m": "1.18%"},
    ]
    curve_payloads = {
        "etf_com_cn:001": [{"date": "2026-04-29", "return_pct": 0.0}, {"date": "2026-05-29", "return_pct": -2.52}],
        "jisilu_cb_index:001": [{"date": "2026-04-29", "return_pct": 0.0}, {"date": "2026-05-29", "return_pct": 1.18}],
    }

    series = module.build_one_month_chart_series(table_rows, curve_payloads)

    assert [(item["name"], item["last_return_pct"]) for item in series] == [("A", -2.52), ("B", 1.18)]


def test_build_one_month_chart_series_uses_distinct_palette_for_first_seven_series():
    table_rows = [
        {"name": f"标的{i}", "code": f"{i:03d}", "return_1m": f"{i}.00%"}
        for i in range(7)
    ]
    curve_payloads = {
        f"{i:03d}": [{"date": "2026-04-29", "return_pct": 0.0}, {"date": "2026-05-29", "return_pct": float(i)}]
        for i in range(7)
    }

    series = module.build_one_month_chart_series(table_rows, curve_payloads)

    colors = [item["color"] for item in series]
    assert len(set(colors)) == 7
    assert "#1558D6" not in colors
    assert "#6BA6FF" not in colors


def test_compute_label_positions_separates_close_values():
    values = [-2.52, -2.4, -2.35, 0.51, 0.6]

    positions = module.compute_label_positions(values, min_gap=0.3)

    assert len(positions) == len(values)
    sorted_positions = sorted(positions)
    for left, right in zip(sorted_positions, sorted_positions[1:]):
        assert round(right - left, 6) >= 0.3


def test_build_tail_label_text_includes_name_and_return():
    item = {
        "name": "黄金ETF易方达",
        "display_return": "-2.52%",
    }

    label = module.build_tail_label_text(item)

    assert label == "黄金ETF易方达 -2.52%"


def test_configure_matplotlib_fonts_accepts_noto_cjk_jp(monkeypatch):
    fake_font = Mock()
    fake_font.name = "Noto Sans CJK JP"
    monkeypatch.setattr(module.font_manager.fontManager, "ttflist", [fake_font])

    module.configure_matplotlib_fonts()

    assert "Noto Sans CJK JP" in module.plt.rcParams["font.sans-serif"]


def test_generate_one_month_return_chart_creates_png(tmp_path: Path):
    table_rows = [
        {"name": "黄金ETF易方达", "code": "159934", "return_1m": "-2.52%"},
        {"name": "纳指ETF广发", "code": "159941", "return_1m": "11.18%"},
    ]
    curve_payloads = {
        "159934": [
            {"date": "2026-04-29", "return_pct": 0.0},
            {"date": "2026-04-30", "return_pct": 0.37},
            {"date": "2026-05-29", "return_pct": -2.52},
        ],
        "159941": [
            {"date": "2026-04-28", "return_pct": 0.0},
            {"date": "2026-04-30", "return_pct": 4.9},
            {"date": "2026-05-28", "return_pct": 11.18},
        ],
    }

    output_path = module.generate_one_month_return_chart(
        table_rows,
        curve_payloads,
        output_dir=tmp_path,
    )

    assert output_path.exists()
    assert output_path.suffix == ".png"
    assert output_path.stat().st_size > 0
