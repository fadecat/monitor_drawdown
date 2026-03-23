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
