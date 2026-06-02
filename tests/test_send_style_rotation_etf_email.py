from email.message import EmailMessage
from pathlib import Path

import pytest

import send_style_rotation_etf_email as module


def test_build_style_rotation_etf_email_message_uses_fixed_subject(tmp_path: Path):
    chart_path = tmp_path / "chart.png"
    chart_path.write_bytes(b"png")
    payload = {
        "meta": {
            "left_name": "成长ETF易方达",
            "right_name": "价值ETF易方达",
            "return_window_days": 40,
            "display_window_days": 180,
        },
        "series": {
            "dates": ["2026-06-02"],
            "spread": [12.34],
        },
    }

    message = module.build_style_rotation_etf_email_message(
        sender="sender@qq.com",
        recipients=["alice@example.com"],
        as_of_label="2026-06-02",
        payload=payload,
        chart_path=chart_path,
    )

    assert isinstance(message, EmailMessage)
    assert message["Subject"] == module.STYLE_ROTATION_ETF_EMAIL_SUBJECT


def test_collect_style_rotation_etf_email_payloads_uses_preview_pipeline(monkeypatch, tmp_path: Path):
    expected = {
        "payload": {"meta": {}, "series": {"dates": ["2026-06-02"], "spread": [12.34]}},
        "chart_path": tmp_path / "out" / "style_rotation_etf_preview.png",
        "as_of_label": "2026-06-02",
    }

    monkeypatch.setattr(
        module.preview,
        "collect_style_rotation_etf_email_payloads",
        lambda output_dir: expected,
    )

    result = module.collect_style_rotation_etf_email_payloads(output_dir=tmp_path / "out")

    assert result == expected


def test_load_style_rotation_etf_email_config_raises_when_email_env_missing(monkeypatch):
    monkeypatch.delenv("RECEIVER_EMAIL", raising=False)
    monkeypatch.delenv("EMAIL_TO", raising=False)
    monkeypatch.delenv("SMTP_USER", raising=False)
    monkeypatch.delenv("EMAIL_USER", raising=False)
    monkeypatch.delenv("SMTP_PASS", raising=False)
    monkeypatch.delenv("EMAIL_PASSWORD", raising=False)

    with pytest.raises(RuntimeError, match="邮件配置不完整"):
        module.load_style_rotation_etf_email_config()
