from __future__ import annotations

import smtplib
from email.message import EmailMessage
from pathlib import Path
from typing import Any

import monitor_drawdown as md
import preview_style_rotation_etf_email as preview


STYLE_ROTATION_ETF_EMAIL_SUBJECT = "ETF风格轮动收益率差值日报"
DEFAULT_OUTPUT_DIR = Path(".test_artifacts/style_rotation_etf_email")


def load_style_rotation_etf_email_config() -> dict[str, Any]:
    config = md.load_email_config_from_env()
    if config is None:
        raise RuntimeError("邮件配置不完整，需要 RECEIVER_EMAIL/SMTP_USER/SMTP_PASS")
    config["subject"] = STYLE_ROTATION_ETF_EMAIL_SUBJECT
    return config


def collect_style_rotation_etf_email_payloads(
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> dict[str, Any]:
    return preview.collect_style_rotation_etf_email_payloads(output_dir=output_dir)


def build_style_rotation_etf_email_message(
    *,
    sender: str,
    recipients: list[str],
    as_of_label: str,
    payload: dict[str, Any],
    chart_path: Path,
) -> EmailMessage:
    message = EmailMessage()
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    message["Subject"] = STYLE_ROTATION_ETF_EMAIL_SUBJECT
    message.set_content(
        "\n".join(
            [
                STYLE_ROTATION_ETF_EMAIL_SUBJECT,
                f"数据截至: {as_of_label}",
                "请在 HTML 邮件中查看 ETF 风格轮动收益率差值图。",
            ]
        )
    )
    html = preview.build_style_rotation_email_html(
        payload=payload,
        chart_cid="cid:style_rotation_etf_chart",
        as_of_label=as_of_label,
    )
    message.add_alternative(html, subtype="html")
    html_part = message.get_payload()[-1]
    html_part.add_related(
        chart_path.read_bytes(),
        maintype="image",
        subtype="png",
        cid="<style_rotation_etf_chart>",
    )
    return message


def send_style_rotation_etf_email(
    *,
    config: dict[str, Any],
    as_of_label: str,
    payload: dict[str, Any],
    chart_path: Path,
) -> None:
    message = build_style_rotation_etf_email_message(
        sender=str(config["sender"]),
        recipients=list(config["recipients"]),
        as_of_label=as_of_label,
        payload=payload,
        chart_path=chart_path,
    )
    with smtplib.SMTP_SSL(str(config["smtp_host"]), int(config["smtp_port"]), timeout=15) as smtp:
        smtp.login(str(config["username"]), str(config["password"]))
        smtp.send_message(message)
    print(f"[INFO] ETF 风格轮动日报发送成功，收件人: {', '.join(config['recipients'])}")


def main() -> int:
    config = load_style_rotation_etf_email_config()
    payloads = collect_style_rotation_etf_email_payloads()
    send_style_rotation_etf_email(
        config=config,
        as_of_label=str(payloads["as_of_label"]),
        payload=dict(payloads["payload"]),
        chart_path=Path(payloads["chart_path"]),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
