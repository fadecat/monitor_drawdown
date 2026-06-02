from pathlib import Path

import preview_period_return_email as module


def test_build_period_return_email_html_places_chart_before_table():
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

    html = module.build_period_return_email_html(
        table_rows=rows,
        chart_data_uri="data:image/png;base64,abc",
        as_of_label="2026-05-29",
    )

    assert "近1月收益率走势图" in html
    assert "近1月" in html
    assert "成立以来" in html
    assert html.index("data:image/png;base64,abc") < html.index("区间收益率表格")
    assert html.index('alt="近1月收益率走势图"') < html.index("名称")


def test_build_period_return_email_html_uses_email_table_layout():
    html = module.build_period_return_email_html(
        table_rows=[],
        chart_data_uri="data:image/png;base64,abc",
        as_of_label="2026-05-29",
    )

    assert 'role="presentation"' in html
    assert 'width="100%"' in html
    assert "max-width:1180px" not in html


def test_write_preview_outputs_html_file(tmp_path: Path):
    html = "<html><body>preview</body></html>"

    output_path = module.write_preview_html(html, tmp_path)

    assert output_path == tmp_path / "preview_period_return_email.html"
    assert output_path.read_text(encoding="utf-8") == html


def test_load_curve_payloads_supports_target_key_storage_name(tmp_path: Path):
    one_month_dir = tmp_path / "one_month_analysis"
    one_month_dir.mkdir(parents=True, exist_ok=True)
    (one_month_dir / "etf_com_cn__159934_one_month_curve.json").write_text(
        '[{"date":"2026-05-29","return_pct":0.0}]',
        encoding="utf-8",
    )

    payloads = module.load_curve_payloads(["etf_com_cn:159934"], sample_dir=tmp_path)

    assert payloads == {
        "etf_com_cn:159934": [{"date": "2026-05-29", "return_pct": 0.0}]
    }


def test_preview_main_builds_html_for_mixed_source_targets(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(module, "DEFAULT_CONFIG_PATH", tmp_path / "period_return_email_config.yaml")
    monkeypatch.setattr(module, "DEFAULT_OUTPUT_DIR", tmp_path / "out")

    payloads = {
        "analyses": [
            {"code": "159934", "latest_date": "2026-05-29", "period_returns": {}},
            {"code": "cb_equal_weight", "latest_date": "2026-06-02", "period_returns": {}},
        ],
        "table_rows": [
            {"target_key": "etf_com_cn:159934", "name": "黄金ETF易方达", "code": "159934", "return_1m": "10.00%"},
            {"target_key": "jisilu_cb_index:cb_equal_weight", "name": "集思录转债等权", "code": "cb_equal_weight", "return_1m": "2.50%"},
        ],
        "curve_payloads": {
            "etf_com_cn:159934": [{"date": "2026-05-29", "return_pct": 0.0}],
            "jisilu_cb_index:cb_equal_weight": [{"date": "2026-06-02", "return_pct": 0.0}],
        },
        "as_of_label": "2026-06-02",
    }

    monkeypatch.setattr(module.analysis, "collect_period_return_payloads", lambda config_path, output_dir: payloads)

    chart_path = tmp_path / "out" / "chart.png"
    chart_path.parent.mkdir(parents=True, exist_ok=True)
    chart_path.write_bytes(b"png")
    monkeypatch.setattr(module.chart, "generate_one_month_return_chart", lambda table_rows, curve_payloads, output_dir: chart_path)

    exit_code = module.main()

    html = (tmp_path / "out" / "preview_period_return_email.html").read_text(encoding="utf-8")
    assert exit_code == 0
    assert "黄金ETF易方达" in html
    assert "集思录转债等权" in html
    assert "2026-06-02" in html
