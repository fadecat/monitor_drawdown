import json
from pathlib import Path
import shutil
import uuid

import pandas as pd
import pytest

import monitor_drawdown as md
import prototype_valuation_percentile_chart as valuation_chart


class FakeKlines:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def get(self, symbol, **kwargs):
        self.calls.append((symbol, kwargs))
        response = self.responses[symbol]
        if isinstance(response, Exception):
            raise response
        return response


class FakeTickFlowClient:
    def __init__(self, responses):
        self.klines = FakeKlines(responses)
        self.closed = False

    def close(self):
        self.closed = True


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def sample_style_rotation_payload():
    return {
        "meta": {
            "left_name": "国证小盘成长",
            "right_name": "国证大盘价值",
            "return_window_days": 250,
            "display_window_days": 252,
        },
        "series": {
            "dates": ["2026-06-12"],
            "spread": [12.34],
        },
    }


def test_normalize_dataframe_supports_tickflow_trade_date():
    df = pd.DataFrame(
        {
            "trade_date": ["2026-03-20", "2026-03-23"],
            "close": [1.085, 1.046],
        }
    )

    normalized = md.normalize_dataframe(df)

    assert list(normalized.columns) == ["date", "close"]
    assert normalized["date"].dt.strftime("%Y-%m-%d").tolist() == ["2026-03-20", "2026-03-23"]
    assert normalized["close"].tolist() == [1.085, 1.046]


def test_build_tickflow_symbols():
    assert md.build_tickflow_etf_symbols("159307") == ["159307.SZ", "159307.SH"]
    assert md.build_tickflow_etf_symbols("sh512040") == ["512040.SH", "512040.SZ"]
    assert md.build_tickflow_index_symbols("000300") == ["000300.SH", "000300.SZ"]
    assert md.build_tickflow_index_symbols("399006") == ["399006.SZ", "399006.SH"]
    assert md.build_tickflow_index_symbols("csi000985") == ["000985.SH", "000985.SZ"]


def test_fetch_etf_data_prefers_tickflow(monkeypatch):
    tickflow_df = pd.DataFrame(
        {
            "trade_date": ["2026-03-20", "2026-03-23"],
            "close": [1.085, 1.046],
        }
    )

    fake_client = FakeTickFlowClient({"159307.SZ": tickflow_df})
    monkeypatch.setattr(md, "build_tickflow_client", lambda: fake_client)
    monkeypatch.setattr(
        md.ak,
        "fund_etf_hist_em",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("AkShare should not be called")),
        raising=False,
    )

    result = md.fetch_etf_data("159307", "20260301", "20260331")

    assert result["date"].dt.strftime("%Y-%m-%d").tolist() == ["2026-03-20", "2026-03-23"]
    assert result["close"].tolist() == [1.085, 1.046]
    assert fake_client.klines.calls[0][1]["adjust"] == "none"


def test_fetch_index_data_falls_back_to_akshare(monkeypatch):
    empty_tickflow_df = pd.DataFrame(columns=["trade_date", "close"])
    akshare_df = pd.DataFrame(
        {
            "日期": ["2026-03-20", "2026-03-23"],
            "收盘": [4567.018, 4417.997],
        }
    )

    monkeypatch.setattr(
        md,
        "build_tickflow_client",
        lambda: FakeTickFlowClient({"930955.SH": empty_tickflow_df, "930955.SZ": empty_tickflow_df}),
    )
    monkeypatch.setattr(md.ak, "stock_zh_index_daily_em", lambda **kwargs: akshare_df, raising=False)

    result = md.fetch_index_data("930955", "20260301", "20260331")

    assert result["date"].dt.strftime("%Y-%m-%d").tolist() == ["2026-03-20", "2026-03-23"]
    assert result["close"].tolist() == [4567.018, 4417.997]


def test_fetch_index_data_prefers_tickflow(monkeypatch):
    tickflow_df = pd.DataFrame(
        {
            "trade_date": ["2026-03-20", "2026-03-23"],
            "close": [4567.018, 4417.997],
        }
    )
    eod_calls = []

    def fake_fetch_index_eod_price_data(*args, **kwargs):
        eod_calls.append((args, kwargs))
        raise RuntimeError("EOD should not be called")

    monkeypatch.setattr(
        md,
        "fetch_index_eod_price_data",
        fake_fetch_index_eod_price_data,
    )
    monkeypatch.setattr(
        md,
        "build_tickflow_client",
        lambda: FakeTickFlowClient({"930955.SH": tickflow_df}),
    )
    monkeypatch.setattr(
        md.ak,
        "stock_zh_index_daily_em",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("AkShare should not be called")),
        raising=False,
    )

    result = md.fetch_index_data("930955", "20260301", "20260331")

    assert result["date"].dt.strftime("%Y-%m-%d").tolist() == ["2026-03-20", "2026-03-23"]
    assert result["close"].tolist() == [4567.018, 4417.997]
    assert eod_calls == []


def test_find_jisilu_index_etf_candidates_matches_index_id():
    rows = [
        {"cell": {"fund_id": "159915", "index_id": "399006", "fund_nm": "创业板ETF"}},
        {"cell": {"fund_id": "510300", "index_id": "000300", "fund_nm": "沪深300ETF"}},
    ]

    candidates = md.find_jisilu_index_etf_candidates(rows, "000300")

    assert len(candidates) == 1
    assert candidates[0]["fund_id"] == "510300"


def test_patch_etf_dataframe_with_jisilu_appends_today_price():
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-03-21", "2026-03-23"]),
            "close": [1.032, 1.046],
        }
    )
    rows = [
        {
            "cell": {
                "fund_id": "159307",
                "fund_nm": "红利低波100ETF(博时)",
                "price": "1.058",
                "pre_close": "1.0460",
                "increase_rt": "1.15",
                "index_nm": "红利低波100",
                "last_time": "15:00:00",
            }
        }
    ]

    patched_df, patch = md.patch_etf_dataframe_with_jisilu(
        df,
        "159307",
        rows,
        current_time=md.datetime(2026, 3, 24, 15, 30, tzinfo=md.BEIJING_TZ),
    )

    assert patch is not None
    assert patch["fund_id"] == "159307"
    assert patched_df["date"].dt.strftime("%Y-%m-%d").tolist() == ["2026-03-21", "2026-03-23", "2026-03-24"]
    assert patched_df.iloc[-1]["close"] == 1.058


def test_patch_index_dataframe_with_jisilu_appends_synthetic_today_row():
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-03-21", "2026-03-23"]),
            "close": [4380.0, 4417.997],
        }
    )
    rows = [
        {
            "cell": {
                "fund_id": "510300",
                "fund_nm": "沪深300ETF",
                "index_id": "000300",
                "index_nm": "沪深300",
                "price": "4.498",
                "pre_close": "4.4610",
                "idx_price_dt": "2026-03-24",
                "volume": "120000.55",
                "amount": "2000000",
                "last_time": "15:00:00",
            }
        }
    ]

    patched_df, patch = md.patch_index_dataframe_with_jisilu(
        df,
        "000300",
        rows,
        current_time=md.datetime(2026, 3, 24, 15, 30, tzinfo=md.BEIJING_TZ),
    )

    assert patch is not None
    assert patch["fund_id"] == "510300"
    assert round(patch["etf_return"], 6) == round(4.498 / 4.4610 - 1, 6)
    assert patched_df["date"].dt.strftime("%Y-%m-%d").tolist() == ["2026-03-21", "2026-03-23", "2026-03-24"]
    assert round(patched_df.iloc[-1]["close"], 6) == round(4417.997 * (4.498 / 4.4610), 6)


def test_fetch_index_dividend_yield_uses_latest_row(monkeypatch):
    payload = [
        {"dividendYield": 5.1234, "trdCode": "930955", "trdDt": "2026-03-20"},
        {"dividendYield": 5.2345, "trdCode": "930955", "trdDt": "2026-03-24"},
    ]
    calls = []

    def fake_get(url, timeout):
        calls.append((url, timeout))
        return FakeResponse(payload)

    monkeypatch.setattr(md.requests, "get", fake_get)

    result = md.fetch_index_dividend_yield(
        "930955",
        url="https://cdn.efunds.com.cn/etf-net/index_dividend_ratio_930955.json",
    )

    assert result["index_code"] == "930955"
    assert result["index_dividend_yield"] == 5.2345
    assert result["index_dividend_yield_date"] == "2026-03-24"
    assert calls == [("https://cdn.efunds.com.cn/etf-net/index_dividend_ratio_930955.json", 15)]


def test_parse_index_detail_response_extracts_index_metadata_and_urls():
    result = md.parse_index_detail_response(
        {
            "success": True,
            "data": {
                "trdCode": "931052",
                "indexName": "中证国信价值指数",
                "indexSht": "国信价值",
                "indexType": "风格因子-价值",
                "dividendRatioJson": "https://cdn.efunds.com.cn/etf-net/index_dividend_ratio_931052.json",
                "valuationPercentileJson": "https://cdn.efunds.com.cn/etf-net/index_valuation_percentile_931052.json",
            },
        },
        fallback_index_code="931052",
    )

    assert result["index_code"] == "931052"
    assert result["index_name"] == "中证国信价值指数"
    assert result["index_dividend_yield_url"].endswith("index_dividend_ratio_931052.json")
    assert result["index_valuation_percentile_url"].endswith("index_valuation_percentile_931052.json")


def test_parse_index_valuation_percentile_rows_uses_latest_row():
    result = md.parse_index_valuation_percentile_rows(
        [
            {"trdCode": "931052", "trdDt": "2026-03-20", "pETtm": 9.1, "pETtm1Y": 40},
            {
                "trdCode": "931052",
                "trdDt": "2026-03-24",
                "pETtm": 10.8491,
                "pETtm3M": 100,
                "pETtm1Y": 98.2,
                "pBLf": 1.4048,
                "pBLf3M": 75.4386,
                "pSTtm": 1.7871,
                "pSTtmBgn": 97.8282,
            },
        ],
        fallback_index_code="931052",
    )

    assert result["index_code"] == "931052"
    assert result["index_valuation_date"] == "2026-03-24"
    assert result["index_valuation_metrics"]["PE(TTM)"]["current"] == 10.8491
    assert result["index_valuation_metrics"]["PE(TTM)"]["percentiles"]["3M"] == 100
    assert result["index_valuation_metrics"]["PB(LF)"]["percentiles"]["3M"] == 75.4386


def test_build_webhook_markdown_includes_index_dividend_yield():
    content = md.build_webhook_markdown_content(
        [
            {
                "name": "红利低波100ETF(博时)",
                "code": "159307",
                "drawdown": 0.052,
                "current_price": 1.058,
                "peak_price": 1.116,
                "peak_date": "2026-03-10",
                "index_code": "930955",
                "index_name": "中证红利低波动100指数",
                "index_dividend_yield": 5.2345,
                "index_dividend_yield_date": "2026-03-24",
                "index_valuation_date": "2026-03-24",
                "index_valuation_metrics": {
                    "PE(TTM)": {"current": 10.8491, "percentiles": {"3M": 100, "1Y": 98.2}},
                    "PB(LF)": {"current": 1.4048, "percentiles": {"3M": 75.4386}},
                    "PS(TTM)": {"current": 1.7871, "percentiles": {"成立以来": 97.8282}},
                },
            }
        ],
        current_time=md.datetime(2026, 3, 24, 15, 30, tzinfo=md.BEIJING_TZ),
    )

    assert "> 追踪指数股息率: **5.23%** (930955, 2026-03-24)" in content


def test_load_email_config_defaults_to_qq_smtp(monkeypatch):
    monkeypatch.setenv("RECEIVER_EMAIL", "alice@example.com; bob@example.com,alice@example.com")
    monkeypatch.setenv("SMTP_USER", "sender@qq.com")
    monkeypatch.setenv("SMTP_PASS", "qq_auth_code")
    monkeypatch.delenv("EMAIL_SMTP_HOST", raising=False)
    monkeypatch.delenv("EMAIL_SMTP_PORT", raising=False)
    monkeypatch.delenv("EMAIL_FROM", raising=False)

    config = md.load_email_config_from_env()

    assert config["smtp_host"] == "smtp.qq.com"
    assert config["smtp_port"] == 465
    assert config["sender"] == "sender@qq.com"
    assert config["recipients"] == ["alice@example.com", "bob@example.com"]


def test_load_email_config_supports_legacy_email_env_names(monkeypatch):
    monkeypatch.setenv("EMAIL_TO", "legacy@example.com")
    monkeypatch.setenv("EMAIL_USER", "legacy@qq.com")
    monkeypatch.setenv("EMAIL_PASSWORD", "legacy_auth_code")
    monkeypatch.delenv("RECEIVER_EMAIL", raising=False)
    monkeypatch.delenv("SMTP_USER", raising=False)
    monkeypatch.delenv("SMTP_PASS", raising=False)

    config = md.load_email_config_from_env()

    assert config["recipients"] == ["legacy@example.com"]
    assert config["username"] == "legacy@qq.com"


def test_build_email_html_content_uses_table_and_escapes_values():
    content = md.build_email_html_content(
        [
            {
                "name": "红利低波100ETF & 博时",
                "code": "159307",
                "drawdown": 0.052,
                "current_price": 1.058,
                "peak_price": 1.116,
                "peak_date": "2026-03-10",
                "index_code": "930955",
                "index_name": "中证红利低波动100指数",
                "index_dividend_yield": 5.2345,
                "index_dividend_yield_date": "2026-03-24",
                "index_valuation_date": "2026-03-24",
                "index_valuation_metrics": {
                    "PE(TTM)": {"current": 10.8491, "percentiles": {"3M": 100, "1Y": 98.2}},
                    "PB(LF)": {"current": 1.4048, "percentiles": {"3M": 75.4386}},
                    "PS(TTM)": {"current": 1.7871, "percentiles": {"成立以来": 97.8282}},
                },
            }
        ],
        current_time=md.datetime(2026, 3, 24, 15, 30, tzinfo=md.BEIJING_TZ),
    )

    assert "<table" in content
    assert '<meta charset="utf-8">' in content
    assert "指数估值监控" in content
    assert "中证红利低波动100指数" in content
    assert "930955" in content
    assert "股息率" in content
    assert "5.23%" in content
    assert "10.85" in content
    assert "PE(TTM)" in content
    # extreme percentile values use the new soft red
    assert 'color:#D32F2F">98.20%' in content
    assert "<th" in content  # table headers present
    # legacy sections/labels are gone
    assert "告警汇总" not in content
    assert "红利低波100ETF" not in content
    assert "追踪指数" not in content


def test_build_email_html_content_renders_full_bleed_charts_and_fx_chart():
    content = md.build_email_html_content(
        [],
        valuation_items=[
            {
                "name": "中证红利低波动100指数",
                "code": "930955",
                "index_code": "930955",
                "index_name": "中证红利低波动100指数",
                "index_valuation_date": "2026-04-22",
                "index_valuation_metrics": {
                    "PE(TTM)": {"current": 9.19, "percentiles": {"5Y": 91.24}},
                    "PB(LF)": {"current": 0.92, "percentiles": {"5Y": 89.01}},
                },
                "index_dividend_yield": 4.63,
            }
        ],
        current_time=md.datetime(2026, 4, 23, 23, 45, tzinfo=md.BEIJING_TZ),
        chart_paths={"930955": md.Path(".test_artifacts/valuation_percentile/valuation_percentile_930955.png")},
        fx_chart_path=md.Path(".test_artifacts/fx/fx_usd_cny_vs_mid_10y.png"),
    )

    assert 'width="100%" style="background:#ffffff;border-radius:12px;overflow:hidden"' in content
    assert 'padding:14px 0 0 0' in content
    assert 'style="width:100%;max-width:100%;height:auto;display:block"' in content
    assert 'cid:fx_usd_cny_vs_mid_10y' in content
    assert "美元人民币汇率对比图" in content


def test_build_email_content_includes_style_rotation_section():
    payload = sample_style_rotation_payload()

    html = md.build_email_html_content(
        [],
        valuation_items=[],
        current_time=md.datetime(2026, 6, 13, 15, 30, tzinfo=md.BEIJING_TZ),
        style_rotation_payload=payload,
        style_rotation_as_of_label="2026-06-12",
        style_rotation_chart_path=md.Path(".test_artifacts/style_rotation/style_rotation_preview.png"),
    )
    text = md.build_email_plain_text_content(
        [],
        valuation_items=[],
        current_time=md.datetime(2026, 6, 13, 15, 30, tzinfo=md.BEIJING_TZ),
        style_rotation_payload=payload,
        style_rotation_as_of_label="2026-06-12",
    )

    assert "风格轮动收益率差值" in html
    assert "国证小盘成长 vs 国证大盘价值" in html
    assert "当前差值 12.34%" in html
    assert "cid:style_rotation_chart" in html
    assert "风格轮动收益率差值" in text
    assert "国证小盘成长 vs 国证大盘价值" in text
    assert "当前差值: 12.34%" in text


def test_build_email_message_attaches_style_rotation_chart(tmp_path):
    chart_path = tmp_path / "style_rotation.png"
    chart_path.write_bytes(b"png-bytes")

    message = md.build_email_message(
        "sender@example.com",
        ["alice@example.com"],
        "核心标的监控告警",
        [],
        valuation_items=[],
        current_time=md.datetime(2026, 6, 13, 15, 30, tzinfo=md.BEIJING_TZ),
        style_rotation_payload=sample_style_rotation_payload(),
        style_rotation_as_of_label="2026-06-12",
        style_rotation_chart_path=chart_path,
    )

    html_part = message.get_payload()[-1]
    related = html_part.get_payload()

    assert any(part.get("Content-ID") == "<style_rotation_chart>" for part in related)


def test_fetch_index_pe_history_retries_on_connection_abort(monkeypatch):
    payload = [
        {"trdDt": "2026-03-20", "pETtm": 9.1},
        {"trdDt": "2026-03-24", "pETtm": 10.8},
    ]
    responses = [
        md.requests.exceptions.ConnectionError("Connection aborted. Remote end closed connection without response"),
        FakeResponse(payload),
    ]
    calls = []

    def fake_get(url, timeout):
        calls.append((url, timeout))
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(md.requests, "get", fake_get)
    monkeypatch.setattr(md.time, "sleep", lambda seconds: None)

    result = md.fetch_index_pe_history("931052", url="https://example.com/valuation.json")

    assert result["date"].dt.strftime("%Y-%m-%d").tolist() == ["2026-03-20", "2026-03-24"]
    assert result["pe"].tolist() == [9.1, 10.8]
    assert calls == [
        ("https://example.com/valuation.json", 15),
        ("https://example.com/valuation.json", 15),
    ]


def test_main_keeps_other_charts_when_one_valuation_chart_fails(monkeypatch, capsys):
    workspace_tmp = Path(".test_artifacts") / f"test_main_charts_{uuid.uuid4().hex}"
    workspace_tmp.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("WEBHOOK_URL", "https://example.invalid/webhook")
    monkeypatch.setenv("CONFIG_PATH", str(workspace_tmp / "config.yaml"))
    monkeypatch.setenv("RECEIVER_EMAIL", "alice@example.com")
    monkeypatch.setenv("SMTP_USER", "sender@example.com")
    monkeypatch.setenv("SMTP_PASS", "secret")

    config_path = workspace_tmp / "config.yaml"
    config_path.write_text(
        """
targets:
  - name: "价值100"
    code: "512040"
    type: "valuation"
  - name: "沪深300"
    code: "000300"
    type: "valuation"
""".strip(),
        encoding="utf-8",
    )

    metrics_by_code = {
        "512040": {
            "index_code": "931052",
            "index_name": "价值100",
            "index_dividend_yield": 4.0309,
            "index_dividend_yield_source": "https://example.com/dividend/931052.json",
            "index_valuation_date": "2026-05-12",
            "index_valuation_percentile_source": "https://example.com/valuation/931052.json",
            "index_valuation_metrics": {"PE(TTM)": {"current": 10.8, "percentiles": {"5Y": 91.2}}},
        },
        "000300": {
            "index_code": "000300",
            "index_name": "沪深300",
            "index_dividend_yield": 2.4652,
            "index_dividend_yield_source": "https://example.com/dividend/000300.json",
            "index_valuation_date": "2026-05-12",
            "index_valuation_percentile_source": "https://example.com/valuation/000300.json",
            "index_valuation_metrics": {"PE(TTM)": {"current": 12.3, "percentiles": {"5Y": 55.0}}},
        },
    }

    monkeypatch.setattr(md, "fetch_cn_10y_bond_yield", lambda: 1.7592)
    monkeypatch.setattr(
        md,
        "fetch_cn_10y_bond_history",
        lambda: pd.DataFrame({"date": pd.to_datetime(["2026-05-12"]), "yield_pct": [1.7592]}),
    )
    monkeypatch.setattr(md, "fetch_target_index_metrics", lambda target: metrics_by_code[str(target["code"])])
    monkeypatch.setattr(md, "attach_equity_bond_ratio", lambda item, bond_yield: None)
    monkeypatch.setattr(md, "attach_equity_bond_spread", lambda item, bond_history: None)
    monkeypatch.setattr(md, "send_webhook", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("send_webhook should not be called")))

    fx_png = workspace_tmp / "fx.png"
    fx_png.write_bytes(b"fx")
    style_png = workspace_tmp / "style_rotation.png"
    style_png.write_bytes(b"style")
    captured = {}

    def fake_send_email(
        config,
        triggered_items,
        valuation_items=None,
        current_time=None,
        chart_paths=None,
        fx_chart_path=None,
        style_rotation_payload=None,
        style_rotation_as_of_label=None,
        style_rotation_chart_path=None,
    ):
        captured.update(
            {
                "chart_paths": chart_paths,
                "fx_chart_path": fx_chart_path,
                "valuation_items": valuation_items,
                "style_rotation_payload": style_rotation_payload,
                "style_rotation_as_of_label": style_rotation_as_of_label,
                "style_rotation_chart_path": style_rotation_chart_path,
            }
        )

    monkeypatch.setattr(md, "send_email", fake_send_email)

    def fake_generate_fx_chart(output_dir):
        return fx_png

    def fake_generate_valuation_percentile_chart(target, output_dir):
        index_code = str(target.get("index_code") or target.get("code"))
        if index_code == "931052":
            raise RuntimeError("simulated chart failure")
        output_path = workspace_tmp / f"{index_code}.png"
        output_path.write_bytes(b"png")
        return output_path

    monkeypatch.setattr("prototype_fx_chart.generate_fx_chart", fake_generate_fx_chart)
    monkeypatch.setattr(valuation_chart, "generate_valuation_percentile_chart", fake_generate_valuation_percentile_chart)
    monkeypatch.setattr(
        "preview_style_rotation_email.collect_style_rotation_email_payloads",
        lambda output_dir: {
            "payload": sample_style_rotation_payload(),
            "as_of_label": "2026-06-12",
            "chart_path": style_png,
        },
    )

    try:
        md.main()

        output = capsys.readouterr().out
        assert "邮件图表批量生成异常" not in output
        assert "价值100" in output
        assert "simulated chart failure" in output
        assert captured["fx_chart_path"] == fx_png
        assert captured["chart_paths"] == {"000300": workspace_tmp / "000300.png"}
        assert captured["style_rotation_payload"] == sample_style_rotation_payload()
        assert captured["style_rotation_as_of_label"] == "2026-06-12"
        assert captured["style_rotation_chart_path"] == style_png
    finally:
        shutil.rmtree(workspace_tmp, ignore_errors=True)


def test_main_sends_email_when_style_rotation_collection_fails(monkeypatch, capsys, tmp_path):
    workspace_tmp = tmp_path / "style_rotation_failure"
    workspace_tmp.mkdir()
    monkeypatch.setenv("WEBHOOK_URL", "https://example.invalid/webhook")
    monkeypatch.setenv("CONFIG_PATH", str(workspace_tmp / "config.yaml"))
    monkeypatch.setenv("RECEIVER_EMAIL", "alice@example.com")
    monkeypatch.setenv("SMTP_USER", "sender@example.com")
    monkeypatch.setenv("SMTP_PASS", "secret")

    (workspace_tmp / "config.yaml").write_text(
        """
targets:
  - name: "沪深300"
    code: "000300"
    type: "valuation"
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setattr(md, "fetch_cn_10y_bond_yield", lambda: None)
    monkeypatch.setattr(
        md,
        "fetch_cn_10y_bond_history_with_archive_fallback",
        lambda: (
            pd.DataFrame({"date": pd.to_datetime(["2026-06-12"]), "yield_pct": [1.7]}),
            {"data_source": "live", "archive_latest_date": None},
        ),
    )
    monkeypatch.setattr(
        md,
        "fetch_target_index_metrics",
        lambda target: {
            "index_code": "000300",
            "index_name": "沪深300",
            "index_dividend_yield": 2.46,
            "index_valuation_date": "2026-06-12",
            "index_valuation_metrics": {"PE(TTM)": {"current": 12.3, "percentiles": {"5Y": 55.0}}},
        },
    )
    monkeypatch.setattr(md, "attach_equity_bond_spread", lambda item, bond_history: None)
    monkeypatch.setattr(md, "send_webhook", lambda *args, **kwargs: None)
    monkeypatch.setattr("prototype_fx_chart.generate_fx_chart", lambda output_dir: None)
    monkeypatch.setattr("prototype_valuation_percentile_chart.generate_valuation_percentile_chart", lambda target, output_dir: None)
    monkeypatch.setattr(
        "preview_style_rotation_email.collect_style_rotation_email_payloads",
        lambda output_dir: (_ for _ in ()).throw(RuntimeError("style failed")),
    )

    captured = {}

    def fake_send_email(
        config,
        triggered_items,
        valuation_items=None,
        current_time=None,
        chart_paths=None,
        fx_chart_path=None,
        style_rotation_payload=None,
        style_rotation_as_of_label=None,
        style_rotation_chart_path=None,
    ):
        captured["sent"] = True
        captured["style_rotation_payload"] = style_rotation_payload
        captured["style_rotation_chart_path"] = style_rotation_chart_path

    monkeypatch.setattr(md, "send_email", fake_send_email)

    md.main()

    output = capsys.readouterr().out
    assert captured["sent"] is True
    assert captured["style_rotation_payload"] is None
    assert captured["style_rotation_chart_path"] is None
    assert "风格轮动邮件区块生成失败" in output


def test_load_archive_records_reads_index_archive(tmp_path):
    archive_root = tmp_path / "data_archive"
    payload = {
        "source": "archive",
        "index_code": "931052",
        "updated_at": "2026-05-13T12:00:00+08:00",
        "records": [{"trdDt": "2026-05-12", "pETtm": 10.84}],
    }
    path = archive_root / "index_valuation_percentile" / "931052.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    records = md.load_archive_records(
        "index_valuation_percentile",
        "931052",
        archive_root=archive_root,
    )

    assert records == [{"trdDt": "2026-05-12", "pETtm": 10.84}]


def test_is_archive_fresh_rejects_records_older_than_seven_days():
    now = md.datetime(2026, 5, 13, 10, 0, tzinfo=md.BEIJING_TZ)

    assert md.is_archive_fresh("2026-05-06", now=now) is True
    assert md.is_archive_fresh("2026-05-05", now=now) is False


def test_fetch_index_dividend_yield_with_archive_fallback_prefers_live(monkeypatch, tmp_path):
    archive_reads = []

    def fake_load_archive_records(dataset_name, index_code=None, archive_root=None):
        archive_reads.append((dataset_name, index_code, archive_root))
        return []

    monkeypatch.setattr(
        md,
        "fetch_index_dividend_yield",
        lambda index_code, url="": {
            "index_code": index_code,
            "index_dividend_yield": 4.23,
            "index_dividend_yield_date": "2026-05-13",
        },
    )
    monkeypatch.setattr(md, "load_archive_records", fake_load_archive_records)

    result = md.fetch_index_dividend_yield_with_archive_fallback(
        "931052",
        archive_root=tmp_path / "data_archive",
    )

    assert result["data_source"] == "live"
    assert result["archive_latest_date"] is None
    assert archive_reads == []


def test_fetch_index_dividend_yield_with_archive_fallback_uses_fresh_archive(monkeypatch, tmp_path):
    monkeypatch.setattr(
        md,
        "fetch_index_dividend_yield",
        lambda index_code, url="": (_ for _ in ()).throw(RuntimeError("live failed")),
    )
    archive_root = tmp_path / "data_archive"
    path = archive_root / "index_dividend_ratio" / "931052.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "source": "archive",
                "index_code": "931052",
                "updated_at": "2026-05-13T12:00:00+08:00",
                "records": [{"trdCode": "931052", "trdDt": "2026-05-12", "dividendYield": 4.23}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = md.fetch_index_dividend_yield_with_archive_fallback(
        "931052",
        archive_root=archive_root,
        now=md.datetime(2026, 5, 13, 15, 0, tzinfo=md.BEIJING_TZ),
    )

    assert result["index_dividend_yield"] == 4.23
    assert result["data_source"] == "archive"
    assert result["archive_latest_date"] == "2026-05-12"


def test_fetch_index_dividend_yield_with_archive_fallback_rejects_stale_archive(monkeypatch, tmp_path):
    monkeypatch.setattr(
        md,
        "fetch_index_dividend_yield",
        lambda index_code, url="": (_ for _ in ()).throw(RuntimeError("live failed")),
    )
    archive_root = tmp_path / "data_archive"
    path = archive_root / "index_dividend_ratio" / "931052.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "source": "archive",
                "index_code": "931052",
                "updated_at": "2026-05-13T12:00:00+08:00",
                "records": [{"trdCode": "931052", "trdDt": "2026-05-04", "dividendYield": 4.23}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="live failed"):
        md.fetch_index_dividend_yield_with_archive_fallback(
            "931052",
            archive_root=archive_root,
            now=md.datetime(2026, 5, 13, 15, 0, tzinfo=md.BEIJING_TZ),
        )


def test_fetch_index_pe_history_with_archive_fallback_reconstructs_pe_series(monkeypatch, tmp_path):
    monkeypatch.setattr(
        md,
        "fetch_index_pe_history",
        lambda index_code, url="": (_ for _ in ()).throw(RuntimeError("live failed")),
    )
    archive_root = tmp_path / "data_archive"
    path = archive_root / "index_valuation_percentile" / "931052.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "source": "archive",
                "index_code": "931052",
                "updated_at": "2026-05-13T12:00:00+08:00",
                "records": [
                    {"trdDt": "2026-05-11", "pETtm": 9.11},
                    {"trdDt": "2026-05-12", "pETtm": 10.84},
                    {"trdDt": "2026-05-13", "pETtm": None},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    pe_df, meta = md.fetch_index_pe_history_with_archive_fallback(
        "931052",
        archive_root=archive_root,
        now=md.datetime(2026, 5, 13, 15, 0, tzinfo=md.BEIJING_TZ),
    )

    assert pe_df["date"].dt.strftime("%Y-%m-%d").tolist() == ["2026-05-11", "2026-05-12"]
    assert pe_df["pe"].tolist() == [9.11, 10.84]
    assert meta == {"data_source": "archive", "archive_latest_date": "2026-05-13"}


def test_build_email_plain_text_content_marks_archive_metrics():
    content = md.build_email_plain_text_content(
        [],
        valuation_items=[
            {
                "name": "中证红利低波动100指数",
                "index_code": "931052",
                "index_dividend_yield": 4.23,
                "index_dividend_yield_date": "2026-05-12",
                "index_dividend_yield_data_source": "archive",
                "index_dividend_yield_archive_latest_date": "2026-05-12",
                "index_valuation_date": "2026-05-12",
                "index_valuation_data_source": "archive",
                "index_valuation_archive_latest_date": "2026-05-12",
                "index_valuation_metrics": {
                    "PE(TTM)": {"current": 10.84, "percentiles": {"1Y": 98.2}},
                    "PB(LF)": {"current": 1.40, "percentiles": {"1Y": 75.4}},
                },
                "cn_10y_bond_yield": 1.73,
                "cn_10y_bond_yield_data_source": "archive",
                "cn_10y_bond_yield_archive_latest_date": "2026-05-12",
                "equity_bond_ratio": 7.49,
            }
        ],
        current_time=md.datetime(2026, 5, 13, 15, 0, tzinfo=md.BEIJING_TZ),
    )

    assert "股息率: 4.23% (2026-05-12) (archive, 2026-05-12)" in content
    assert "估值 (2026-05-12): PE(TTM) 10.84, PB(LF) 1.40 (archive, 2026-05-12)" in content
    assert "股债收益差: +7.49% (1/PE − 1.73% 10Y债) (archive, 2026-05-12)" in content


def test_build_email_html_content_marks_archive_metrics():
    content = md.build_email_html_content(
        [],
        valuation_items=[
            {
                "name": "中证红利低波动100指数",
                "index_code": "931052",
                "index_name": "中证红利低波动100指数",
                "index_dividend_yield": 4.23,
                "index_dividend_yield_data_source": "archive",
                "index_dividend_yield_archive_latest_date": "2026-05-12",
                "index_valuation_date": "2026-05-12",
                "index_valuation_data_source": "archive",
                "index_valuation_archive_latest_date": "2026-05-12",
                "index_valuation_metrics": {
                    "PE(TTM)": {"current": 10.84, "percentiles": {"1Y": 98.2, "3Y": 88.1, "5Y": 91.2}},
                    "PB(LF)": {"current": 1.40, "percentiles": {"1Y": 75.4, "3Y": 66.2, "5Y": 70.1}},
                },
                "cn_10y_bond_yield": 1.73,
                "cn_10y_bond_yield_data_source": "archive",
                "cn_10y_bond_yield_archive_latest_date": "2026-05-12",
                "equity_bond_ratio": 7.49,
            }
        ],
        current_time=md.datetime(2026, 5, 13, 15, 0, tzinfo=md.BEIJING_TZ),
    )

    assert "archive, 2026-05-12" in content
    assert "4.23%" in content
    assert "10.84" in content
