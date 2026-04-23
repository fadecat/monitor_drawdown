from pathlib import Path

from matplotlib.colors import to_hex
import pandas as pd

import prototype_valuation_percentile_chart as chart


def _fake_pe_history() -> pd.DataFrame:
    dates = pd.date_range("2024-01-07", periods=30, freq="W")
    values = [10.0 + idx * 0.2 for idx in range(len(dates))]
    return pd.DataFrame({"date": dates, "pe": values})


def _make_target(pct_5y: float = 18.5) -> dict:
    return {
        "name": "测试指数",
        "code": "000300",
        "index_code": "000300",
        "index_name": "测试指数",
        "index_valuation_date": "2026-04-23",
        "index_valuation_metrics": {
            "PE(TTM)": {"current": 15.8, "percentiles": {"5Y": pct_5y}},
        },
    }


def _make_figure(monkeypatch, pct_5y: float = 18.5):
    monkeypatch.setattr(chart.md, "fetch_index_pe_history", lambda index_code, url="": _fake_pe_history())
    target = _make_target(pct_5y=pct_5y)
    data = chart._prepare_chart_data(target)
    assert data is not None
    fig = chart._build_figure(target, data)
    return fig, data


def test_generate_valuation_percentile_chart_outputs_png_with_missing_pb_and_dividend(
    monkeypatch,
    tmp_path: Path,
):
    monkeypatch.setattr(chart.md, "fetch_index_pe_history", lambda index_code, url="": _fake_pe_history())
    output = chart.generate_valuation_percentile_chart(_make_target(), tmp_path)

    assert output is not None
    assert output.exists()
    assert output.stat().st_size > 5 * 1024


def test_build_figure_contains_three_percentile_axhlines(monkeypatch):
    fig, _ = _make_figure(monkeypatch)
    chart_ax = fig.axes[2]

    horizontal_lines = []
    for line in chart_ax.lines:
        xdata = list(line.get_xdata())
        if len(xdata) == 2 and xdata == [0, 1]:
            horizontal_lines.append(line)

    assert len(horizontal_lines) == 3
    assert {to_hex(line.get_color()).lower() for line in horizontal_lines} == {
        chart.PALETTE["pct_low"],
        chart.PALETTE["pct_mid"],
        chart.PALETTE["pct_high"],
    }


def test_build_figure_contains_allowed_level_text(monkeypatch):
    fig, data = _make_figure(monkeypatch, pct_5y=70.0)
    texts = {text.get_text() for ax in fig.axes for text in ax.texts}

    assert data["level_text"] in {"估值极低", "估值偏低", "估值合理", "估值偏高", "估值极高"}
    assert data["level_text"] in texts


def test_classify_level_by_percentile_returns_spec_colors():
    assert chart.classify_level_by_percentile(10) == ("估值极低", chart.PALETTE["level_low"])
    assert chart.classify_level_by_percentile(30) == ("估值偏低", chart.PALETTE["level_belowmid"])
    assert chart.classify_level_by_percentile(50) == ("估值合理", chart.PALETTE["level_mid"])
    assert chart.classify_level_by_percentile(70) == ("估值偏高", chart.PALETTE["level_abovemid"])
    assert chart.classify_level_by_percentile(90) == ("估值极高", chart.PALETTE["level_high"])


def test_build_figure_places_header_texts_at_spec_positions(monkeypatch):
    fig, _ = _make_figure(monkeypatch, pct_5y=91.24)
    header_ax = fig.axes[0]
    by_text = {text.get_text(): text for text in header_ax.texts}
    latest_mmdd = pd.Timestamp(_fake_pe_history()["date"].iloc[-1]).strftime("%m-%d")

    assert "测试指数" not in by_text
    assert by_text["比过去"].get_position() == (0.00, 0.55)
    assert by_text["估值极高"].get_position() == (0.00, 0.18)
    assert by_text["估值极高"].get_fontsize() <= 26
    assert by_text[f"PE {latest_mmdd}"].get_position() == (0.35, 0.72)
    assert by_text["PE百分位"].get_position() == (0.60, 0.72)
    assert "91.24%" in by_text
