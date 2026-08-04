"""ETF 20 日轮动策略邮件发送。"""
from __future__ import annotations

import os
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from html import escape
from pathlib import Path
from typing import Any, Dict

import etf_rotation_20d as strategy
import etf_rotation_20d_email_chart as email_chart


CONFIG_PATH = os.getenv("ETF_ROTATION_20D_CONFIG", "etf_rotation_20d_config.yaml")
DEFAULT_OUTPUT_DIR = Path(".test_artifacts/etf_rotation_20d")
DEFAULT_SMTP_HOST = "smtp.qq.com"
DEFAULT_SMTP_PORT = 465


def load_email_config() -> Dict[str, Any]:
    recipients_raw = os.getenv("RECEIVER_EMAIL", "") or os.getenv("EMAIL_TO", "")
    recipients = [r.strip() for r in recipients_raw.replace(";", ",").split(",") if r.strip()]
    username = (os.getenv("SMTP_USER", "") or os.getenv("EMAIL_USER", "")).strip()
    password = (os.getenv("SMTP_PASS", "") or os.getenv("EMAIL_PASSWORD", "")).strip()
    if not recipients or not username or not password:
        raise RuntimeError("邮件配置不完整，需要 RECEIVER_EMAIL/SMTP_USER/SMTP_PASS")
    return {
        "smtp_host": os.getenv("EMAIL_SMTP_HOST", DEFAULT_SMTP_HOST).strip() or DEFAULT_SMTP_HOST,
        "smtp_port": int(os.getenv("EMAIL_SMTP_PORT", str(DEFAULT_SMTP_PORT))),
        "username": username,
        "password": password,
        "sender": os.getenv("EMAIL_FROM", username).strip() or username,
        "recipients": recipients,
    }


def _fmt_pct(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value) * 100:.2f}%"
    except (TypeError, ValueError):
        return "-"


def _fmt_nav(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.4f}"
    except (TypeError, ValueError):
        return "-"


def build_email_text(report: Dict[str, Any]) -> str:
    lines = [
        "20 日涨幅 ETF 轮动日报",
        f"信号日期: {report.get('as_of_date', '-')}",
        f"当日持仓: {report.get('current_holding_name', '-')} ({report.get('current_holding', '-')})",
        f"组合净值: {_fmt_nav(report.get('current_nav'))}",
        f"次日持仓: {report.get('next_holding_name', '-')} ({report.get('next_holding', '-')})",
        "",
        "20 日涨幅排名:",
    ]
    for item in report.get("ranking", []):
        lines.append(f"  {item['name']} ({item['code']}): {_fmt_pct(item['return_20d'])}")
    lines.extend(["", "历史持仓(近 20 日):"])
    for entry in report.get("history", [])[-20:]:
        lines.append(
            f"  {entry['date']} 持有 {entry['holding']} 净值 {_fmt_nav(entry.get('nav'))} "
            f"日收益 {_fmt_pct(entry.get('daily_return'))}"
        )
    return "\n".join(lines)


def build_email_html(report: Dict[str, Any], chart_cid: str) -> str:
    as_of = escape(str(report.get("as_of_date", "-")))
    cur_name = escape(str(report.get("current_holding_name", "-")))
    cur_code = escape(str(report.get("current_holding", "-")))
    next_name = escape(str(report.get("next_holding_name", "-")))
    next_code = escape(str(report.get("next_holding", "-")))
    cur_nav = _fmt_nav(report.get("current_nav"))

    next_code_raw = str(report.get("next_holding", ""))
    is_fallback = next_code_raw == report.get("fallback_code")

    ranking_rows = []
    for item in report.get("ranking", []):
        is_top = item is report.get("ranking", [None])[0] and item.get("return_20d", 0) > 0
        color = "#2E7D32" if is_top else "#333"
        weight = "bold" if is_top else "normal"
        ranking_rows.append(
            f"<tr><td style='padding:4px 10px'>{escape(item['name'])}</td>"
            f"<td style='padding:4px 10px'>{escape(item['code'])}</td>"
            f"<td style='padding:4px 10px;color:{color};font-weight:{weight};text-align:right'>"
            f"{_fmt_pct(item['return_20d'])}</td></tr>"
        )
    ranking_html = "\n".join(ranking_rows) if ranking_rows else "<tr><td colspan='3'>无数据</td></tr>"

    history_rows = []
    for entry in report.get("history", [])[-20:]:
        history_rows.append(
            f"<tr><td style='padding:3px 10px'>{escape(str(entry['date']))}</td>"
            f"<td style='padding:3px 10px'>{escape(str(entry['holding']))}</td>"
            f"<td style='padding:3px 10px;text-align:right'>{_fmt_nav(entry.get('nav'))}</td>"
            f"<td style='padding:3px 10px;text-align:right'>{_fmt_pct(entry.get('daily_return'))}</td></tr>"
        )
    history_html = "\n".join(history_rows) if history_rows else "<tr><td colspan='4'>无历史</td></tr>"

    next_badge = "（空仓防御）" if is_fallback else ""
    generated = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    return f"""\
<div style="font-family:-apple-system,'Segoe UI','Microsoft YaHei',Arial,sans-serif;color:#222;max-width:680px">
  <h2 style="margin:0 0 4px">📊 20 日涨幅 ETF 轮动日报</h2>
  <div style="color:#888;font-size:12px">信号日期 {as_of} · 生成 {generated}</div>
  <table style="border-collapse:collapse;margin:14px 0;font-size:14px">
    <tr><td style="padding:4px 16px 4px 0;color:#888">次日持仓</td>
        <td style="padding:4px 0"><b style="color:#2c7be5">{next_name}</b> ({next_code}){next_badge}</td></tr>
    <tr><td style="padding:4px 16px 4px 0;color:#888">当日持仓</td>
        <td style="padding:4px 0">{cur_name} ({cur_code})</td></tr>
    <tr><td style="padding:4px 16px 4px 0;color:#888">组合净值</td>
        <td style="padding:4px 0">{cur_nav}</td></tr>
  </table>

  <h3 style="margin:18px 0 6px">20 日涨幅排名</h3>
  <table style="border-collapse:collapse;font-size:13px;width:100%">
    <thead><tr style="background:#f4f6f8;color:#555">
      <th style="padding:6px 10px;text-align:left">名称</th>
      <th style="padding:6px 10px;text-align:left">代码</th>
      <th style="padding:6px 10px;text-align:right">20 日涨幅</th>
    </tr></thead>
    <tbody>
{ranking_html}
    </tbody>
  </table>

  <h3 style="margin:18px 0 6px">组合净值曲线</h3>
  <img src="cid:{chart_cid}" alt="nav chart" style="width:100%;max-width:640px;border:1px solid #e5e5e5;border-radius:6px" />

  <h3 style="margin:18px 0 6px">历史持仓（近 20 日）</h3>
  <table style="border-collapse:collapse;font-size:12px;width:100%">
    <thead><tr style="background:#f4f6f8;color:#555">
      <th style="padding:5px 10px;text-align:left">日期</th>
      <th style="padding:5px 10px;text-align:left">持仓</th>
      <th style="padding:5px 10px;text-align:right">净值</th>
      <th style="padding:5px 10px;text-align:right">日收益</th>
    </tr></thead>
    <tbody>
{history_html}
    </tbody>
  </table>
  <p style="color:#aaa;font-size:11px;margin-top:16px">
    规则：20 日涨幅（收盘价）&gt; 0 中取最大者为次日持仓；全 ≤ 0 时空仓持有 {escape(str(report.get('fallback_name', '')))}。
    T 日净值用 T-1 收盘已决定的持仓更新（无未来函数）。
  </p>
</div>
"""


def build_message(
    *,
    sender: str,
    recipients: list,
    subject: str,
    text: str,
    html: str,
    chart_path: Path | None = None,
    chart_cid: str = email_chart.NAV_CHART_CID,
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


def main() -> int:
    config = strategy.load_strategy_config(CONFIG_PATH)
    state_path = config["state_path"]

    prev = strategy.load_state(state_path)
    state = strategy.run_strategy(CONFIG_PATH, state_path)
    if state is None:
        print("[WARN] 策略无数据，退出")
        return 1

    prev_count = len((prev or {}).get("holdings_history", []))
    updated = len(state.get("holdings_history", [])) > prev_count
    if not updated:
        print(f"[INFO] 无新交易日（last_run_date={state.get('last_run_date')}），跳过邮件")
        return 0

    report = strategy.build_report(state, config)

    output_dir = Path(os.getenv("ETF_ROTATION_20D_OUTPUT", str(DEFAULT_OUTPUT_DIR)))
    chart_path = output_dir / "nav_chart.png"
    try:
        email_chart.generate_nav_chart(report["history"], chart_path)
    except Exception as exc:  # noqa: BLE001
        print(f"[WARN] 净值曲线生成失败: {exc}")
        chart_path = None

    subject = f"ETF 20 日轮动日报 {report.get('as_of_date', '')}"
    text = build_email_text(report)
    html = build_email_html(report, email_chart.NAV_CHART_CID)

    email_config = load_email_config()
    message = build_message(
        sender=email_config["sender"],
        recipients=email_config["recipients"],
        subject=subject,
        text=text,
        html=html,
        chart_path=chart_path,
    )
    with smtplib.SMTP_SSL(email_config["smtp_host"], int(email_config["smtp_port"]), timeout=15) as smtp:
        smtp.login(email_config["username"], email_config["password"])
        smtp.send_message(message)
    print(f"[INFO] 邮件发送成功，收件人: {', '.join(email_config['recipients'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
