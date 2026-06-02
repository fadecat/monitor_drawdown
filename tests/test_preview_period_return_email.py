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
