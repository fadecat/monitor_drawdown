from email.message import EmailMessage
from pathlib import Path

import pytest

import send_style_rotation_email as module


def test_build_style_rotation_email_message_uses_fixed_subject(tmp_path: Path):
    chart_path = tmp_path / "chart.png"
    chart_path.write_bytes(b"png")
    payload = {
        "meta": {
            "left_name": "国证小盘成长",
            "right_name": "国证大盘价值",
            "return_window_days": 250,
            "display_window_days": 252,
        },
        "series": {
            "dates": ["2026-06-02"],
            "spread": [12.34],
        },
    }

    message = module.build_style_rotation_email_message(
        sender="sender@qq.com",
        recipients=["alice@example.com"],
        as_of_label="2026-06-02",
        payload=payload,
        chart_path=chart_path,
    )

    assert isinstance(message, EmailMessage)
    assert message["Subject"] == module.STYLE_ROTATION_EMAIL_SUBJECT
    html_part = message.get_body(preferencelist=("html",))
    html = html_part.get_content()
    assert "风格轮动收益率差值预览" in html
    assert "国证小盘成长" in html
    assert "国证大盘价值" in html
    assert "cid:style_rotation_chart" in html


def test_build_style_rotation_email_message_attaches_png(tmp_path: Path):
    chart_path = tmp_path / "chart.png"
    chart_path.write_bytes(b"png-bytes")
    payload = {
        "meta": {
            "left_name": "国证小盘成长",
            "right_name": "国证大盘价值",
            "return_window_days": 250,
            "display_window_days": 252,
        },
        "series": {
            "dates": ["2026-06-02"],
            "spread": [12.34],
        },
    }

    message = module.build_style_rotation_email_message(
        sender="sender@qq.com",
        recipients=["alice@example.com"],
        as_of_label="2026-06-02",
        payload=payload,
        chart_path=chart_path,
    )

    html_part = message.get_payload()[-1]
    related_parts = html_part.get_payload()
    assert any(part.get_content_type() == "image/png" for part in related_parts)


def test_load_style_rotation_email_config_raises_when_email_env_missing(monkeypatch):
    monkeypatch.delenv("RECEIVER_EMAIL", raising=False)
    monkeypatch.delenv("EMAIL_TO", raising=False)
    monkeypatch.delenv("SMTP_USER", raising=False)
    monkeypatch.delenv("EMAIL_USER", raising=False)
    monkeypatch.delenv("SMTP_PASS", raising=False)
    monkeypatch.delenv("EMAIL_PASSWORD", raising=False)

    with pytest.raises(RuntimeError, match="邮件配置不完整"):
        module.load_style_rotation_email_config()


def test_send_style_rotation_email_uses_smtp_ssl(monkeypatch, tmp_path: Path):
    chart_path = tmp_path / "chart.png"
    chart_path.write_bytes(b"png")
    sent = {}
    payload = {
        "meta": {
            "left_name": "国证小盘成长",
            "right_name": "国证大盘价值",
            "return_window_days": 250,
            "display_window_days": 252,
        },
        "series": {
            "dates": ["2026-06-02"],
            "spread": [12.34],
        },
    }

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            sent["host"] = host
            sent["port"] = port
            sent["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def login(self, username, password):
            sent["username"] = username
            sent["password"] = password

        def send_message(self, message):
            sent["message"] = message

    monkeypatch.setattr(module.smtplib, "SMTP_SSL", FakeSMTP)

    config = {
        "smtp_host": "smtp.qq.com",
        "smtp_port": 465,
        "username": "sender@qq.com",
        "password": "auth-code",
        "sender": "sender@qq.com",
        "recipients": ["alice@example.com"],
        "subject": "will-be-overridden",
    }

    module.send_style_rotation_email(
        config=config,
        as_of_label="2026-06-02",
        payload=payload,
        chart_path=chart_path,
    )

    assert sent["host"] == "smtp.qq.com"
    assert sent["port"] == 465
    assert sent["username"] == "sender@qq.com"
    assert sent["password"] == "auth-code"
    assert sent["message"]["Subject"] == module.STYLE_ROTATION_EMAIL_SUBJECT


def test_collect_style_rotation_email_payloads_uses_preview_pipeline(monkeypatch, tmp_path: Path):
    expected = {
        "payload": {"meta": {}, "series": {"dates": ["2026-06-02"], "spread": [12.34]}},
        "chart_path": tmp_path / "out" / "style_rotation_preview.png",
        "as_of_label": "2026-06-02",
    }

    monkeypatch.setattr(
        module.preview,
        "collect_style_rotation_email_payloads",
        lambda output_dir: expected,
    )

    result = module.collect_style_rotation_email_payloads(output_dir=tmp_path / "out")

    assert result == expected
