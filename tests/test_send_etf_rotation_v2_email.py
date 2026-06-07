from __future__ import annotations

import json
from email.message import EmailMessage
from pathlib import Path

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


def test_archive_run_artifacts_copies_email_rotation_state_and_backtest_outputs(
    monkeypatch,
    tmp_path: Path,
):
    output_dir = tmp_path / "runtime"
    rotation_dir = output_dir / "rotation"
    rotation_dir.mkdir(parents=True)
    (rotation_dir / "data_status.json").write_text('{"status": "ready"}', encoding="utf-8")
    (rotation_dir / "portfolio_decision.json").write_text('{"selected": "A"}', encoding="utf-8")
    source_dir = output_dir / "source" / "series"
    source_dir.mkdir(parents=True)
    (source_dir / "etf_510001.json").write_text('[{"date": "2026-06-05", "close": 1.0}]', encoding="utf-8")

    state_path = tmp_path / "state.json"
    state_path.write_text('{"last_holding_label": "A"}', encoding="utf-8")
    archive_root = tmp_path / "archive"
    seen = {}

    def fake_backtest(*, source_output_root, output_root):
        seen["source_output_root"] = source_output_root
        seen["output_root"] = output_root
        output_root.mkdir(parents=True)
        (output_root / "backtest_summary.md").write_text("summary", encoding="utf-8")
        (output_root / "daily_positions.csv").write_text("date,nav\n2026-06-05,1.0\n", encoding="utf-8")
        return {"summary": {"final_nav": 1.0}}

    monkeypatch.setattr(module.backtest, "run_backtest", fake_backtest)

    module.archive_run_artifacts(
        payloads={
            "subject": "【持仓不变】ETF轮动V2 | A | 信号日 2026-06-05",
            "text": "plain",
            "html": "<html>preview</html>",
            "next_state": {"last_holding_label": "A"},
        },
        output_dir=output_dir,
        archive_root=archive_root,
        state_path=state_path,
    )

    assert seen["source_output_root"] == output_dir / "source"
    assert seen["output_root"] == output_dir / "backtest"
    latest = archive_root / "latest"
    assert (latest / "email_subject.txt").read_text(encoding="utf-8").startswith("【持仓不变】")
    assert (latest / "email_preview.html").read_text(encoding="utf-8") == "<html>preview</html>"
    assert json.loads((latest / "state.json").read_text(encoding="utf-8")) == {
        "last_holding_label": "A"
    }
    assert (latest / "rotation" / "data_status.json").exists()
    assert (latest / "rotation" / "portfolio_decision.json").exists()
    assert (latest / "source" / "series" / "etf_510001.json").exists()
    assert (latest / "backtest" / "backtest_summary.md").read_text(encoding="utf-8") == "summary"
    assert (latest / "backtest" / "daily_positions.csv").exists()
    manifest = json.loads((latest / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["subject"].startswith("【持仓不变】")
    assert manifest["rotation_status"] == "ready"
    assert manifest["signal_date"] == "unknown"
    assert manifest["generated_at_utc"].endswith("Z")


def test_archive_run_artifacts_reuses_existing_backtest_outputs(monkeypatch, tmp_path: Path):
    output_dir = tmp_path / "runtime"
    rotation_dir = output_dir / "rotation"
    rotation_dir.mkdir(parents=True)
    (rotation_dir / "data_status.json").write_text('{"status": "ready"}', encoding="utf-8")
    (output_dir / "source").mkdir(parents=True)
    backtest_dir = output_dir / "backtest"
    backtest_dir.mkdir(parents=True)
    (backtest_dir / "daily_positions.csv").write_text(
        "date,strategy_nav\n2026-06-05,38.5\n",
        encoding="utf-8",
    )
    (backtest_dir / "backtest_summary.md").write_text("existing summary", encoding="utf-8")

    def fail_if_called(**kwargs):
        raise AssertionError("archive should reuse preview backtest outputs")

    monkeypatch.setattr(module.backtest, "run_backtest", fail_if_called)

    module.archive_run_artifacts(
        payloads={
            "subject": "【持仓不变】ETF轮动V2 | A | 信号日 2026-06-05",
            "text": "plain",
            "html": "<html>preview</html>",
            "next_state": {"last_holding_label": "A"},
        },
        output_dir=output_dir,
        archive_root=tmp_path / "archive",
        state_path=tmp_path / "missing_state.json",
    )

    latest = tmp_path / "archive" / "latest"
    assert (latest / "backtest" / "daily_positions.csv").read_text(encoding="utf-8") == (
        "date,strategy_nav\n2026-06-05,38.5\n"
    )
    assert (latest / "backtest" / "backtest_summary.md").read_text(encoding="utf-8") == (
        "existing summary"
    )
