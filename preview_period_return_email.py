from __future__ import annotations

import base64
import json
from html import escape
from pathlib import Path
from typing import Any

import analyze_etf_com_cn_period_returns as analysis
import prototype_period_return_chart as chart


DEFAULT_CONFIG_PATH = Path("period_return_email_config.yaml")
DEFAULT_OUTPUT_DIR = Path(".test_artifacts/period_return_email")
DEFAULT_SAMPLE_DIR = Path(".test_artifacts/etf_com_cn_api")


def load_curve_payloads(codes: list[str], sample_dir: Path = DEFAULT_SAMPLE_DIR) -> dict[str, list[dict[str, Any]]]:
    output: dict[str, list[dict[str, Any]]] = {}
    one_month_dir = sample_dir / "one_month_analysis"
    for code in codes:
        storage_key = analysis.build_target_storage_key(code)
        path = one_month_dir / f"{storage_key}_one_month_curve.json"
        if not path.exists():
            path = one_month_dir / f"{code}_one_month_curve.json"
        output[code] = json.loads(path.read_text(encoding="utf-8"))
    return output


def png_to_data_uri(path: Path) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def render_period_return_table(table_rows: list[dict[str, str]]) -> str:
    headers = [
        ("name", "名称"),
        ("code", "代码"),
        ("return_1m", "近1月"),
        ("return_3m", "近3月"),
        ("return_6m", "近6月"),
        ("return_1y", "近1年"),
        ("return_ytd", "年初至今"),
        ("return_3y", "近3年"),
        ("return_5y", "近5年"),
        ("return_10y", "近10年"),
        ("return_since_inception", "成立以来"),
    ]
    th_style = (
        "padding:10px 12px;background:#f4f6f8;border:1px solid #d9e0e7;"
        "font-size:12px;color:#4c5563;text-align:right;white-space:nowrap"
    )
    td_style = (
        "padding:10px 12px;border:1px solid #d9e0e7;font-size:13px;"
        "color:#1f2937;text-align:right;white-space:nowrap"
    )
    rows_html = []
    for row in table_rows:
        cells = []
        for key, _ in headers:
            align = "left" if key == "name" else "right"
            style = td_style + f";text-align:{align}"
            cells.append(f'<td style="{style}">{escape(str(row.get(key, "--")))}</td>')
        rows_html.append(f"<tr>{''.join(cells)}</tr>")

    header_html = "".join(
        f'<th style="{th_style};text-align:{"left" if key == "name" else "right"}">{escape(label)}</th>'
        for key, label in headers
    )
    return (
        '<div style="overflow-x:auto">'
        '<table cellpadding="0" cellspacing="0" border="0" width="100%" '
        'style="border-collapse:collapse;min-width:980px">'
        f"<thead><tr>{header_html}</tr></thead>"
        f"<tbody>{''.join(rows_html)}</tbody>"
        "</table></div>"
    )


def build_period_return_email_html(
    table_rows: list[dict[str, str]],
    chart_data_uri: str,
    as_of_label: str,
) -> str:
    table_html = render_period_return_table(table_rows)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>ETF 区间收益预览</title>
</head>
<body style="margin:0;padding:0;background:#eef2f6;font-family:'Microsoft YaHei','PingFang SC','Helvetica Neue',Arial,sans-serif;color:#1f2937">
  <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background:#eef2f6">
    <tr>
      <td align="center" style="padding:20px 8px">
        <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background:#ffffff;border-radius:18px;overflow:hidden">
          <tr>
            <td style="padding:22px 20px 14px 20px;border-bottom:1px solid #e6ebf2">
              <div style="font-size:24px;font-weight:700;color:#152033">ETF 区间收益对比</div>
              <div style="margin-top:8px;font-size:13px;color:#667085">数据截至 {escape(as_of_label)}</div>
            </td>
          </tr>
          <tr>
            <td style="padding:16px 20px 0 20px">
              <div style="font-size:16px;font-weight:700;color:#152033;margin-bottom:12px">近1月收益率走势图</div>
            </td>
          </tr>
          <tr>
            <td style="padding:0">
              <img src="{chart_data_uri}" alt="近1月收益率走势图" style="display:block;width:100%;max-width:100%;height:auto">
            </td>
          </tr>
          <tr>
            <td style="padding:22px 20px 22px 20px">
              <div style="font-size:16px;font-weight:700;color:#152033;margin-bottom:12px">区间收益率表格</div>
              {table_html}
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
    output_path = output_dir / "preview_period_return_email.html"
    output_path.write_text(html, encoding="utf-8")
    return output_path


def main() -> int:
    payloads = analysis.collect_period_return_payloads(
        config_path=DEFAULT_CONFIG_PATH,
        output_dir=DEFAULT_OUTPUT_DIR,
    )
    table_rows = payloads["table_rows"]
    curve_payloads = payloads["curve_payloads"]

    chart_path = chart.generate_one_month_return_chart(
        table_rows,
        curve_payloads,
        output_dir=DEFAULT_OUTPUT_DIR,
    )
    chart_data_uri = png_to_data_uri(chart_path)
    as_of_label = str(payloads["as_of_label"])
    html = build_period_return_email_html(table_rows, chart_data_uri, as_of_label)
    output_path = write_preview_html(html, DEFAULT_OUTPUT_DIR)
    print(f"[INFO] 预览已生成: {output_path.resolve()}")
    print(f"[INFO] 图表已生成: {chart_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
