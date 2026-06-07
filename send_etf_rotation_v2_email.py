from __future__ import annotations

import json
import re
import shutil
import smtplib
from datetime import UTC, datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Any

import backtest_etf_rotation_v2_strategy as backtest
import etf_rotation_v2_email_chart as email_chart
import monitor_drawdown as md
import preview_etf_rotation_v2_email as preview


DEFAULT_OUTPUT_DIR = Path(".test_artifacts/etf_rotation_v2_email")
DEFAULT_ARCHIVE_ROOT = Path("data_state/etf_rotation_v2_email")


def load_etf_rotation_v2_email_config() -> dict[str, Any]:
    config = md.load_email_config_from_env()
    if config is None:
        raise RuntimeError("邮件配置不完整，需要 RECEIVER_EMAIL/SMTP_USER/SMTP_PASS")
    return config


def collect_etf_rotation_v2_email_payloads(
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> dict[str, Any]:
    return preview.collect_etf_rotation_v2_email_payloads(output_dir=output_dir)


def build_etf_rotation_v2_email_message(
    *,
    sender: str,
    recipients: list[str],
    subject: str,
    text: str,
    html: str,
    chart_path: Path | None = None,
    chart_cid: str = email_chart.BENCHMARK_CHART_CID,
) -> EmailMessage:
    message = EmailMessage()
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    message["Subject"] = subject
    message.set_content(text)
    message.add_alternative(html, subtype="html")
    if chart_path is not None and chart_path.exists():
        html_part = message.get_body(preferencelist=("html",))
        html_part.add_related(
            chart_path.read_bytes(),
            maintype="image",
            subtype="png",
            cid=f"<{chart_cid}>",
        )
    return message


def send_etf_rotation_v2_email(
    *,
    config: dict[str, Any],
    subject: str,
    text: str,
    html: str,
    chart_path: Path | None = None,
) -> None:
    message = build_etf_rotation_v2_email_message(
        sender=str(config["sender"]),
        recipients=list(config["recipients"]),
        subject=subject,
        text=text,
        html=html,
        chart_path=chart_path,
    )
    with smtplib.SMTP_SSL(str(config["smtp_host"]), int(config["smtp_port"]), timeout=15) as smtp:
        smtp.login(str(config["username"]), str(config["password"]))
        smtp.send_message(message)
    print(f"[INFO] ETF 轮动 V2 邮件发送成功，收件人: {', '.join(config['recipients'])}")


def build_send_html(payloads: dict[str, Any]) -> str:
    html = str(payloads.get("html") or "")
    chart_path = payloads.get("chart_path")
    if isinstance(chart_path, Path) and chart_path.exists():
        return re.sub(
            r"data:image/png;base64,[A-Za-z0-9+/=]+",
            f"cid:{email_chart.BENCHMARK_CHART_CID}",
            html,
            count=1,
        )
    return html


def persist_next_state(payloads: dict[str, Any], state_path: Path = preview.DEFAULT_STATE_PATH) -> None:
    next_state = payloads.get("next_state")
    if not isinstance(next_state, dict):
        return
    preview.write_email_state(state_path, next_state)


def _copy_tree_contents(source: Path, destination: Path) -> None:
    if not source.exists():
        return
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)


def _read_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def archive_run_artifacts(
    *,
    payloads: dict[str, Any],
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    archive_root: Path = DEFAULT_ARCHIVE_ROOT,
    state_path: Path = preview.DEFAULT_STATE_PATH,
) -> None:
    latest_dir = archive_root / "latest"
    if latest_dir.exists():
        shutil.rmtree(latest_dir)
    latest_dir.mkdir(parents=True, exist_ok=True)

    (latest_dir / "email_subject.txt").write_text(str(payloads.get("subject") or ""), encoding="utf-8")
    (latest_dir / "email_text.txt").write_text(str(payloads.get("text") or ""), encoding="utf-8")
    (latest_dir / "email_preview.html").write_text(str(payloads.get("html") or ""), encoding="utf-8")

    if state_path.exists():
        shutil.copy2(state_path, latest_dir / "state.json")
    elif isinstance(payloads.get("next_state"), dict):
        preview.write_email_state(latest_dir / "state.json", dict(payloads["next_state"]))

    _copy_tree_contents(output_dir / "rotation", latest_dir / "rotation")
    _copy_tree_contents(output_dir / "source", latest_dir / "source")

    backtest_output_root = output_dir / "backtest"
    if not (backtest_output_root / "daily_positions.csv").exists():
        backtest.run_backtest(
            source_output_root=output_dir / "source",
            output_root=backtest_output_root,
        )
    _copy_tree_contents(backtest_output_root, latest_dir / "backtest")
    _copy_tree_contents(output_dir / "benchmark", latest_dir / "benchmark")
    chart_path = payloads.get("chart_path")
    if isinstance(chart_path, Path) and chart_path.exists():
        shutil.copy2(chart_path, latest_dir / "email_chart.png")

    data_status = _read_json_file(output_dir / "rotation" / "data_status.json")
    manifest = {
        "generated_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "subject": str(payloads.get("subject") or ""),
        "signal_date": str(data_status.get("signal_date") or "unknown"),
        "rotation_status": str(data_status.get("status") or "unknown"),
        "all_targets_aligned": bool(data_status.get("all_targets_aligned")),
        "lagging_labels": data_status.get("lagging_labels") or [],
    }
    (latest_dir / "run_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> int:
    config = load_etf_rotation_v2_email_config()
    payloads = collect_etf_rotation_v2_email_payloads(DEFAULT_OUTPUT_DIR)
    chart_path = payloads.get("chart_path") if isinstance(payloads.get("chart_path"), Path) else None
    send_etf_rotation_v2_email(
        config=config,
        subject=str(payloads["subject"]),
        text=str(payloads["text"]),
        html=build_send_html(payloads),
        chart_path=chart_path,
    )
    persist_next_state(payloads)
    archive_run_artifacts(payloads=payloads, output_dir=DEFAULT_OUTPUT_DIR)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
