from __future__ import annotations

from html import escape
import json
from pathlib import Path
from typing import Any

import run_etf_rotation_v2_strategy as runner


DEFAULT_OUTPUT_DIR = Path(".test_artifacts/etf_rotation_v2_email")
DEFAULT_STATE_PATH = Path("data_state/etf_rotation_v2_email.json")


def _selected_holding(rotation_result: dict[str, Any]) -> dict[str, Any]:
    holdings = rotation_result.get("portfolio_decision", {}).get("selected_holdings") or []
    if not holdings:
        return {}
    first = holdings[0]
    return first if isinstance(first, dict) else {}


def _signal_date(rotation_result: dict[str, Any]) -> str:
    return str(rotation_result.get("data_status", {}).get("signal_date") or "unknown")


def _selected_label(rotation_result: dict[str, Any]) -> str:
    return str(_selected_holding(rotation_result).get("label") or "未选择")


def _is_data_ready(rotation_result: dict[str, Any]) -> bool:
    data_status = rotation_result.get("data_status") or {}
    return data_status.get("status") == "ready"


def _data_status_label(data_status: dict[str, Any]) -> str:
    if data_status.get("status") != "ready":
        return "数据不可用"
    if data_status.get("all_targets_aligned"):
        return "全部齐备"
    return "数据日期不一致，已回退统一信号日"


def build_email_subject(
    rotation_result: dict[str, Any],
    previous_holding_label: str | None = None,
) -> str:
    signal_date = _signal_date(rotation_result)
    selected_label = _selected_label(rotation_result)
    decision = rotation_result.get("portfolio_decision") or {}

    if not _is_data_ready(rotation_result):
        return f"【数据不可用】ETF轮动V2 | 沿用上一信号 | 信号日 {signal_date}"
    if decision.get("selection_reason") == "fallback_defensive_asset":
        return f"【切入防守】ETF轮动V2 | → {selected_label} | 信号日 {signal_date}"
    if previous_holding_label and previous_holding_label == selected_label:
        return f"【持仓不变】ETF轮动V2 | {selected_label} | 信号日 {signal_date}"
    if previous_holding_label and previous_holding_label != selected_label:
        return f"【换仓通知】ETF轮动V2 | {previous_holding_label} → {selected_label} | 信号日 {signal_date}"
    return f"【今日信号】ETF轮动V2 | {selected_label} | 信号日 {signal_date}"


def _format_number(value: Any, digits: int = 3) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "--"


def _format_pct(value: Any, digits: int = 1) -> str:
    try:
        return f"{float(value) * 100:+.{digits}f}%"
    except (TypeError, ValueError):
        return "--"


def _build_decision_summary(
    rotation_result: dict[str, Any],
    previous_holding_label: str | None,
) -> list[str]:
    selected = _selected_holding(rotation_result)
    selected_label = str(selected.get("label") or "未选择")
    selected_symbol = str(selected.get("symbol") or "").strip()
    data_status = rotation_result.get("data_status") or {}
    reason = str(rotation_result.get("portfolio_decision", {}).get("selection_reason") or "")
    if not _is_data_ready(rotation_result):
        action = "数据不可用，沿用上一有效信号"
        holding_text = previous_holding_label or "未知"
        return [
            f"今日结论：{action}",
            f"当前有效持仓：{holding_text}",
            f"信号日：{data_status.get('signal_date') or 'unknown'}",
            f"数据状态：{_data_status_label(data_status)}",
        ]
    elif reason == "fallback_defensive_asset":
        action = "切入防守"
    elif previous_holding_label and previous_holding_label == selected_label:
        action = "持仓不变"
    elif previous_holding_label and previous_holding_label != selected_label:
        action = f"换仓：{previous_holding_label} → {selected_label}"
    else:
        action = "今日信号"

    holding_text = selected_label if not selected_symbol else f"{selected_label}（{selected_symbol}）"
    return [
        f"今日结论：{action}",
        f"当前信号持仓：{holding_text}",
        f"信号日：{data_status.get('signal_date') or 'unknown'}",
        f"数据状态：{_data_status_label(data_status)}",
    ]


def _build_data_status_html(data_status: dict[str, Any]) -> str:
    rows = []
    latest_dates = data_status.get("latest_dates_by_label") or {}
    for label, latest_date in latest_dates.items():
        rows.append(
            "<tr>"
            f"<td>{escape(str(label))}</td>"
            f"<td>{escape(str(latest_date))}</td>"
            "</tr>"
        )
    lagging_labels = ", ".join(str(item) for item in data_status.get("lagging_labels") or []) or "无"
    return (
        "<h2>数据状态</h2>"
        f"<p>状态：{escape(_data_status_label(data_status))}</p>"
        f"<p>统一信号日：<strong>{escape(str(data_status.get('signal_date') or 'unknown'))}</strong></p>"
        f"<p>滞后标的：{escape(lagging_labels)}</p>"
        "<table><thead><tr><th>标的</th><th>最新数据日期</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def _build_candidate_table_html(rotation_result: dict[str, Any]) -> str:
    ranked_labels = [
        str(item.get("label") or "")
        for item in rotation_result.get("ranked_candidates") or []
        if isinstance(item, dict)
    ]
    rank_by_label = {label: index + 1 for index, label in enumerate(ranked_labels)}
    rows = []
    for candidate in rotation_result.get("candidate_metrics") or []:
        if not isinstance(candidate, dict):
            continue
        label = str(candidate.get("label") or "")
        qualified = bool(candidate.get("qualified"))
        status = "合格" if qualified else str(candidate.get("rejection_reason") or "不合格")
        rank = rank_by_label.get(label, "--")
        rows.append(
            "<tr>"
            f"<td>{rank}</td>"
            f"<td>{escape(label)}</td>"
            f"<td>{escape(str(candidate.get('data_date') or '--'))}</td>"
            f"<td>{_format_number(candidate.get('score_25'))}</td>"
            f"<td>{_format_pct(candidate.get('annualized_return_25'))}</td>"
            f"<td>{_format_number(candidate.get('r_squared_25'))}</td>"
            f"<td>{_format_pct(candidate.get('return_10d'))}</td>"
            f"<td>{escape(status)}</td>"
            "</tr>"
        )
    return (
        "<h2>候选池评分</h2>"
        "<table><thead><tr>"
        "<th>排名</th><th>标的</th><th>数据日期</th><th>score_25</th>"
        "<th>年化收益</th><th>R²</th><th>10日收益</th><th>状态</th>"
        "</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def build_ascii_equity_curve(equity_curve: list[dict[str, Any]] | None, width: int = 42) -> str:
    if not equity_curve:
        return "暂无净值数据"
    values: list[float] = []
    for row in equity_curve[-60:]:
        try:
            values.append(float(row.get("strategy_nav")))
        except (TypeError, ValueError):
            continue
    if not values:
        return "暂无净值数据"
    if len(values) > width:
        step = max(len(values) / width, 1)
        values = [values[int(index * step)] for index in range(width)]
    low = min(values)
    high = max(values)
    span = high - low
    chars = "▁▂▃▄▅▆▇█"
    line = "".join(
        chars[0] if span <= 0 else chars[min(int((value - low) / span * (len(chars) - 1)), len(chars) - 1)]
        for value in values
    )
    return f"{high:.2f} ┤{line}\n{low:.2f} └{'─' * len(line)}"


def build_email_html(
    rotation_result: dict[str, Any],
    previous_holding_label: str | None = None,
    equity_curve: list[dict[str, Any]] | None = None,
) -> str:
    subject = build_email_subject(rotation_result, previous_holding_label)
    summary_lines = _build_decision_summary(rotation_result, previous_holding_label)
    data_status = rotation_result.get("data_status") or {}
    curve_text = build_ascii_equity_curve(equity_curve)
    summary_html = "".join(f"<p>{escape(line)}</p>" for line in summary_lines)
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #202124; }}
    table {{ border-collapse: collapse; width: 100%; margin: 12px 0 20px; }}
    th, td {{ border-bottom: 1px solid #e5e7eb; padding: 8px 10px; text-align: left; font-size: 13px; }}
    th {{ background: #f8fafc; color: #475569; }}
    .summary {{ border-left: 4px solid #2563eb; padding: 8px 14px; background: #f8fafc; }}
    pre {{ background: #f8fafc; padding: 12px; overflow-x: auto; }}
  </style>
</head>
<body>
  <h1>{escape(subject)}</h1>
  <div class="summary">{summary_html}</div>
  {_build_data_status_html(data_status)}
  {_build_candidate_table_html(rotation_result)}
  <h2>近60日策略净值走势</h2>
  <pre>{escape(curve_text)}</pre>
</body>
</html>
"""


def build_email_text(
    rotation_result: dict[str, Any],
    previous_holding_label: str | None = None,
    equity_curve: list[dict[str, Any]] | None = None,
) -> str:
    lines = [build_email_subject(rotation_result, previous_holding_label), ""]
    lines.extend(_build_decision_summary(rotation_result, previous_holding_label))
    lines.extend(["", "近60日策略净值走势", build_ascii_equity_curve(equity_curve)])
    return "\n".join(lines)


def load_email_state(state_path: Path = DEFAULT_STATE_PATH) -> dict[str, Any]:
    if not state_path.exists():
        return {}
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def build_next_state(rotation_result: dict[str, Any]) -> dict[str, Any] | None:
    if not _is_data_ready(rotation_result):
        return None
    selected_label = _selected_label(rotation_result)
    if selected_label == "未选择":
        return None
    return {
        "last_signal_date": _signal_date(rotation_result),
        "last_holding_label": selected_label,
        "last_selection_reason": str(
            rotation_result.get("portfolio_decision", {}).get("selection_reason") or ""
        ),
    }


def write_email_state(state_path: Path, state: dict[str, Any]) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def collect_etf_rotation_v2_email_payloads(
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    state_path: Path = DEFAULT_STATE_PATH,
) -> dict[str, Any]:
    rotation_result = runner.run(
        output_root=output_dir / "rotation",
        source_output_root=output_dir / "source",
    )
    previous_state = load_email_state(state_path)
    previous_holding_label = str(previous_state.get("last_holding_label") or "").strip() or None
    subject = build_email_subject(rotation_result, previous_holding_label)
    html = build_email_html(rotation_result, previous_holding_label)
    text = build_email_text(rotation_result, previous_holding_label)
    return {
        "rotation_result": rotation_result,
        "previous_state": previous_state,
        "next_state": build_next_state(rotation_result),
        "subject": subject,
        "html": html,
        "text": text,
    }


def write_preview_html(html: str, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "preview_etf_rotation_v2_email.html"
    output_path.write_text(html, encoding="utf-8")
    return output_path


def main() -> int:
    payloads = collect_etf_rotation_v2_email_payloads(DEFAULT_OUTPUT_DIR)
    output_path = write_preview_html(str(payloads["html"]), DEFAULT_OUTPUT_DIR)
    print(f"[INFO] ETF 轮动 V2 邮件预览已生成: {output_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
