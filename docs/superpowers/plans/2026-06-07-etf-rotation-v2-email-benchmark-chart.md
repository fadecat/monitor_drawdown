# ETF Rotation V2 Email Benchmark Chart Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 V2 每日邮件中的 ASCII 净值走势升级为“近 1 年策略收益率 vs 沪深300ETF基准”的 PNG 图，同时保持 V2 策略逻辑、回测口径和每日信号不变。

**Architecture:** 新增一个只负责展示层图表的模块，从 V2 回测 `daily_positions` 读取策略净值，从易方达 CDN 的 `etf_fund_nav_510300.json` 读取沪深300ETF复权净值，按共同日期窗口归一化为收益率曲线。预览邮件使用 base64 data URI 嵌入 PNG，正式邮件使用 CID 附件嵌入 PNG，并在归档中保存图表文件和基准源数据。

**Tech Stack:** Python 3.10, matplotlib, pandas-free CSV/JSON processing, `EmailMessage.add_related`, pytest, existing `analyze_etf_com_cn_period_returns.load_nav_rows`, existing V2 runner/backtest pipeline.

---

## 文件结构

- Create: `etf_rotation_v2_email_chart.py`
  - 负责基准序列加载、收益曲线数据构建、近 1 年指标计算、PNG 图生成。
  - 不读取 V2 配置，不参与候选池、排名、过滤、防守逻辑。
- Modify: `preview_etf_rotation_v2_email.py`
  - 调用图表模块生成 PNG。
  - 预览 HTML 使用 base64 data URI。
  - HTML 结构从当前简单页面升级为邮件表格布局。
  - 保留 ASCII 文本邮件作为纯文本 fallback。
- Modify: `send_etf_rotation_v2_email.py`
  - 支持可选图片附件 CID。
  - 正式发送时使用 `cid:etf_rotation_v2_equity_chart`。
  - 归档 `email_chart.png` 和 `benchmark/` 数据。
- Modify: `docs/etf_rotation_v2_email_design.md`
  - 记录基准口径：沪深300ETF（510300）复权净值，只用于展示，不进入策略。
- Tests:
  - Modify: `tests/test_preview_etf_rotation_v2_email.py`
  - Modify: `tests/test_send_etf_rotation_v2_email.py`
  - Create: `tests/test_etf_rotation_v2_email_chart.py`

---

### Task 1: 新增图表数据模块，冻结基准口径

**Files:**
- Create: `etf_rotation_v2_email_chart.py`
- Test: `tests/test_etf_rotation_v2_email_chart.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_etf_rotation_v2_email_chart.py`:

```python
from __future__ import annotations

from pathlib import Path

import etf_rotation_v2_email_chart as module


def test_normalize_benchmark_nav_rows_uses_adj_unit_nav_and_dedupes_dates():
    rows = [
        {"trdDt": "2026-06-01", "adjUnitNav": "4.00", "unitNav": "3.00"},
        {"trdDt": "2026-06-02", "adjUnitNav": 4.20},
        {"trdDt": "2026-06-02", "adjUnitNav": 4.30},
        {"trdDt": "", "adjUnitNav": 9.99},
        {"trdDt": "2026-06-03", "adjUnitNav": None},
    ]

    assert module.normalize_benchmark_nav_rows(rows) == [
        {"date": "2026-06-01", "benchmark_nav": 4.0},
        {"date": "2026-06-02", "benchmark_nav": 4.3},
    ]


def test_build_relative_return_curve_aligns_strategy_and_benchmark_dates():
    strategy_rows = [
        {"date": "2026-06-01", "strategy_nav": 38.0},
        {"date": "2026-06-02", "strategy_nav": 39.9},
        {"date": "2026-06-03", "strategy_nav": 38.76},
    ]
    benchmark_rows = [
        {"date": "2026-06-01", "benchmark_nav": 4.0},
        {"date": "2026-06-03", "benchmark_nav": 4.4},
    ]

    result = module.build_relative_return_curve(
        strategy_rows=strategy_rows,
        benchmark_rows=benchmark_rows,
        window_days=365,
    )

    assert result["benchmark_label"] == "沪深300ETF"
    assert result["points"] == [
        {
            "date": "2026-06-01",
            "strategy_return": 0.0,
            "benchmark_return": 0.0,
            "strategy_nav": 38.0,
            "benchmark_nav": 4.0,
        },
        {
            "date": "2026-06-03",
            "strategy_return": 0.02,
            "benchmark_return": 0.1,
            "strategy_nav": 38.76,
            "benchmark_nav": 4.4,
        },
    ]
    assert result["summary"]["strategy_period_return"] == 0.02
    assert result["summary"]["benchmark_period_return"] == 0.1
    assert result["summary"]["excess_return"] == -0.08
    assert result["summary"]["strategy_max_drawdown"] == 0.0


def test_write_benchmark_series_uses_etf_nav_loader_and_archives_json(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        module.etf_analysis,
        "load_nav_rows",
        lambda code: [
            {"trdDt": "2026-06-01", "adjUnitNav": 4.0},
            {"trdDt": "2026-06-02", "adjUnitNav": 4.2},
        ],
    )

    rows = module.load_benchmark_series(output_dir=tmp_path)

    assert rows == [
        {"date": "2026-06-01", "benchmark_nav": 4.0},
        {"date": "2026-06-02", "benchmark_nav": 4.2},
    ]
    assert (tmp_path / "benchmark" / "etf_510300.json").exists()
    assert "2026-06-02" in (tmp_path / "benchmark" / "etf_510300.json").read_text(encoding="utf-8")
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_etf_rotation_v2_email_chart.py -q
```

Expected:

```text
ModuleNotFoundError: No module named 'etf_rotation_v2_email_chart'
```

- [ ] **Step 3: Implement the minimal module**

Create `etf_rotation_v2_email_chart.py`:

```python
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import analyze_etf_com_cn_period_returns as etf_analysis


BENCHMARK_CODE = "510300"
BENCHMARK_LABEL = "沪深300ETF"
BENCHMARK_CHART_CID = "etf_rotation_v2_equity_chart"


def normalize_benchmark_nav_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for row in rows:
        date_text = str(row.get("trdDt") or "").strip()
        raw_nav = row.get("adjUnitNav")
        if not date_text or raw_nav in {None, ""}:
            continue
        try:
            nav = float(raw_nav)
        except (TypeError, ValueError):
            continue
        deduped[date_text] = {"date": date_text, "benchmark_nav": nav}
    return [deduped[key] for key in sorted(deduped)]


def load_benchmark_series(output_dir: Path, code: str = BENCHMARK_CODE) -> list[dict[str, Any]]:
    rows = etf_analysis.load_nav_rows(code)
    normalized = normalize_benchmark_nav_rows([row for row in rows if isinstance(row, dict)])
    benchmark_dir = output_dir / "benchmark"
    benchmark_dir.mkdir(parents=True, exist_ok=True)
    (benchmark_dir / f"etf_{code}.json").write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return normalized


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _clean_float(value: float) -> float:
    return round(float(value), 12)


def _max_drawdown(values: list[float]) -> float:
    if not values:
        return 0.0
    peak = values[0]
    max_drawdown = 0.0
    for value in values:
        if value > peak:
            peak = value
        if peak > 0:
            max_drawdown = min(max_drawdown, value / peak - 1.0)
    return _clean_float(max_drawdown)


def build_relative_return_curve(
    *,
    strategy_rows: list[dict[str, Any]],
    benchmark_rows: list[dict[str, Any]],
    window_days: int = 365,
) -> dict[str, Any]:
    strategy_by_date = {
        str(row.get("date") or "").strip(): float(row["strategy_nav"])
        for row in strategy_rows
        if str(row.get("date") or "").strip() and row.get("strategy_nav") not in {None, ""}
    }
    benchmark_by_date = {
        str(row.get("date") or "").strip(): float(row["benchmark_nav"])
        for row in benchmark_rows
        if str(row.get("date") or "").strip() and row.get("benchmark_nav") not in {None, ""}
    }
    common_dates = sorted(set(strategy_by_date) & set(benchmark_by_date))
    if not common_dates:
        return {"benchmark_label": BENCHMARK_LABEL, "points": [], "summary": {}}

    end_date = _parse_date(common_dates[-1])
    start_cutoff = end_date - timedelta(days=window_days)
    window_dates = [item for item in common_dates if _parse_date(item) >= start_cutoff]
    if not window_dates:
        window_dates = common_dates

    base_strategy = strategy_by_date[window_dates[0]]
    base_benchmark = benchmark_by_date[window_dates[0]]
    points = []
    for item in window_dates:
        strategy_nav = strategy_by_date[item]
        benchmark_nav = benchmark_by_date[item]
        points.append(
            {
                "date": item,
                "strategy_return": _clean_float(strategy_nav / base_strategy - 1.0),
                "benchmark_return": _clean_float(benchmark_nav / base_benchmark - 1.0),
                "strategy_nav": strategy_nav,
                "benchmark_nav": benchmark_nav,
            }
        )

    strategy_returns = [float(point["strategy_return"]) for point in points]
    summary = {
        "start_date": points[0]["date"],
        "end_date": points[-1]["date"],
        "strategy_period_return": _clean_float(points[-1]["strategy_return"]),
        "benchmark_period_return": _clean_float(points[-1]["benchmark_return"]),
        "excess_return": _clean_float(points[-1]["strategy_return"] - points[-1]["benchmark_return"]),
        "strategy_max_drawdown": _max_drawdown([1.0 + value for value in strategy_returns]),
    }
    return {"benchmark_label": BENCHMARK_LABEL, "points": points, "summary": summary}
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```powershell
python -m pytest tests/test_etf_rotation_v2_email_chart.py -q
```

Expected:

```text
3 passed
```

- [ ] **Step 5: Commit**

```powershell
git add etf_rotation_v2_email_chart.py tests/test_etf_rotation_v2_email_chart.py
git commit -m "feat: add ETF rotation V2 benchmark chart data"
```

---

### Task 2: 生成策略 vs 基准 PNG 图

**Files:**
- Modify: `etf_rotation_v2_email_chart.py`
- Test: `tests/test_etf_rotation_v2_email_chart.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_etf_rotation_v2_email_chart.py`:

```python
def test_generate_equity_chart_png_writes_file(tmp_path: Path):
    curve = {
        "benchmark_label": "沪深300ETF",
        "points": [
            {"date": "2026-06-01", "strategy_return": 0.0, "benchmark_return": 0.0},
            {"date": "2026-06-02", "strategy_return": 0.04, "benchmark_return": 0.01},
            {"date": "2026-06-03", "strategy_return": 0.02, "benchmark_return": -0.01},
        ],
        "summary": {
            "strategy_period_return": 0.02,
            "benchmark_period_return": -0.01,
            "excess_return": 0.03,
            "strategy_max_drawdown": -0.019230769231,
        },
    }

    output_path = module.generate_equity_chart_png(curve, output_dir=tmp_path)

    assert output_path == tmp_path / "etf_rotation_v2_equity_chart.png"
    assert output_path.exists()
    assert output_path.stat().st_size > 1000
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests/test_etf_rotation_v2_email_chart.py::test_generate_equity_chart_png_writes_file -q
```

Expected:

```text
AttributeError: module 'etf_rotation_v2_email_chart' has no attribute 'generate_equity_chart_png'
```

- [ ] **Step 3: Implement chart generation**

Modify `etf_rotation_v2_email_chart.py`, add imports:

```python
from datetime import datetime

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.ticker import FuncFormatter
```

Append:

```python
PREFERRED_FONT_FAMILIES = [
    "Noto Sans CJK SC",
    "Noto Sans CJK JP",
    "Microsoft YaHei",
    "SimHei",
    "PingFang SC",
    "WenQuanYi Zen Hei",
    "Source Han Sans SC",
    "Arial Unicode MS",
]


def configure_matplotlib_fonts() -> None:
    available = {font.name for font in font_manager.fontManager.ttflist}
    selected = [name for name in PREFERRED_FONT_FAMILIES if name in available]
    if selected:
        plt.rcParams["font.sans-serif"] = selected + ["DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False


def _format_pct(value: float) -> str:
    return f"{value * 100:+.1f}%"


def generate_equity_chart_png(curve: dict[str, Any], output_dir: Path) -> Path:
    points = list(curve.get("points") or [])
    if not points:
        raise ValueError("no ETF rotation V2 chart points available")

    configure_matplotlib_fonts()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "etf_rotation_v2_equity_chart.png"

    x_values = [datetime.strptime(str(point["date"]), "%Y-%m-%d") for point in points]
    strategy_values = [float(point["strategy_return"]) for point in points]
    benchmark_values = [float(point["benchmark_return"]) for point in points]
    summary = curve.get("summary") or {}
    benchmark_label = str(curve.get("benchmark_label") or BENCHMARK_LABEL)

    fig, ax = plt.subplots(figsize=(13, 6), dpi=150)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    ax.plot(x_values, benchmark_values, color="#DC2626", linewidth=1.8, label=benchmark_label)
    ax.plot(x_values, strategy_values, color="#2563EB", linewidth=2.6, label="ETF轮动V2")

    ax.scatter([x_values[-1]], [strategy_values[-1]], color="#2563EB", s=42, zorder=4)
    ax.scatter([x_values[-1]], [benchmark_values[-1]], color="#DC2626", s=34, zorder=4)

    ax.text(
        x_values[-1],
        strategy_values[-1],
        "  " + _format_pct(float(summary.get("strategy_period_return") or strategy_values[-1])),
        color="#2563EB",
        fontsize=10,
        va="center",
        fontweight="bold",
    )
    ax.text(
        x_values[-1],
        benchmark_values[-1],
        "  " + _format_pct(float(summary.get("benchmark_period_return") or benchmark_values[-1])),
        color="#DC2626",
        fontsize=10,
        va="center",
        fontweight="bold",
    )

    all_values = strategy_values + benchmark_values
    y_min = min(all_values)
    y_max = max(all_values)
    margin = max((y_max - y_min) * 0.18, 0.03)
    ax.set_ylim(y_min - margin, y_max + margin)

    ax.axhline(0, color="#94A3B8", linewidth=0.9)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value * 100:.0f}%"))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=4, maxticks=7))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    ax.grid(axis="y", color="#E2E8F0", linewidth=0.8)
    ax.grid(axis="x", color="#F1F5F9", linewidth=0.6)

    ax.set_title("近1年策略收益率 vs 沪深300ETF", fontsize=17, fontweight="bold", pad=18)
    ax.legend(loc="upper left", frameon=False, fontsize=10)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#CBD5E1")
    ax.spines["bottom"].set_color("#CBD5E1")
    ax.tick_params(axis="x", labelsize=9, colors="#475569")
    ax.tick_params(axis="y", labelsize=10, colors="#475569")

    footer = (
        f"策略 {_format_pct(float(summary.get('strategy_period_return') or 0.0))}  "
        f"基准 {_format_pct(float(summary.get('benchmark_period_return') or 0.0))}  "
        f"超额 {_format_pct(float(summary.get('excess_return') or 0.0))}  "
        f"最大回撤 {_format_pct(float(summary.get('strategy_max_drawdown') or 0.0))}"
    )
    fig.text(0.06, 0.02, footer, fontsize=10, color="#334155")

    plt.tight_layout(rect=(0.02, 0.05, 0.98, 0.96))
    fig.savefig(output_path, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    return output_path
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```powershell
python -m pytest tests/test_etf_rotation_v2_email_chart.py -q
```

Expected:

```text
4 passed
```

- [ ] **Step 5: Commit**

```powershell
git add etf_rotation_v2_email_chart.py tests/test_etf_rotation_v2_email_chart.py
git commit -m "feat: render ETF rotation V2 benchmark chart"
```

---

### Task 3: 预览邮件接入 PNG 图和新 HTML 布局

**Files:**
- Modify: `preview_etf_rotation_v2_email.py`
- Test: `tests/test_preview_etf_rotation_v2_email.py`

- [ ] **Step 1: Write failing tests**

Modify `tests/test_preview_etf_rotation_v2_email.py`.

Add import:

```python
import base64
```

Add test:

```python
def test_build_email_html_places_decision_chart_then_candidate_table():
    html = module.build_email_html(
        _rotation_result(aligned=False),
        previous_holding_label="上一有效持仓",
        equity_curve=[{"date": "2026-06-01", "strategy_nav": 38.0}],
        chart_data_uri="data:image/png;base64,abc",
        chart_summary={
            "strategy_period_return": 0.12,
            "benchmark_period_return": 0.03,
            "excess_return": 0.09,
            "strategy_max_drawdown": -0.04,
        },
    )

    assert "今日信号" in html
    assert "近1年策略收益率 vs 沪深300ETF" in html
    assert "data:image/png;base64,abc" in html
    assert "策略近1年" in html
    assert "+12.0%" in html
    assert html.index("今日结论") < html.index("近1年策略收益率 vs 沪深300ETF")
    assert html.index("近1年策略收益率 vs 沪深300ETF") < html.index("候选池评分")
    assert html.index("候选池评分") < html.index("数据状态")
```

Add test:

```python
def test_collect_payload_generates_chart_from_backtest_and_benchmark(monkeypatch, tmp_path: Path):
    state_path = tmp_path / "state.json"
    state_path.write_text('{"last_holding_label": "黄金ETF易方达"}', encoding="utf-8")

    monkeypatch.setattr(module.runner, "run", lambda **kwargs: _rotation_result())
    monkeypatch.setattr(
        module.backtest,
        "run_backtest",
        lambda **kwargs: {
            "daily_positions": [
                {"date": "2026-06-01", "strategy_nav": 38.0},
                {"date": "2026-06-02", "strategy_nav": 39.0},
            ]
        },
    )
    monkeypatch.setattr(
        module.email_chart,
        "load_benchmark_series",
        lambda output_dir: [
            {"date": "2026-06-01", "benchmark_nav": 4.0},
            {"date": "2026-06-02", "benchmark_nav": 4.1},
        ],
    )
    monkeypatch.setattr(
        module.email_chart,
        "generate_equity_chart_png",
        lambda curve, output_dir: (output_dir / "chart.png"),
    )
    (tmp_path / "out" / "chart.png").parent.mkdir(parents=True)
    (tmp_path / "out" / "chart.png").write_bytes(b"png")

    payload = module.collect_etf_rotation_v2_email_payloads(
        output_dir=tmp_path / "out",
        state_path=state_path,
    )

    assert payload["chart_path"] == tmp_path / "out" / "chart.png"
    assert payload["chart_summary"]["strategy_period_return"] > 0
    assert payload["chart_data_uri"].startswith("data:image/png;base64,")
    assert "近1年策略收益率 vs 沪深300ETF" in payload["html"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_preview_etf_rotation_v2_email.py::test_build_email_html_places_decision_chart_then_candidate_table tests/test_preview_etf_rotation_v2_email.py::test_collect_payload_generates_chart_from_backtest_and_benchmark -q
```

Expected:

```text
TypeError: build_email_html() got an unexpected keyword argument 'chart_data_uri'
```

- [ ] **Step 3: Implement preview integration**

Modify `preview_etf_rotation_v2_email.py`.

Add imports:

```python
import base64

import etf_rotation_v2_email_chart as email_chart
```

Add helpers:

```python
def png_to_data_uri(path: Path) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _format_plain_pct(value: Any) -> str:
    try:
        return f"{float(value) * 100:+.1f}%"
    except (TypeError, ValueError):
        return "--"


def _build_chart_summary_html(chart_summary: dict[str, Any] | None) -> str:
    summary = chart_summary or {}
    items = [
        ("策略近1年", summary.get("strategy_period_return")),
        ("基准近1年", summary.get("benchmark_period_return")),
        ("超额收益", summary.get("excess_return")),
        ("策略最大回撤", summary.get("strategy_max_drawdown")),
    ]
    cells = "".join(
        "<td style=\"padding:10px 12px;border:1px solid #e2e8f0\">"
        f"<div style=\"font-size:12px;color:#64748b\">{escape(label)}</div>"
        f"<div style=\"font-size:18px;font-weight:700;color:#0f172a\">{escape(_format_plain_pct(value))}</div>"
        "</td>"
        for label, value in items
    )
    return f"<table cellpadding=\"0\" cellspacing=\"0\" border=\"0\" width=\"100%\"><tr>{cells}</tr></table>"
```

Change signature:

```python
def build_email_html(
    rotation_result: dict[str, Any],
    previous_holding_label: str | None = None,
    equity_curve: list[dict[str, Any]] | None = None,
    chart_data_uri: str | None = None,
    chart_summary: dict[str, Any] | None = None,
) -> str:
```

Replace the body HTML with:

```python
    chart_block = (
        f'<img src="{escape(chart_data_uri)}" alt="近1年策略收益率 vs 沪深300ETF" '
        'style="display:block;width:100%;max-width:100%;height:auto">'
        if chart_data_uri
        else f"<pre>{escape(curve_text)}</pre>"
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{escape(subject)}</title>
</head>
<body style="margin:0;padding:0;background:#eef2f6;font-family:'Microsoft YaHei','PingFang SC','Helvetica Neue',Arial,sans-serif;color:#1f2937">
  <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background:#eef2f6">
    <tr>
      <td align="center" style="padding:20px 8px">
        <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background:#ffffff;border-radius:12px;overflow:hidden">
          <tr>
            <td style="padding:20px 20px 12px;border-bottom:1px solid #e2e8f0">
              <div style="font-size:22px;font-weight:700;color:#0f172a">ETF轮动V2 每日信号</div>
              <div style="margin-top:6px;font-size:13px;color:#64748b">{escape(subject)}</div>
            </td>
          </tr>
          <tr>
            <td style="padding:16px 20px;background:#f8fafc">
              <div style="font-size:16px;font-weight:700;color:#0f172a;margin-bottom:8px">今日信号</div>
              {summary_html}
            </td>
          </tr>
          <tr>
            <td style="padding:18px 20px 8px">
              <div style="font-size:16px;font-weight:700;color:#0f172a;margin-bottom:12px">近1年策略收益率 vs 沪深300ETF</div>
              {_build_chart_summary_html(chart_summary)}
            </td>
          </tr>
          <tr>
            <td style="padding:0 20px 18px">{chart_block}</td>
          </tr>
          <tr>
            <td style="padding:18px 20px">{_build_candidate_table_html(rotation_result)}</td>
          </tr>
          <tr>
            <td style="padding:0 20px 22px">{_build_data_status_html(data_status)}</td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""
```

In `collect_etf_rotation_v2_email_payloads`, after `equity_curve` is assigned:

```python
    chart_error = None
    chart_path = None
    chart_data_uri = None
    chart_summary: dict[str, Any] = {}
    try:
        benchmark_rows = email_chart.load_benchmark_series(output_dir)
        chart_curve = email_chart.build_relative_return_curve(
            strategy_rows=equity_curve,
            benchmark_rows=benchmark_rows,
            window_days=365,
        )
        chart_summary = dict(chart_curve.get("summary") or {})
        chart_path = email_chart.generate_equity_chart_png(chart_curve, output_dir=output_dir)
        chart_data_uri = png_to_data_uri(chart_path)
    except Exception as exc:
        chart_error = str(exc)
```

Change HTML call:

```python
    html = build_email_html(
        rotation_result,
        previous_holding_label,
        equity_curve,
        chart_data_uri=chart_data_uri,
        chart_summary=chart_summary,
    )
```

Add payload fields:

```python
        "chart_path": chart_path,
        "chart_data_uri": chart_data_uri,
        "chart_summary": chart_summary,
        "chart_error": chart_error,
```

- [ ] **Step 4: Run tests**

Run:

```powershell
python -m pytest tests/test_preview_etf_rotation_v2_email.py tests/test_etf_rotation_v2_email_chart.py -q
```

Expected:

```text
all tests pass
```

- [ ] **Step 5: Commit**

```powershell
git add preview_etf_rotation_v2_email.py tests/test_preview_etf_rotation_v2_email.py
git commit -m "feat: show ETF rotation V2 benchmark chart in preview"
```

---

### Task 4: 正式邮件使用 CID 图片附件

**Files:**
- Modify: `send_etf_rotation_v2_email.py`
- Test: `tests/test_send_etf_rotation_v2_email.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_send_etf_rotation_v2_email.py`:

```python
def test_build_email_message_attaches_equity_chart_with_cid(tmp_path: Path):
    chart_path = tmp_path / "chart.png"
    chart_path.write_bytes(b"png-bytes")

    message = module.build_etf_rotation_v2_email_message(
        sender="sender@qq.com",
        recipients=["alice@example.com"],
        subject="ETF",
        text="plain",
        html='<img src="cid:etf_rotation_v2_equity_chart">',
        chart_path=chart_path,
        chart_cid="etf_rotation_v2_equity_chart",
    )

    html = message.get_body(preferencelist=("html",)).get_content()
    assert "cid:etf_rotation_v2_equity_chart" in html
    related_parts = [part for part in message.walk() if part.get_content_maintype() == "image"]
    assert len(related_parts) == 1
    assert related_parts[0]["Content-ID"] == "<etf_rotation_v2_equity_chart>"
    assert related_parts[0].get_content_subtype() == "png"
```

Append:

```python
def test_send_main_uses_cid_html_instead_of_preview_data_uri(monkeypatch, tmp_path: Path):
    chart_path = tmp_path / "chart.png"
    chart_path.write_bytes(b"png")
    captured = {}
    payloads = {
        "subject": "ETF",
        "text": "plain",
        "html": '<img src="data:image/png;base64,abc">',
        "chart_path": chart_path,
        "next_state": None,
    }

    monkeypatch.setattr(module, "load_etf_rotation_v2_email_config", lambda: {
        "sender": "sender@qq.com",
        "recipients": ["alice@example.com"],
        "smtp_host": "smtp.example.com",
        "smtp_port": 465,
        "username": "u",
        "password": "p",
    })
    monkeypatch.setattr(module, "collect_etf_rotation_v2_email_payloads", lambda output_dir: payloads)
    monkeypatch.setattr(module, "persist_next_state", lambda payloads: None)
    monkeypatch.setattr(module, "archive_run_artifacts", lambda payloads, output_dir: None)

    def fake_send_etf_rotation_v2_email(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(module, "send_etf_rotation_v2_email", fake_send_etf_rotation_v2_email)

    assert module.main() == 0
    assert 'cid:etf_rotation_v2_equity_chart' in captured["html"]
    assert "data:image/png" not in captured["html"]
    assert captured["chart_path"] == chart_path
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_send_etf_rotation_v2_email.py::test_build_email_message_attaches_equity_chart_with_cid tests/test_send_etf_rotation_v2_email.py::test_send_main_uses_cid_html_instead_of_preview_data_uri -q
```

Expected:

```text
TypeError: build_etf_rotation_v2_email_message() got an unexpected keyword argument 'chart_path'
```

- [ ] **Step 3: Implement CID support**

Modify `send_etf_rotation_v2_email.py`.

Add import:

```python
import etf_rotation_v2_email_chart as email_chart
```

Change `build_etf_rotation_v2_email_message` signature:

```python
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
```

After `message.add_alternative(html, subtype="html")`, add:

```python
    if chart_path is not None and chart_path.exists():
        html_part = message.get_body(preferencelist=("html",))
        html_part.add_related(
            chart_path.read_bytes(),
            maintype="image",
            subtype="png",
            cid=f"<{chart_cid}>",
        )
```

Change `send_etf_rotation_v2_email` signature:

```python
def send_etf_rotation_v2_email(
    *,
    config: dict[str, Any],
    subject: str,
    text: str,
    html: str,
    chart_path: Path | None = None,
) -> None:
```

Pass `chart_path=chart_path` to `build_etf_rotation_v2_email_message`.

Add helper:

```python
def build_send_html(payloads: dict[str, Any]) -> str:
    html = str(payloads.get("html") or "")
    chart_path = payloads.get("chart_path")
    if isinstance(chart_path, Path) and chart_path.exists():
        import re
        return re.sub(
            r"data:image/png;base64,[A-Za-z0-9+/=]+",
            f"cid:{email_chart.BENCHMARK_CHART_CID}",
            html,
            count=1,
        )
    return html
```

In `main`, before send:

```python
    send_html = build_send_html(payloads)
```

Pass:

```python
        html=send_html,
        chart_path=payloads.get("chart_path") if isinstance(payloads.get("chart_path"), Path) else None,
```

- [ ] **Step 4: Run tests**

Run:

```powershell
python -m pytest tests/test_send_etf_rotation_v2_email.py -q
```

Expected:

```text
all tests pass
```

- [ ] **Step 5: Commit**

```powershell
git add send_etf_rotation_v2_email.py tests/test_send_etf_rotation_v2_email.py
git commit -m "feat: attach ETF rotation V2 chart to email"
```

---

### Task 5: 归档图表、基准数据和更新中文文档

**Files:**
- Modify: `send_etf_rotation_v2_email.py`
- Modify: `docs/etf_rotation_v2_email_design.md`
- Test: `tests/test_send_etf_rotation_v2_email.py`

- [ ] **Step 1: Write failing archive test**

Append to `tests/test_send_etf_rotation_v2_email.py`:

```python
def test_archive_run_artifacts_copies_chart_and_benchmark_data(tmp_path: Path):
    output_dir = tmp_path / "runtime"
    rotation_dir = output_dir / "rotation"
    rotation_dir.mkdir(parents=True)
    (rotation_dir / "data_status.json").write_text('{"status": "ready"}', encoding="utf-8")
    (output_dir / "source").mkdir(parents=True)
    backtest_dir = output_dir / "backtest"
    backtest_dir.mkdir(parents=True)
    (backtest_dir / "daily_positions.csv").write_text("date,strategy_nav\n2026-06-05,38.5\n", encoding="utf-8")
    benchmark_dir = output_dir / "benchmark"
    benchmark_dir.mkdir(parents=True)
    (benchmark_dir / "etf_510300.json").write_text('[{"date":"2026-06-05","benchmark_nav":4.2}]', encoding="utf-8")
    chart_path = output_dir / "etf_rotation_v2_equity_chart.png"
    chart_path.write_bytes(b"png")

    module.archive_run_artifacts(
        payloads={
            "subject": "ETF",
            "text": "plain",
            "html": "<html></html>",
            "next_state": {"last_holding_label": "A"},
            "chart_path": chart_path,
        },
        output_dir=output_dir,
        archive_root=tmp_path / "archive",
        state_path=tmp_path / "missing_state.json",
    )

    latest = tmp_path / "archive" / "latest"
    assert (latest / "email_chart.png").read_bytes() == b"png"
    assert (latest / "benchmark" / "etf_510300.json").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests/test_send_etf_rotation_v2_email.py::test_archive_run_artifacts_copies_chart_and_benchmark_data -q
```

Expected:

```text
AssertionError: email_chart.png does not exist
```

- [ ] **Step 3: Implement archive copy**

In `send_etf_rotation_v2_email.py`, inside `archive_run_artifacts`, after backtest copy:

```python
    _copy_tree_contents(output_dir / "benchmark", latest_dir / "benchmark")
    chart_path = payloads.get("chart_path")
    if isinstance(chart_path, Path) and chart_path.exists():
        shutil.copy2(chart_path, latest_dir / "email_chart.png")
```

- [ ] **Step 4: Update Chinese docs**

Modify `docs/etf_rotation_v2_email_design.md`.

Replace the “第四块是近 60 日策略净值走势...” paragraph with:

```markdown
第四块是近 1 年策略收益率对比图。图表使用 PNG，不再使用 ASCII 文字曲线。策略线来自同一次运行中 V2 回测输出的 `daily_positions`；基准线使用沪深300ETF（510300）的复权净值 `adjUnitNav`，只作为展示基准，不进入 V2 候选池、排名、过滤或防守逻辑。

图表口径：

| 项目 | 口径 |
|---|---|
| 策略线 | V2 `strategy_nav` 在展示窗口首日归一化为 0% |
| 基准线 | 沪深300ETF（510300）`adjUnitNav` 在同一展示窗口首日归一化为 0% |
| 展示窗口 | 最近 365 个自然日内的共同交易日期 |
| 图表指标 | 策略近 1 年收益、基准近 1 年收益、超额收益、策略最大回撤 |

如果图表生成失败，邮件仍然照常发送，并回退显示已有的文字净值走势，避免展示层故障阻断每日信号。
```

In archive table add:

```markdown
| `email_chart.png` | 邮件中展示的策略收益率 vs 沪深300ETF PNG 图 |
| `benchmark/` | 当次沪深300ETF基准序列缓存 |
```

- [ ] **Step 5: Run tests**

Run:

```powershell
python -m pytest tests/test_send_etf_rotation_v2_email.py -q
```

Expected:

```text
all tests pass
```

- [ ] **Step 6: Commit**

```powershell
git add send_etf_rotation_v2_email.py tests/test_send_etf_rotation_v2_email.py docs/etf_rotation_v2_email_design.md
git commit -m "feat: archive ETF rotation V2 email chart"
```

---

### Task 6: 全链路验证和真实预览

**Files:**
- No required code changes.
- Generated ignored files under `.test_artifacts/etf_rotation_v2_email/`.

- [ ] **Step 1: Run targeted tests**

Run:

```powershell
python -m pytest tests/test_etf_rotation_v2_strategy.py tests/test_run_etf_rotation_v2_strategy.py tests/test_backtest_etf_rotation_v2_strategy.py tests/test_etf_rotation_v2_data.py tests/test_etf_rotation_v2_email_chart.py tests/test_preview_etf_rotation_v2_email.py tests/test_send_etf_rotation_v2_email.py -q
```

Expected:

```text
all tests pass
```

- [ ] **Step 2: Generate real preview**

Run:

```powershell
python preview_etf_rotation_v2_email.py
```

Expected:

```text
[INFO] ETF 轮动 V2 邮件预览已生成: ...
```

Check generated files:

```powershell
Test-Path .test_artifacts\etf_rotation_v2_email\preview_etf_rotation_v2_email.html
Test-Path .test_artifacts\etf_rotation_v2_email\etf_rotation_v2_equity_chart.png
Test-Path .test_artifacts\etf_rotation_v2_email\benchmark\etf_510300.json
```

Expected:

```text
True
True
True
```

- [ ] **Step 3: Confirm preview HTML uses PNG data URI and no ASCII placeholder**

Run:

```powershell
Select-String -Path .test_artifacts\etf_rotation_v2_email\preview_etf_rotation_v2_email.html -Pattern "近1年策略收益率 vs 沪深300ETF|data:image/png;base64|暂无净值数据"
```

Expected:

```text
contains 近1年策略收益率 vs 沪深300ETF
contains data:image/png;base64
does not contain 暂无净值数据
```

- [ ] **Step 4: Confirm V2 回测指标未变**

Run:

```powershell
Get-Content .test_artifacts\etf_rotation_v2_email\backtest\backtest_summary.md
```

Expected key lines remain:

```text
- final_nav=38.294515
- annualized_return=0.354965
- max_drawdown=-0.216032
```

- [ ] **Step 5: Commit if any verification-only doc adjustment was needed**

If no files changed, skip. If docs changed:

```powershell
git add docs/etf_rotation_v2_email_design.md
git commit -m "docs: clarify ETF rotation V2 benchmark chart"
```

- [ ] **Step 6: Push branch**

Run:

```powershell
git push
```

Expected:

```text
codex/v2-rotation-email -> codex/v2-rotation-email
```

---

## 自检

- 计划覆盖了基准数据、曲线数据、PNG 生成、预览邮件、正式邮件 CID、归档和中文文档。
- 基准明确为 `510300` 沪深300ETF复权净值，只用于展示，不进入 V2 策略逻辑。
- 每个行为改动都有先失败再实现的测试步骤。
- 没有引入网页交互、tab、拖拽时间轴、完整月度/年度表等邮件第一版不需要的功能。
- 图表失败不会阻断每日信号邮件，保留当前 ASCII 曲线作为 fallback。
