import json
from datetime import date
from pathlib import Path

import analyze_etf_com_cn_period_returns as module


def test_shift_years_clamps_shorter_month_end():
    assert module.shift_years(date(2024, 2, 29), 1) == date(2023, 2, 28)


def test_shift_months_clamps_shorter_month_end():
    assert module.shift_months(date(2026, 3, 31), 1) == date(2026, 2, 28)


def test_select_base_record_returns_none_when_history_is_insufficient():
    rows = [
        {"trdDt": "2026-05-10", "adjUnitNav": 1.00},
        {"trdDt": "2026-05-29", "adjUnitNav": 1.10},
    ]

    record = module.select_base_record(rows, date(2026, 4, 29))

    assert record is None


def test_compute_period_return_returns_unavailable_when_base_missing():
    rows = [
        {"trdDt": "2026-05-10", "adjUnitNav": 1.00},
        {"trdDt": "2026-05-29", "adjUnitNav": 1.10},
    ]

    result = module.compute_period_return(rows, "3y", date(2023, 5, 29))

    assert result == {
        "label": "3y",
        "available": False,
        "base_date": None,
        "return_pct": None,
    }


def test_compute_period_return_uses_adj_unit_nav():
    rows = [
        {"trdDt": "2026-04-29", "adjUnitNav": 1.00},
        {"trdDt": "2026-05-29", "adjUnitNav": 1.10},
    ]

    result = module.compute_period_return(rows, "1m", date(2026, 4, 29))

    assert result == {
        "label": "1m",
        "available": True,
        "base_date": "2026-04-29",
        "return_pct": 10.0,
    }


def test_compute_period_returns_includes_expected_labels():
    rows = [
        {"trdDt": "2020-05-29", "adjUnitNav": 1.00},
        {"trdDt": "2023-05-29", "adjUnitNav": 1.20},
        {"trdDt": "2025-11-28", "adjUnitNav": 1.30},
        {"trdDt": "2026-02-27", "adjUnitNav": 1.40},
        {"trdDt": "2026-04-29", "adjUnitNav": 1.50},
        {"trdDt": "2026-05-29", "adjUnitNav": 1.65},
    ]

    result = module.compute_period_returns("159999", rows)

    assert result["code"] == "159999"
    assert result["latest_date"] == "2026-05-29"
    assert set(result["period_returns"]) == {
        "1m",
        "3m",
        "6m",
        "1y",
        "ytd",
        "3y",
        "5y",
        "10y",
        "since_inception",
    }


def test_render_report_formats_unavailable_period_as_dashes(tmp_path: Path):
    analyses = [
        {
            "code": "159259",
            "latest_date": "2026-05-29",
            "period_returns": {
                "1m": {"available": True, "base_date": "2026-04-29", "return_pct": 9.79},
                "3m": {"available": True, "base_date": "2026-02-28", "return_pct": 28.14},
                "6m": {"available": True, "base_date": "2025-11-28", "return_pct": 52.38},
                "1y": {"available": False, "base_date": None, "return_pct": None},
                "ytd": {"available": True, "base_date": "2025-12-31", "return_pct": 37.41},
                "3y": {"available": False, "base_date": None, "return_pct": None},
                "5y": {"available": False, "base_date": None, "return_pct": None},
                "10y": {"available": False, "base_date": None, "return_pct": None},
                "since_inception": {"available": True, "base_date": "2025-08-20", "return_pct": 45.32},
            },
        }
    ]

    report = module.render_report(analyses, output_dir=tmp_path)

    assert "159259" in report
    assert "近1年: `--`" in report
    assert "近3年: `--`" in report
    assert "成立以来: `45.32%`" in report


def test_write_analysis_payloads_creates_json_files(tmp_path: Path):
    analyses = [
        {
            "code": "159934",
            "latest_date": "2026-05-29",
            "period_returns": {
                "1m": {"available": True, "base_date": "2026-04-29", "return_pct": -2.52},
            },
        }
    ]

    module.write_analysis_payloads(analyses, output_dir=tmp_path)

    assert (tmp_path / "159934_period_returns.json").exists()


def test_fetch_fund_names_posts_fund_codes_payload(monkeypatch):
    post_calls = []

    class FakeResponse:
        def json(self):
            return {
                "success": True,
                "data": [
                    {"fundCode": "159934", "fundName": "黄金ETF易方达"},
                    {"fundCode": "159941", "fundName": "纳指ETF广发"},
                ],
            }

        def raise_for_status(self):
            return None

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, json, timeout):
            post_calls.append({"url": url, "json": json, "timeout": timeout})
            return FakeResponse()

    monkeypatch.setattr(module.requests, "Session", lambda: FakeSession())

    names = module.fetch_fund_names(["159934", "159941"])

    assert post_calls == [
        {
            "url": module.SIMPLE_LIST_URL,
            "json": {"fundCodes": ["159934", "159941"]},
            "timeout": module.REQUEST_TIMEOUT,
        }
    ]
    assert names == {
        "159934": "黄金ETF易方达",
        "159941": "纳指ETF广发",
    }


def test_fetch_fund_names_prefers_short_name_when_available(monkeypatch):
    class FakeResponse:
        def json(self):
            return {
                "success": True,
                "data": [
                    {
                        "fundCode": "159934",
                        "fundName": "易方达黄金ETF",
                        "extdSecuSht": "黄金ETF易方达",
                    }
                ],
            }

        def raise_for_status(self):
            return None

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, json, timeout):
            return FakeResponse()

    monkeypatch.setattr(module.requests, "Session", lambda: FakeSession())

    names = module.fetch_fund_names(["159934"])

    assert names == {"159934": "黄金ETF易方达"}


def test_load_period_return_email_codes_reads_codes_only_config(tmp_path: Path):
    config_path = tmp_path / "period_return_email_config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "codes:",
                "  - 159934",
                "  - '159941'",
                "  - 159934",
                "  - ''",
            ]
        ),
        encoding="utf-8",
    )

    codes = module.load_period_return_email_codes(config_path)

    assert codes == ["159934", "159941"]


def test_build_one_month_curve_uses_nearest_prior_trading_day():
    rows = [
        {"trdDt": "2026-04-28", "adjUnitNav": 0.98},
        {"trdDt": "2026-04-29", "adjUnitNav": 1.00},
        {"trdDt": "2026-04-30", "adjUnitNav": 1.03},
        {"trdDt": "2026-05-29", "adjUnitNav": 1.10},
    ]

    curve = module.build_one_month_curve(rows)

    assert curve == [
        {"date": "2026-04-29", "return_pct": 0.0},
        {"date": "2026-04-30", "return_pct": 3.0},
        {"date": "2026-05-29", "return_pct": 10.0},
    ]


def test_build_table_rows_formats_display_values():
    analyses = [
        {
            "code": "159934",
            "latest_date": "2026-05-29",
            "period_returns": {
                "1m": {"available": True, "base_date": "2026-04-29", "return_pct": -2.52},
                "3m": {"available": True, "base_date": "2026-02-27", "return_pct": -13.96},
                "6m": {"available": True, "base_date": "2025-11-28", "return_pct": 3.56},
                "1y": {"available": True, "base_date": "2025-05-29", "return_pct": 28.30},
                "ytd": {"available": True, "base_date": "2025-12-31", "return_pct": 0.77},
                "3y": {"available": True, "base_date": "2023-05-29", "return_pct": 117.93},
                "5y": {"available": True, "base_date": "2021-05-28", "return_pct": 146.21},
                "10y": {"available": True, "base_date": "2016-05-27", "return_pct": 261.80},
                "since_inception": {"available": True, "base_date": "2013-11-29", "return_pct": 278.74},
            },
        }
    ]

    rows = module.build_table_rows(analyses, {"159934": "黄金ETF易方达"})

    assert rows == [
        {
            "name": "黄金ETF易方达",
            "code": "159934",
            "return_1m": "-2.52%",
            "return_3m": "-13.96%",
            "return_6m": "3.56%",
            "return_1y": "28.30%",
            "return_ytd": "0.77%",
            "return_3y": "117.93%",
            "return_5y": "146.21%",
            "return_10y": "261.80%",
            "return_since_inception": "278.74%",
        }
    ]


def test_write_table_json_creates_flattened_table_file(tmp_path: Path):
    rows = [
        {
            "name": "黄金ETF易方达",
            "code": "159934",
            "return_1m": "-2.52%",
            "return_3m": "-13.96%",
            "return_6m": "3.56%",
            "return_1y": "28.30%",
            "return_ytd": "0.77%",
            "return_3y": "117.93%",
            "return_5y": "146.21%",
            "return_10y": "261.80%",
            "return_since_inception": "278.74%",
        }
    ]

    module.write_table_json(rows, output_dir=tmp_path)

    payload = json.loads((tmp_path / "table.json").read_text(encoding="utf-8"))
    assert payload == rows
