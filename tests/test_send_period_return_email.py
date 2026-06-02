from email.message import EmailMessage
from pathlib import Path

import pytest

import send_period_return_email as module


def test_build_period_return_email_message_uses_fixed_subject(tmp_path: Path):
    chart_path = tmp_path / "chart.png"
    chart_path.write_bytes(b"png")
    table_rows = [
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

    message = module.build_period_return_email_message(
        sender="sender@qq.com",
        recipients=["alice@example.com"],
        as_of_label="2026-05-29",
        table_rows=table_rows,
        chart_path=chart_path,
    )

    assert isinstance(message, EmailMessage)
    assert message["Subject"] == module.PERIOD_RETURN_EMAIL_SUBJECT
    html_part = message.get_body(preferencelist=("html",))
    html = html_part.get_content()
    assert "近1月收益率走势图" in html
    assert "区间收益率表格" in html
    assert "cid:period_return_chart" in html


def test_build_period_return_email_message_attaches_png(tmp_path: Path):
    chart_path = tmp_path / "chart.png"
    chart_path.write_bytes(b"png-bytes")

    message = module.build_period_return_email_message(
        sender="sender@qq.com",
        recipients=["alice@example.com"],
        as_of_label="2026-05-29",
        table_rows=[],
        chart_path=chart_path,
    )

    html_part = message.get_payload()[-1]
    related_parts = html_part.get_payload()
    assert any(part.get_content_type() == "image/png" for part in related_parts)


def test_load_period_return_email_config_raises_when_email_env_missing(monkeypatch):
    monkeypatch.delenv("RECEIVER_EMAIL", raising=False)
    monkeypatch.delenv("EMAIL_TO", raising=False)
    monkeypatch.delenv("SMTP_USER", raising=False)
    monkeypatch.delenv("EMAIL_USER", raising=False)
    monkeypatch.delenv("SMTP_PASS", raising=False)
    monkeypatch.delenv("EMAIL_PASSWORD", raising=False)

    with pytest.raises(RuntimeError, match="邮件配置不完整"):
        module.load_period_return_email_config()


def test_send_period_return_email_uses_smtp_ssl(monkeypatch, tmp_path: Path):
    chart_path = tmp_path / "chart.png"
    chart_path.write_bytes(b"png")
    table_rows = []
    sent = {}

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

    module.send_period_return_email(
        config=config,
        as_of_label="2026-05-29",
        table_rows=table_rows,
        chart_path=chart_path,
    )

    assert sent["host"] == "smtp.qq.com"
    assert sent["port"] == 465
    assert sent["username"] == "sender@qq.com"
    assert sent["password"] == "auth-code"
    assert sent["message"]["Subject"] == module.PERIOD_RETURN_EMAIL_SUBJECT
