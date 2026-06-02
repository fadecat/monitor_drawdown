from pathlib import Path

import preview_style_rotation_etf_email as module


def test_collect_style_rotation_etf_email_payloads_uses_preview_pipeline(monkeypatch, tmp_path: Path):
    preview_payload = {
        "meta": {
            "left_name": "成长ETF易方达",
            "right_name": "价值ETF易方达",
            "return_window_days": 40,
            "display_window_days": 180,
        },
        "series": {
            "dates": ["2026-05-28", "2026-05-29"],
            "spread": [1.11, 2.34],
        },
    }
    seen = {}

    def fake_collect(*, return_window_days=40, display_window_days=180):
        seen["window"] = (return_window_days, display_window_days)
        return preview_payload

    def fake_generate(payload, output_dir):
        seen["payload"] = payload
        seen["output_dir"] = output_dir
        path = output_dir / "style_rotation_etf_preview.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"png")
        return path

    monkeypatch.setattr(module.analysis, "collect_etf_style_rotation_preview_payload", fake_collect)
    monkeypatch.setattr(module.chart, "generate_style_rotation_chart", fake_generate)

    result = module.collect_style_rotation_etf_email_payloads(output_dir=tmp_path / "out")

    assert seen["window"] == (40, 180)
    assert seen["payload"] == preview_payload
    assert seen["output_dir"] == tmp_path / "out"
    assert result["payload"] == preview_payload
    assert result["as_of_label"] == "2026-05-29"
    assert result["chart_path"].name == "style_rotation_etf_preview.png"


def test_write_preview_html_outputs_file(tmp_path: Path):
    html = "<html><body>preview</body></html>"

    output_path = module.write_preview_html(html, tmp_path)

    assert output_path == tmp_path / "preview_style_rotation_etf_email.html"
    assert output_path.read_text(encoding="utf-8") == html
