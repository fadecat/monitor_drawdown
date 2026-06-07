from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.ticker import FuncFormatter

import analyze_etf_com_cn_period_returns as etf_analysis


BENCHMARK_CODE = "510300"
BENCHMARK_LABEL = "沪深300ETF"
BENCHMARK_CHART_CID = "etf_rotation_v2_equity_chart"
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
