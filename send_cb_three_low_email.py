"""可转债三低轮动 模拟盘邮件发送。"""
from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from html import escape
from pathlib import Path
from typing import Any, Dict, List, Optional

import cb_index_history
import cb_three_low as strategy
import cb_three_low_email_chart as email_chart


CONFIG_PATH = os.getenv("CB_THREE_LOW_CONFIG", "cb_three_low_config.yaml")
DEFAULT_OUTPUT_DIR = Path(".test_artifacts/cb_three_low")
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


def history_updated(prev: Optional[Dict[str, Any]], state: Dict[str, Any]) -> bool:
    """本次运行是否产生了新数据：历史变长（新交易日），或签名变化（当日记录被覆盖重算）。"""
    prev = prev or {}
    if len(state.get("holdings_history", [])) > len(prev.get("holdings_history", [])):
        return True
    return state.get("last_snapshot_signature") != prev.get("last_snapshot_signature")


def _fmt_pct(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value) * 100:.2f}%"
    except (TypeError, ValueError):
        return "-"


def _fmt_num(value: Any, digits: int = 2) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "-"


def _return_color(value: Any) -> str:
    """A 股配色：上涨红、下跌绿。"""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "#333"
    if v > 0:
        return "#d93025"
    if v < 0:
        return "#2E7D32"
    return "#333"


def load_benchmark_series() -> Optional[List[Dict[str, Any]]]:
    """拉取集思录可转债等权指数序列（[{date, value}]）。

    优先实时页面（含当日），失败时回退到仓库内已提交的历史文件。
    """
    try:
        series = cb_index_history.build_runtime_index_series()
        if series:
            return series
    except Exception as exc:  # noqa: BLE001
        print(f"[WARN] 集思录等权指数实时拉取失败，回退本地历史: {exc}")
    try:
        series = [
            {"date": str(r["date"])[:10], "value": float(r["index_value"])}
            for r in cb_index_history.load_history()
            if r.get("date") and r.get("index_value") not in (None, "")
        ]
        return series or None
    except Exception as exc:  # noqa: BLE001
        print(f"[WARN] 集思录等权指数本地历史读取失败: {exc}")
        return None


def build_email_text(report: Dict[str, Any]) -> str:
    lines = [
        "可转债三低轮动日报",
        f"信号日期: {report.get('as_of_date', '-')}",
        f"组合净值: {_fmt_num(report.get('current_nav'), 4)}",
        f"累计收益: {_fmt_pct(report.get('total_return'))}",
        f"等权指数同期: {_fmt_pct(report.get('benchmark_return'))}",
        f"超额收益: {_fmt_pct(report.get('excess_return'))}",
        f"最大回撤: {_fmt_pct(report.get('max_drawdown'))}",
        f"当前回撤: {_fmt_pct(report.get('current_drawdown'))}",
        f"持仓只数: {len(report.get('holdings', []))}",
        "",
        "次日持仓:",
    ]
    for h in report.get("holdings", []):
        lines.append(f"  {h['rank']}. {h['name']} ({h['code']}) 收盘 {_fmt_num(h.get('price'))}")
    lines.extend(["", "三低排名:"])
    for item in report.get("ranking", []):
        mark = " *" if item.get("selected") else ""
        lines.append(
            f"  {item['rank']}. {item['name']} ({item['code']}) "
            f"双低 {_fmt_num(item.get('dblow'))} 溢价 {_fmt_num(item.get('premium_rt'))}% "
            f"规模 {_fmt_num(item.get('curr_iss_amt'))}{mark}"
        )
    lines.extend(["", "历史净值(近 20 日):"])
    for entry in report.get("history", [])[-20:][::-1]:
        lines.append(
            f"  {entry['date']} 净值 {_fmt_num(entry.get('nav'), 4)} "
            f"日收益 {_fmt_pct(entry.get('daily_return'))} 持仓 {len(entry.get('holdings', []))} 只"
        )
    return "\n".join(lines)


def build_email_html(report: Dict[str, Any], chart_cid: str) -> str:
    as_of = escape(str(report.get("as_of_date", "-")))
    cur_nav = _fmt_num(report.get("current_nav"), 4)
    total_return = report.get("total_return")
    max_drawdown = report.get("max_drawdown")
    current_drawdown = report.get("current_drawdown")
    benchmark_return = report.get("benchmark_return")
    excess_return = report.get("excess_return")
    tr_color = _return_color(total_return)
    md_color = _return_color(max_drawdown)
    cd_color = _return_color(current_drawdown)
    br_color = _return_color(benchmark_return)
    er_color = _return_color(excess_return)
    generated = strategy.now_in_beijing().replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")

    # 次日持仓表
    holding_rows = []
    for h in report.get("holdings", []):
        holding_rows.append(
            f"<tr><td style='padding:4px 10px;text-align:right'>{escape(str(h.get('rank', '')))}</td>"
            f"<td style='padding:4px 10px'>{escape(str(h.get('name', '')))}</td>"
            f"<td style='padding:4px 10px'>{escape(str(h.get('code', '')))}</td>"
            f"<td style='padding:4px 10px;text-align:right'>{_fmt_num(h.get('price'))}</td></tr>"
        )
    holdings_html = "\n".join(holding_rows) if holding_rows else "<tr><td colspan='4'>无数据</td></tr>"

    # 三低排名表
    ranking_rows = []
    for item in report.get("ranking", []):
        bg = "background:#eef5ff" if item.get("selected") else ""
        ranking_rows.append(
            f"<tr style='{bg}'>"
            f"<td style='padding:4px 10px;text-align:right'>{escape(str(item.get('rank', '')))}</td>"
            f"<td style='padding:4px 10px'>{escape(str(item.get('name', '')))}</td>"
            f"<td style='padding:4px 10px'>{escape(str(item.get('code', '')))}</td>"
            f"<td style='padding:4px 10px;text-align:right'>{_fmt_num(item.get('price'))}</td>"
            f"<td style='padding:4px 10px;text-align:right'>{_fmt_num(item.get('dblow'))}</td>"
            f"<td style='padding:4px 10px;text-align:right'>{_fmt_num(item.get('premium_rt'))}%</td>"
            f"<td style='padding:4px 10px;text-align:right'>{_fmt_num(item.get('curr_iss_amt'))}</td>"
            f"<td style='padding:4px 10px;text-align:right'>{_fmt_num(item.get('total_score'), 1)}</td>"
            f"<td style='padding:4px 10px;text-align:center'>{'✓' if item.get('selected') else ''}</td></tr>"
        )
    ranking_html = "\n".join(ranking_rows) if ranking_rows else "<tr><td colspan='9'>无数据</td></tr>"

    # 历史净值表
    history_rows = []
    for entry in report.get("history", [])[-20:][::-1]:
        ret_color = _return_color(entry.get("daily_return"))
        history_rows.append(
            f"<tr><td style='padding:3px 10px'>{escape(str(entry.get('date', '')))}</td>"
            f"<td style='padding:3px 10px;text-align:right'>{_fmt_num(entry.get('nav'), 4)}</td>"
            f"<td style='padding:3px 10px;text-align:right;color:{ret_color}'>{_fmt_pct(entry.get('daily_return'))}</td>"
            f"<td style='padding:3px 10px;text-align:right'>{len(entry.get('holdings', []))}</td></tr>"
        )
    history_html = "\n".join(history_rows) if history_rows else "<tr><td colspan='4'>无历史</td></tr>"

    target_count = report.get("target_count", 10)

    return f"""\
<div style="font-family:-apple-system,'Segoe UI','Microsoft YaHei',Arial,sans-serif;color:#222;max-width:720px">
  <h2 style="margin:0 0 4px">📊 可转债三低轮动日报</h2>
  <div style="color:#888;font-size:12px">信号日期 {as_of} · 生成 {generated}</div>
  <table style="border-collapse:collapse;margin:14px 0;font-size:14px">
    <tr><td style="padding:4px 16px 4px 0;color:#888">组合净值</td>
        <td style="padding:4px 0">{cur_nav}</td></tr>
    <tr><td style="padding:4px 16px 4px 0;color:#888">累计收益</td>
        <td style="padding:4px 0;color:{tr_color}">{_fmt_pct(total_return)}</td></tr>
    <tr><td style="padding:4px 16px 4px 0;color:#888">等权指数同期</td>
        <td style="padding:4px 0;color:{br_color}">{_fmt_pct(benchmark_return)}</td></tr>
    <tr><td style="padding:4px 16px 4px 0;color:#888">超额收益</td>
        <td style="padding:4px 0;color:{er_color}">{_fmt_pct(excess_return)}</td></tr>
    <tr><td style="padding:4px 16px 4px 0;color:#888">最大回撤</td>
        <td style="padding:4px 0;color:{md_color}">{_fmt_pct(max_drawdown)}</td></tr>
    <tr><td style="padding:4px 16px 4px 0;color:#888">当前回撤</td>
        <td style="padding:4px 0;color:{cd_color}">{_fmt_pct(current_drawdown)}</td></tr>
    <tr><td style="padding:4px 16px 4px 0;color:#888">持仓只数</td>
        <td style="padding:4px 0">{len(report.get('holdings', []))} / {target_count} 等权</td></tr>
  </table>

  <h3 style="margin:18px 0 6px">次日持仓（{target_count} 只等权）</h3>
  <table style="border-collapse:collapse;font-size:13px;width:100%">
    <thead><tr style="background:#f4f6f8;color:#555">
      <th style="padding:6px 10px;text-align:right">排名</th>
      <th style="padding:6px 10px;text-align:left">名称</th>
      <th style="padding:6px 10px;text-align:left">代码</th>
      <th style="padding:6px 10px;text-align:right">收盘价</th>
    </tr></thead>
    <tbody>
{holdings_html}
    </tbody>
  </table>

  <h3 style="margin:18px 0 6px">三低排名（双低值 + 溢价率 + 剩余规模）</h3>
  <table style="border-collapse:collapse;font-size:12px;width:100%">
    <thead><tr style="background:#f4f6f8;color:#555">
      <th style="padding:6px 8px;text-align:right">排名</th>
      <th style="padding:6px 8px;text-align:left">名称</th>
      <th style="padding:6px 8px;text-align:left">代码</th>
      <th style="padding:6px 8px;text-align:right">收盘价</th>
      <th style="padding:6px 8px;text-align:right">双低</th>
      <th style="padding:6px 8px;text-align:right">溢价率</th>
      <th style="padding:6px 8px;text-align:right">规模(亿)</th>
      <th style="padding:6px 8px;text-align:right">得分</th>
      <th style="padding:6px 8px;text-align:center">选</th>
    </tr></thead>
    <tbody>
{ranking_html}
    </tbody>
  </table>

  <h3 style="margin:18px 0 6px">组合净值 vs 集思录等权指数</h3>
  <img src="cid:{chart_cid}" alt="nav chart" style="width:100%;max-width:640px;border:1px solid #e5e5e5;border-radius:6px" />

  <h3 style="margin:18px 0 6px">历史净值（近 20 日）</h3>
  <table style="border-collapse:collapse;font-size:12px;width:100%">
    <thead><tr style="background:#f4f6f8;color:#555">
      <th style="padding:5px 10px;text-align:left">日期</th>
      <th style="padding:5px 10px;text-align:right">净值</th>
      <th style="padding:5px 10px;text-align:right">日收益</th>
      <th style="padding:5px 10px;text-align:right">持仓数</th>
    </tr></thead>
    <tbody>
{history_html}
    </tbody>
  </table>
  <p style="color:#aaa;font-size:11px;margin-top:16px">
    规则：三低策略（双低值+溢价率+剩余规模综合评分）取前 {target_count} 只等权持仓，日频再平衡，容差保留已持有且仍在池内的转债。
    T 日净值用 T-1 收盘已决定的持仓更新（无未来函数）。模拟盘，不发真实委托。
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

    if not history_updated(prev, state):
        print(f"[INFO] 无新交易日（last_run_date={state.get('last_run_date')}），跳过邮件")
        return 0

    report = strategy.build_report(state, config)

    # 集思录等权指数基准对比 + 最大回撤区间
    benchmark_series = load_benchmark_series()
    aligned = (
        strategy.align_benchmark(report["history"], benchmark_series)
        if benchmark_series
        else []
    )
    comparison = strategy.compute_benchmark_comparison(report["history"], benchmark_series or [])
    report["benchmark_return"] = comparison["benchmark_return"]
    report["excess_return"] = comparison["excess_return"]
    drawdown = strategy.find_max_drawdown_window(
        report["history"], float(config["strategy"]["initial_nav"])
    )

    output_dir = Path(os.getenv("CB_THREE_LOW_OUTPUT", str(DEFAULT_OUTPUT_DIR)))
    chart_path = output_dir / "nav_chart.png"
    try:
        email_chart.generate_nav_chart(
            report["history"],
            chart_path,
            benchmark=aligned or None,
            drawdown=drawdown,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[WARN] 净值曲线生成失败: {exc}")
        chart_path = None

    subject = f"可转债三低轮动日报 {report.get('as_of_date', '')}"
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
