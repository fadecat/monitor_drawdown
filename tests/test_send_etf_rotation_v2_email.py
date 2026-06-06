from __future__ import annotations

from email.message import EmailMessage

import pytest

import send_etf_rotation_v2_email as module


def test_build_etf_rotation_v2_email_message_uses_dynamic_subject():
    message = module.build_etf_rotation_v2_email_message(
        sender="sender@qq.com",
        recipients=["alice@example.com"],
        subject="【持仓不变】ETF轮动V2 | 黄金ETF易方达 | 信号日 2026-06-05",
        text="plain text",
        html="<html><body>html</body></html>",
    )

    assert isinstance(message, EmailMessage)
    assert message["Subject"] == "【持仓不变】ETF轮动V2 | 黄金ETF易方达 | 信号日 2026-06-05"
    assert message.get_body(preferencelist=("plain",)).get_content().strip() == "plain text"
    assert "html" in message.get_body(preferencelist=("html",)).get_content()


def test_collect_etf_rotation_v2_email_payloads_uses_preview_pipeline(monkeypatch):
    expected = {
        "subject": "【数据未齐】ETF轮动V2 | 沿用上一信号 | 信号日 2026-06-05",
        "text": "text",
        "html": "<html>html</html>",
    }

    monkeypatch.setattr(
        module.preview,
        "collect_etf_rotation_v2_email_payloads",
        lambda output_dir: expected,
    )

    assert module.collect_etf_rotation_v2_email_payloads() == expected


def test_load_etf_rotation_v2_email_config_raises_when_email_env_missing(monkeypatch):
    monkeypatch.delenv("RECEIVER_EMAIL", raising=False)
    monkeypatch.delenv("EMAIL_TO", raising=False)
    monkeypatch.delenv("SMTP_USER", raising=False)
    monkeypatch.delenv("EMAIL_USER", raising=False)
    monkeypatch.delenv("SMTP_PASS", raising=False)
    monkeypatch.delenv("EMAIL_PASSWORD", raising=False)

    with pytest.raises(RuntimeError, match="邮件配置不完整"):
        module.load_etf_rotation_v2_email_config()


def test_persist_next_state_writes_only_when_next_state_exists(tmp_path):
    state_path = tmp_path / "state.json"

    module.persist_next_state(
        {"next_state": {"last_signal_date": "2026-06-05", "last_holding_label": "黄金ETF易方达"}},
        state_path,
    )

    assert "黄金ETF易方达" in state_path.read_text(encoding="utf-8")

    module.persist_next_state({"next_state": None}, state_path)

    assert "黄金ETF易方达" in state_path.read_text(encoding="utf-8")
