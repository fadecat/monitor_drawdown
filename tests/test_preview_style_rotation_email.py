from pathlib import Path

import preview_style_rotation_email as module


def test_collect_style_rotation_email_payloads_uses_preview_pipeline(monkeypatch, tmp_path: Path):
    preview_payload = {
        "meta": {
            "left_name": "国证小盘成长",
            "right_name": "国证大盘价值",
            "return_window_days": 250,
            "display_window_days": 252,
        },
        "series": {
            "dates": ["2026-06-01", "2026-06-02"],
            "spread": [11.11, 12.34],
        },
    }
    seen = {}

    def fake_collect():
        seen["collected"] = True
        return preview_payload

    def fake_generate(payload, output_dir):
        seen["payload"] = payload
        seen["output_dir"] = output_dir
        path = output_dir / "style_rotation_preview.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"png")
        return path

    monkeypatch.setattr(module.analysis, "collect_style_rotation_preview_payload", fake_collect)
    monkeypatch.setattr(module.chart, "generate_style_rotation_chart", fake_generate)

    result = module.collect_style_rotation_email_payloads(output_dir=tmp_path / "out")

    assert seen["collected"] is True
    assert seen["payload"] == preview_payload
    assert seen["output_dir"] == tmp_path / "out"
    assert result["payload"] == preview_payload
    assert result["as_of_label"] == "2026-06-02"
    assert result["chart_path"].name == "style_rotation_preview.png"


def test_write_preview_html_outputs_file(tmp_path: Path):
    html = "<html><body>preview</body></html>"

    output_path = module.write_preview_html(html, tmp_path)

    assert output_path == tmp_path / "preview_style_rotation_email.html"
    assert output_path.read_text(encoding="utf-8") == html


def test_preview_main_writes_html_with_inline_chart(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(module, "DEFAULT_OUTPUT_DIR", tmp_path / "out")

    chart_path = tmp_path / "out" / "style_rotation_preview.png"
    chart_path.parent.mkdir(parents=True, exist_ok=True)
    chart_path.write_bytes(b"png-preview")

    payloads = {
        "payload": {
            "meta": {
                "left_name": "国证小盘成长",
                "right_name": "国证大盘价值",
                "return_window_days": 250,
                "display_window_days": 252,
            },
            "series": {
                "dates": ["2026-06-02"],
                "spread": [58.81],
            },
        },
        "chart_path": chart_path,
        "as_of_label": "2026-06-02",
    }
    monkeypatch.setattr(module, "collect_style_rotation_email_payloads", lambda output_dir: payloads)

    exit_code = module.main()

    html = (tmp_path / "out" / "preview_style_rotation_email.html").read_text(encoding="utf-8")
    assert exit_code == 0
    assert "data:image/png;base64," in html
    assert "国证小盘成长" in html
    assert "国证大盘价值" in html
    assert "2026-06-02" in html
