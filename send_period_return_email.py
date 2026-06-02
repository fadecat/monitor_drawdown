from __future__ import annotations

import smtplib
from email.message import EmailMessage
from pathlib import Path
from typing import Any

import analyze_etf_com_cn_period_returns as analysis
import monitor_drawdown as md
import preview_period_return_email as preview
import prototype_period_return_chart as chart


PERIOD_RETURN_EMAIL_SUBJECT = "跨品种ETF区间收益日报"
DEFAULT_CONFIG_PATH = Path("period_return_email_config.yaml")
DEFAULT_OUTPUT_DIR = Path(".test_artifacts/period_return_email")


def load_period_return_email_config() -> dict[str, Any]:
    config = md.load_email_config_from_env()
    if config is None:
        raise RuntimeError("邮件配置不完整，需要 RECEIVER_EMAIL/SMTP_USER/SMTP_PASS")
    config["subject"] = PERIOD_RETURN_EMAIL_SUBJECT
    return config


def collect_period_return_email_payloads(
    config_path: Path = DEFAULT_CONFIG_PATH,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> dict[str, Any]:
    payloads = analysis.collect_period_return_payloads(
        config_path=config_path,
        output_dir=output_dir,
    )
    table_rows = payloads["table_rows"]
    curve_payloads = payloads["curve_payloads"]

    chart_path = chart.generate_one_month_return_chart(
        table_rows,
        curve_payloads,
        output_dir=output_dir,
    )
    return {
        "table_rows": table_rows,
        "chart_path": chart_path,
        "as_of_label": payloads["as_of_label"],
    }


def build_period_return_email_message(
    *,
    sender: str,
    recipients: list[str],
    as_of_label: str,
    table_rows: list[dict[str, str]],
    chart_path: Path,
) -> EmailMessage:
    message = EmailMessage()
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    message["Subject"] = PERIOD_RETURN_EMAIL_SUBJECT
    message.set_content(
        "\n".join(
            [
                PERIOD_RETURN_EMAIL_SUBJECT,
                f"数据截至: {as_of_label}",
                "请在 HTML 邮件中查看近1月收益率图和区间收益率表格。",
            ]
        )
    )
    html = preview.build_period_return_email_html(
        table_rows=table_rows,
        chart_data_uri="cid:period_return_chart",
        as_of_label=as_of_label,
    )
    message.add_alternative(html, subtype="html")

    html_part = message.get_payload()[-1]
    html_part.add_related(
        chart_path.read_bytes(),
        maintype="image",
        subtype="png",
        cid="<period_return_chart>",
    )
    return message


def send_period_return_email(
    *,
    config: dict[str, Any],
    as_of_label: str,
    table_rows: list[dict[str, str]],
    chart_path: Path,
) -> None:
    message = build_period_return_email_message(
        sender=str(config["sender"]),
        recipients=list(config["recipients"]),
        as_of_label=as_of_label,
        table_rows=table_rows,
        chart_path=chart_path,
    )
    with smtplib.SMTP_SSL(str(config["smtp_host"]), int(config["smtp_port"]), timeout=15) as smtp:
        smtp.login(str(config["username"]), str(config["password"]))
        smtp.send_message(message)
    print(f"[INFO] 收益率日报发送成功，收件人: {', '.join(config['recipients'])}")


def main() -> int:
    config = load_period_return_email_config()
    payloads = collect_period_return_email_payloads()
    send_period_return_email(
        config=config,
        as_of_label=str(payloads["as_of_label"]),
        table_rows=list(payloads["table_rows"]),
        chart_path=Path(payloads["chart_path"]),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
