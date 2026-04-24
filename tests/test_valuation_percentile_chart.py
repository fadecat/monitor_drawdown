from pathlib import Path

from matplotlib.colors import to_hex
import pandas as pd

import prototype_valuation_percentile_chart as chart


def _fake_pe_history() -> pd.DataFrame:
    dates = pd.date_range("2024-01-07", periods=30, freq="W")
    values = [10.0 + idx * 0.2 for idx in range(len(dates))]
    return pd.DataFrame({"date": dates, "pe": values})


def _make_target() -> dict:
    return {
        "name": "测试指数",
        "code": "000300",
        "index_code": "000300",
        "index_name": "测试指数",
        "index_valuation_date": "2026-04-23",
    }


def _make_figure(monkeypatch):
    monkeypatch.setattr(chart.md, "fetch_index_pe_history", lambda index_code, url="": _fake_pe_history())
    target = _make_target()
    data = chart._prepare_chart_data(target)
    assert data is not None
    fig = chart._build_figure(target, data)
    return fig, data


def test_generate_valuation_percentile_chart_outputs_png(
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
    chart_ax = fig.axes[0]

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


def test_build_figure_renders_quantile_labels(monkeypatch):
    fig, data = _make_figure(monkeypatch)
    chart_ax = fig.axes[0]
    texts = {text.get_text() for text in chart_ax.texts}

    assert f"30分位值{data['q30']:.2f}" in texts
    assert f"中位值{data['q50']:.2f}" in texts
    assert f"70分位值{data['q70']:.2f}" in texts
    assert "PE走势" in texts


def test_build_figure_omits_pe_and_pb_percentile_header(monkeypatch):
    fig, _ = _make_figure(monkeypatch)
    texts = {text.get_text() for ax in fig.axes for text in ax.texts}

    assert "PE百分位" not in texts
    assert "PB百分位" not in texts
    assert "PB" not in texts
    assert "股息率" not in texts
    assert "比过去" not in texts
