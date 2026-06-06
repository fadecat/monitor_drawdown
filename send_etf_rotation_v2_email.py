from __future__ import annotations

import smtplib
from email.message import EmailMessage
from pathlib import Path
from typing import Any

import monitor_drawdown as md
import preview_etf_rotation_v2_email as preview


DEFAULT_OUTPUT_DIR = Path(".test_artifacts/etf_rotation_v2_email")


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
) -> EmailMessage:
    message = EmailMessage()
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    message["Subject"] = subject
    message.set_content(text)
    message.add_alternative(html, subtype="html")
    return message


def send_etf_rotation_v2_email(
    *,
    config: dict[str, Any],
    subject: str,
    text: str,
    html: str,
) -> None:
    message = build_etf_rotation_v2_email_message(
        sender=str(config["sender"]),
        recipients=list(config["recipients"]),
        subject=subject,
        text=text,
        html=html,
    )
    with smtplib.SMTP_SSL(str(config["smtp_host"]), int(config["smtp_port"]), timeout=15) as smtp:
        smtp.login(str(config["username"]), str(config["password"]))
        smtp.send_message(message)
    print(f"[INFO] ETF 轮动 V2 邮件发送成功，收件人: {', '.join(config['recipients'])}")


def persist_next_state(payloads: dict[str, Any], state_path: Path = preview.DEFAULT_STATE_PATH) -> None:
    next_state = payloads.get("next_state")
    if not isinstance(next_state, dict):
        return
    preview.write_email_state(state_path, next_state)


def main() -> int:
    config = load_etf_rotation_v2_email_config()
    payloads = collect_etf_rotation_v2_email_payloads(DEFAULT_OUTPUT_DIR)
    send_etf_rotation_v2_email(
        config=config,
        subject=str(payloads["subject"]),
        text=str(payloads["text"]),
        html=str(payloads["html"]),
    )
    persist_next_state(payloads)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
