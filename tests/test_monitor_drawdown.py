import pandas as pd

import monitor_drawdown as md


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
    monkeypatch.setattr(
        md.requests,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("EOD source unavailable")),
    )

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


def test_fetch_index_data_prefers_efunds_eod_price(monkeypatch):
    eod_rows = [
        {"trdDt": "2026-03-20", "pxClose": 4567.018, "trdCode": "930955"},
        {"trdDt": "2026-03-23", "pxClose": 4417.997, "trdCode": "930955"},
    ]
    monkeypatch.setattr(md.requests, "get", lambda *args, **kwargs: FakeResponse(eod_rows))
    monkeypatch.setattr(
        md,
        "fetch_tickflow_klines",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("TickFlow should not be called")),
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


def test_build_email_html_content_uses_780px_container_and_full_bleed_chart():
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
    )

    assert 'width="780"' in content
    assert "max-width:780px" in content
    assert 'padding:14px 0 0 0' in content
    assert 'style="width:100%;max-width:100%;height:auto;display:block"' in content
