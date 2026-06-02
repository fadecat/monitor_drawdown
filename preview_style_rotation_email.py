from __future__ import annotations

import base64
from html import escape
from pathlib import Path
from typing import Any

import monitor_drawdown as md
import prototype_style_rotation_chart as chart
import style_rotation_preview as analysis


DEFAULT_OUTPUT_DIR = Path(".test_artifacts/style_rotation_email")


def resolve_as_of_label(payload: dict[str, Any]) -> str:
    dates = ((payload.get("series") or {}).get("dates") or [])
    if dates:
        return str(dates[-1])
    return md.now_in_beijing().strftime("%Y-%m-%d")


def collect_style_rotation_email_payloads(
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> dict[str, Any]:
    payload = analysis.collect_style_rotation_preview_payload()
    chart_path = chart.generate_style_rotation_chart(payload, output_dir)
    return {
        "payload": payload,
        "chart_path": chart_path,
        "as_of_label": resolve_as_of_label(payload),
    }


def png_to_data_uri(path: Path) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def build_style_rotation_email_html(*, payload: dict[str, Any], chart_cid: str, as_of_label: str) -> str:
    meta = payload.get("meta") or {}
    left_name = str(meta.get("left_name") or "左侧标的").strip()
    right_name = str(meta.get("right_name") or "右侧标的").strip()
    return_window_days = meta.get("return_window_days")
    display_window_days = meta.get("display_window_days")
    latest_spread = None
    spread_series = ((payload.get("series") or {}).get("spread") or [])
    if spread_series:
        latest_spread = spread_series[-1]

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>风格轮动收益率差值预览</title>
</head>
<body style="margin:0;padding:0;background:#eef2f6;font-family:'Microsoft YaHei','PingFang SC','Helvetica Neue',Arial,sans-serif;color:#1f2937">
  <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background:#eef2f6">
    <tr>
      <td align="center" style="padding:20px 8px">
        <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background:#ffffff;border-radius:18px;overflow:hidden">
          <tr>
            <td style="padding:22px 20px 14px 20px;border-bottom:1px solid #e6ebf2">
              <div style="font-size:24px;font-weight:700;color:#152033">风格轮动收益率差值预览</div>
              <div style="margin-top:8px;font-size:13px;color:#667085">数据截至 {escape(as_of_label)}</div>
              <div style="margin-top:10px;font-size:14px;color:#344054">{escape(left_name)} vs {escape(right_name)}</div>
              <div style="margin-top:6px;font-size:12px;color:#667085">展示窗口 {escape(str(display_window_days))} 天 | 计算窗口 {escape(str(return_window_days))} 天 | 当前差值 {escape(str(latest_spread))}%</div>
            </td>
          </tr>
          <tr>
            <td style="padding:0">
              <img src="{chart_cid}" alt="风格轮动收益率差值图" style="display:block;width:100%;max-width:100%;height:auto">
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""


def write_preview_html(html: str, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "preview_style_rotation_email.html"
    output_path.write_text(html, encoding="utf-8")
    return output_path


def main() -> int:
    payloads = collect_style_rotation_email_payloads(output_dir=DEFAULT_OUTPUT_DIR)
    chart_data_uri = png_to_data_uri(Path(payloads["chart_path"]))
    html = build_style_rotation_email_html(
        payload=dict(payloads["payload"]),
        chart_cid=chart_data_uri,
        as_of_label=str(payloads["as_of_label"]),
    )
    output_path = write_preview_html(html, DEFAULT_OUTPUT_DIR)
    print(f"[INFO] 风格轮动邮件预览已生成: {output_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
