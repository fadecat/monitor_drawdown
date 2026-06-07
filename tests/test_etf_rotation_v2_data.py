from __future__ import annotations

import pandas as pd

import etf_rotation_v2_data as module


def test_fetch_selected_series_loads_etf_nav_rows(monkeypatch):
    monkeypatch.setattr(
        module.etf_analysis,
        "load_nav_rows",
        lambda code: [
            {"trdDt": "2026-06-03", "adjUnitNav": "1.03"},
            {"trdDt": "2026-06-01", "adjUnitNav": "1.01"},
            {"trdDt": "2026-06-02", "adjUnitNav": ""},
            {"trdDt": "2026-06-03", "adjUnitNav": "1.04"},
        ],
    )

    series, summary = module.fetch_selected_series({"kind": "etf", "code": "510001"})

    assert series == [
        {"date": "2026-06-01", "close": 1.01},
        {"date": "2026-06-03", "close": 1.04},
    ]
    assert summary == {
        "status": "ok",
        "selected_kind": "etf",
        "selected_code": "510001",
        "rows": 2,
        "date_start": "2026-06-01",
        "date_end": "2026-06-03",
        "latest_close": 1.04,
    }


def test_fetch_selected_series_loads_index_eod_rows(monkeypatch):
    seen = {}

    monkeypatch.setattr(module.md, "build_index_eod_price_url", lambda code: f"https://example/{code}")
    monkeypatch.setattr(
        module.md,
        "fetch_json_response",
        lambda name, url: seen.setdefault("request", {"name": name, "url": url}) or [],
    )
    monkeypatch.setattr(
        module.md,
        "parse_index_eod_price_rows",
        lambda rows: pd.DataFrame(
            [
                {"date": pd.Timestamp("2026-06-01"), "close": 100.0},
                {"date": pd.Timestamp("2026-06-02"), "close": 101.5},
            ]
        ),
    )

    series, summary = module.fetch_selected_series({"kind": "index", "code": "980080.CN"})

    assert seen["request"] == {"name": "index_eod_price", "url": "https://example/980080.CN"}
    assert series == [
        {"date": "2026-06-01", "close": 100.0},
        {"date": "2026-06-02", "close": 101.5},
    ]
    assert summary["date_end"] == "2026-06-02"


def test_fetch_selected_series_rejects_unknown_kind():
    try:
        module.fetch_selected_series({"kind": "bond", "code": "x"})
    except ValueError as exc:
        assert "unsupported kind" in str(exc)
    else:
        raise AssertionError("expected unsupported kind to fail")
