import pandas as pd
import pytest
from unittest.mock import Mock

import style_rotation_preview as srp
import prototype_style_rotation_chart as style_chart
from style_rotation_preview import calculate_style_rotation_preview
from style_rotation_preview import build_style_rotation_preview_payload
from style_rotation_preview import collect_style_rotation_preview_payload
from style_rotation_preview import normalize_price_frame


def test_calculate_style_rotation_preview_uses_rolling_return_spread():
    left = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]),
            "close": [100.0, 110.0, 121.0],
        }
    )
    right = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]),
            "close": [100.0, 105.0, 110.25],
        }
    )

    result = calculate_style_rotation_preview(
        left_df=left,
        right_df=right,
        return_window_days=1,
        display_window_days=10,
    )

    assert result["dates"] == ["2024-01-02", "2024-01-03"]
    assert result["left_return"] == [10.0, 10.0]
    assert result["right_return"] == [5.0, 5.0]
    assert result["spread"] == [5.0, 5.0]


def test_calculate_style_rotation_preview_rejects_non_positive_return_window_days():
    left = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-01", "2024-01-02"]),
            "close": [100.0, 110.0],
        }
    )
    right = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-01", "2024-01-02"]),
            "close": [100.0, 105.0],
        }
    )

    with pytest.raises(ValueError, match="return_window_days must be greater than 0"):
        calculate_style_rotation_preview(
            left_df=left,
            right_df=right,
            return_window_days=0,
            display_window_days=10,
        )


def test_normalize_price_frame_deduplicates_dates_keep_last():
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-01", "2024-01-01", "2024-01-02"]),
            "close": [99.0, 100.0, 110.0],
        }
    )

    normalized = normalize_price_frame(frame)

    assert normalized["date"].dt.strftime("%Y-%m-%d").tolist() == ["2024-01-01", "2024-01-02"]
    assert normalized["close"].tolist() == [100.0, 110.0]


def test_calculate_style_rotation_preview_deduplicates_input_dates_before_alignment():
    left = pd.DataFrame(
        {
            "date": pd.to_datetime(
                ["2024-01-01", "2024-01-01", "2024-01-02", "2024-01-03"]
            ),
            "close": [99.0, 100.0, 110.0, 121.0],
        }
    )
    right = pd.DataFrame(
        {
            "date": pd.to_datetime(
                ["2024-01-01", "2024-01-01", "2024-01-02", "2024-01-03"]
            ),
            "close": [98.0, 100.0, 105.0, 110.25],
        }
    )

    result = calculate_style_rotation_preview(
        left_df=left,
        right_df=right,
        return_window_days=1,
        display_window_days=10,
    )

    assert result["dates"] == ["2024-01-02", "2024-01-03"]
    assert result["spread"] == [5.0, 5.0]


def test_calculate_style_rotation_preview_raises_value_error_when_samples_are_insufficient_for_window():
    left = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-01", "2024-01-02"]),
            "close": [100.0, 110.0],
        }
    )
    right = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-01", "2024-01-02"]),
            "close": [100.0, 105.0],
        }
    )

    with pytest.raises(ValueError, match="有效收益率差值为空"):
        calculate_style_rotation_preview(
            left_df=left,
            right_df=right,
            return_window_days=2,
            display_window_days=10,
        )


def test_calculate_style_rotation_preview_raises_value_error_when_aligned_data_is_empty():
    left = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-01"]),
            "close": [100.0],
        }
    )
    right = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02"]),
            "close": [100.0],
        }
    )

    with pytest.raises(ValueError, match="对齐后的价格数据为空"):
        calculate_style_rotation_preview(
            left_df=left,
            right_df=right,
            return_window_days=1,
            display_window_days=10,
        )


def test_build_style_rotation_preview_payload_limits_display_window():
    dates = pd.date_range("2024-01-01", periods=6, freq="D")
    left = pd.DataFrame({"date": dates, "close": [100, 101, 102, 103, 104, 105]})
    right = pd.DataFrame({"date": dates, "close": [100, 100, 100, 100, 100, 100]})

    payload = build_style_rotation_preview_payload(
        left_df=left,
        right_df=right,
        return_window_days=1,
        display_window_days=3,
    )

    assert payload["meta"]["left_symbol"] == srp.FIXED_LEFT_SYMBOL
    assert payload["meta"]["right_symbol"] == srp.FIXED_RIGHT_SYMBOL
    assert payload["series"]["dates"] == ["2024-01-04", "2024-01-05", "2024-01-06"]


def test_collect_style_rotation_preview_payload_uses_fixed_symbols(monkeypatch):
    calls = []

    def fake_fetch_index_history(symbol: str) -> pd.DataFrame:
        calls.append(symbol)
        return pd.DataFrame(
            {
                "date": pd.to_datetime(["2024-01-01", "2024-01-02"]),
                "close": [100.0, 110.0],
            }
        )

    monkeypatch.setattr(srp, "fetch_index_history", fake_fetch_index_history)

    payload = collect_style_rotation_preview_payload(return_window_days=1, display_window_days=1)

    assert calls == [srp.FIXED_LEFT_SYMBOL, srp.FIXED_RIGHT_SYMBOL]
    assert payload["meta"] == {
        "left_symbol": srp.FIXED_LEFT_SYMBOL,
        "left_name": srp.FIXED_LEFT_NAME,
        "right_symbol": srp.FIXED_RIGHT_SYMBOL,
        "right_name": srp.FIXED_RIGHT_NAME,
        "return_window_days": 1,
        "display_window_days": 1,
    }
    assert set(payload["series"].keys()) == {"dates", "left_return", "right_return", "spread"}


def test_fetch_etf_history_uses_etf_com_nav_rows(monkeypatch):
    monkeypatch.setattr(
        srp.etf_analysis,
        "load_nav_rows",
        lambda symbol: [
            {"trdDt": "2026-03-20", "adjUnitNav": "1.0234"},
            {"trdDt": "2026-03-21", "adjUnitNav": "1.0456"},
            {"trdDt": "2026-03-21", "adjUnitNav": "1.0500"},
        ],
    )

    result = srp.fetch_etf_history("159263")

    assert result["date"].dt.strftime("%Y-%m-%d").tolist() == ["2026-03-20", "2026-03-21"]
    assert result["close"].tolist() == [1.0234, 1.05]


def test_collect_etf_style_rotation_preview_payload_uses_fixed_symbols(monkeypatch):
    calls = []

    def fake_fetch_etf_history(symbol: str) -> pd.DataFrame:
        calls.append(symbol)
        return pd.DataFrame(
            {
                "date": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"]),
                "close": [1.0, 1.1, 1.2],
            }
        )

    monkeypatch.setattr(srp, "fetch_etf_history", fake_fetch_etf_history)

    payload = srp.collect_etf_style_rotation_preview_payload(return_window_days=1, display_window_days=2)

    assert calls == [srp.FIXED_ETF_LEFT_SYMBOL, srp.FIXED_ETF_RIGHT_SYMBOL]
    assert payload["meta"] == {
        "left_symbol": srp.FIXED_ETF_LEFT_SYMBOL,
        "left_name": srp.FIXED_ETF_LEFT_NAME,
        "right_symbol": srp.FIXED_ETF_RIGHT_SYMBOL,
        "right_name": srp.FIXED_ETF_RIGHT_NAME,
        "return_window_days": 1,
        "display_window_days": 2,
    }
    assert set(payload["series"].keys()) == {"dates", "left_return", "right_return", "spread"}


def test_fetch_index_history_uses_monitor_drawdown_fetch_index_data(monkeypatch):
    calls = []

    def fake_fetch_index_data(symbol: str, start_str: str, end_str: str) -> pd.DataFrame:
        calls.append((symbol, start_str, end_str))
        return pd.DataFrame(
            {
                "trade_date": ["2024-01-02", "2024-01-01", "2024-01-01"],
                "close": ["110.0", "100.0", "99.0"],
            }
        )

    monkeypatch.setattr(srp.md, "fetch_index_data", fake_fetch_index_data)

    result = srp.fetch_index_history("399376")

    assert len(calls) == 1
    assert calls[0][0] == "399376"
    assert result["date"].dt.strftime("%Y-%m-%d").tolist() == ["2024-01-01", "2024-01-02"]
    assert result["close"].tolist() == [99.0, 110.0]


def test_fetch_index_history_raises_runtime_error_when_normalized_result_is_empty(monkeypatch):
    monkeypatch.setattr(srp.md, "fetch_index_data", lambda symbol, start_str, end_str: pd.DataFrame())

    with pytest.raises(RuntimeError, match="指数历史数据规范化后为空: 399376"):
        srp.fetch_index_history("399376")


def test_configure_matplotlib_fonts_raises_when_no_cjk_font_available(monkeypatch):
    fake_font = Mock()
    fake_font.name = "DejaVu Sans"
    monkeypatch.setattr(style_chart.font_manager.fontManager, "ttflist", [fake_font])

    with pytest.raises(RuntimeError, match="未找到可用中文字体"):
        style_chart.configure_matplotlib_fonts()


def test_extract_series_rejects_mismatched_dates_and_spread_lengths():
    payload = {
        "series": {
            "dates": ["2024-01-01", "2024-01-02"],
            "spread": [1.5],
        }
    }

    with pytest.raises(ValueError, match="length mismatch"):
        style_chart._extract_series(payload)


def test_extract_series_rejects_non_mapping_series():
    payload = {"series": [1, 2, 3]}

    with pytest.raises(ValueError, match="must be a mapping"):
        style_chart._extract_series(payload)


def test_extract_series_deduplicates_and_sorts_dates():
    payload = {
        "series": {
            "dates": ["2024-01-03", "2024-01-01", "2024-01-03", "2024-01-02"],
            "spread": [3.2, 1.5, 4.8, -2.0],
        }
    }

    dates, spread = style_chart._extract_series(payload)

    assert dates.strftime("%Y-%m-%d").tolist() == ["2024-01-01", "2024-01-02", "2024-01-03"]
    assert spread.tolist() == [1.5, -2.0, 4.8]


def test_extract_series_accepts_pandas_series_inputs():
    payload = {
        "series": {
            "dates": pd.Series(["2024-01-02", "2024-01-01"]),
            "spread": pd.Series([2.5, -1.0]),
        }
    }

    dates, spread = style_chart._extract_series(payload)

    assert dates.strftime("%Y-%m-%d").tolist() == ["2024-01-01", "2024-01-02"]
    assert spread.tolist() == [-1.0, 2.5]


def test_extract_series_rejects_invalid_date_or_spread_values():
    invalid_date_payload = {
        "series": {
            "dates": ["2024-01-01", "not-a-date"],
            "spread": [1.0, 2.0],
        }
    }
    invalid_spread_payload = {
        "series": {
            "dates": ["2024-01-01", "2024-01-02"],
            "spread": [1.0, "not-a-number"],
        }
    }

    with pytest.raises(ValueError, match="invalid date values"):
        style_chart._extract_series(invalid_date_payload)
    with pytest.raises(ValueError, match="invalid numeric values"):
        style_chart._extract_series(invalid_spread_payload)


def test_generate_style_rotation_chart_rejects_non_mapping_payload(tmp_path):
    with pytest.raises(ValueError, match="payload must be a mapping"):
        style_chart.generate_style_rotation_chart(["not", "a", "mapping"], tmp_path)


def test_chart_helpers_include_symbols_latest_date_and_spread():
    meta = {
        "left_name": "国证小盘成长",
        "left_symbol": "399376",
        "right_name": "国证大盘价值",
        "right_symbol": "399373",
    }
    payload = {
        "meta": meta,
        "series": {
            "dates": ["2026-05-30", "2026-06-02"],
            "spread": [57.11, 58.23],
        },
    }

    assert (
        style_chart._build_chart_title(meta)
        == "风格轮动收益率差值（国证小盘成长(399376) vs 国证大盘价值(399373)）"
    )
    assert (
        style_chart._build_footer_text(payload)
        == "最新日期：2026年6月2日    最新差值：58.23%"
    )
    assert style_chart._build_latest_x_axis_label(payload) == "2026-06-02"
    assert style_chart.SPREAD_LINE_WIDTH == 1.6


def test_hide_matching_x_tick_labels_blanks_only_matching_label():
    labels = ["2026-04-01", "2026-05-01", "2026-06-01"]

    hidden = style_chart._hide_matching_x_tick_labels(labels, "2026-06-01")

    assert hidden == ["2026-04-01", "2026-05-01", ""]


def test_hide_matching_tick_label_objects_hides_only_matching_label():
    class FakeTick:
        def __init__(self, text):
            self.visible = True
            self.text = text

        def set_visible(self, value):
            self.visible = value

        def get_text(self):
            return self.text

    first = FakeTick("2026-05-01")
    last = FakeTick("2026-06-01")

    style_chart._hide_matching_tick_label_objects([first, last], "2026-06-01")

    assert first.visible is True
    assert last.visible is False


def test_generate_style_rotation_chart_creates_png(tmp_path):
    if not style_chart.get_available_cjk_fonts():
        pytest.skip("environment has no preferred CJK font available")

    payload = {
        "meta": {
            "left_name": "国证小盘成长",
            "left_symbol": "399376",
            "right_name": "国证大盘价值",
            "right_symbol": "399373",
            "return_window_days": 1,
            "display_window_days": 3,
        },
        "series": {
            "dates": ["2024-01-01", "2024-01-02", "2024-01-03"],
            "left_return": [2.0, 1.0, 4.0],
            "right_return": [0.5, 3.0, 0.8],
            "spread": [1.5, -2.0, 3.2],
        },
    }

    output_path = style_chart.generate_style_rotation_chart(payload, tmp_path)

    assert output_path.exists()
    assert output_path.suffix == ".png"
    assert output_path.stat().st_size > 5 * 1024


def test_preview_main_writes_chart_and_returns_zero(tmp_path, monkeypatch, capsys):
    import preview_style_rotation_chart as preview_module

    fake_payload = {
        "meta": {
            "left_name": "国证小盘成长",
            "right_name": "国证大盘价值",
        },
        "series": {
            "dates": ["2024-01-01"],
            "left_return": [1.0],
            "right_return": [0.5],
            "spread": [0.5],
        },
    }
    fake_output_path = tmp_path / "style_rotation_preview.png"
    collect_mock = Mock(return_value=fake_payload)
    generate_mock = Mock(return_value=fake_output_path)

    monkeypatch.setattr(
        preview_module.style_rotation_preview,
        "collect_style_rotation_preview_payload",
        collect_mock,
    )
    monkeypatch.setattr(
        preview_module.prototype_style_rotation_chart,
        "generate_style_rotation_chart",
        generate_mock,
    )

    result = preview_module.main()
    captured = capsys.readouterr()

    assert result == 0
    assert captured.out.strip() == f"[INFO] 风格轮动预览图已生成: {fake_output_path}"
    collect_mock.assert_called_once_with()
    generate_mock.assert_called_once_with(fake_payload, preview_module.DEFAULT_OUTPUT_DIR)
