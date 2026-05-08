from pathlib import Path

import pandas as pd

import prototype_fx_chart as chart


def _fake_hist_df() -> pd.DataFrame:
    dates = pd.date_range("2015-01-02", periods=40, freq="QS")
    values = [6.05 + idx * 0.021 for idx in range(len(dates))]
    return pd.DataFrame({"日期": dates, "代码": ["USDCNH"] * len(dates), "名称": ["美元兑离岸人民币"] * len(dates), "最新价": values})


def test_prepare_chart_data_returns_single_hist_series(monkeypatch):
    monkeypatch.setattr(chart.ak, "forex_hist_em", lambda symbol="USDCNH": _fake_hist_df())

    data = chart._prepare_chart_data(days=3650, hist_symbol="USDCNH")

    assert data is not None
    assert not data["hist_df"].empty
    assert data["hist_symbol"] == "USDCNH"
    assert round(data["latest_hist"], 4) == round(float(data["hist_df"].iloc[-1]["市场价"]), 4)


def test_build_figure_contains_chart_and_footer_axes(monkeypatch):
    monkeypatch.setattr(chart.ak, "forex_hist_em", lambda symbol="USDCNH": _fake_hist_df())
    data = chart._prepare_chart_data(days=3650, hist_symbol="USDCNH")
    assert data is not None

    fig = chart._build_figure(data)

    assert len(fig.axes) == 2
    chart_ax = fig.axes[0]
    texts = {text.get_text() for text in chart_ax.texts}
    assert f"{data['hist_symbol']} 市场价走势" in texts
    assert f"{data['latest_hist']:.4f}" in texts


def test_generate_fx_chart_outputs_png(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(chart.ak, "forex_hist_em", lambda symbol="USDCNH": _fake_hist_df())

    output = chart.generate_fx_chart(tmp_path, days=3650, hist_symbol="USDCNH")

    assert output is not None
    assert output.exists()
    assert output.stat().st_size > 5 * 1024
