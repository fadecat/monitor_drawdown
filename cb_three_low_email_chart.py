"""可转债三低轮动 模拟盘邮件净值曲线图。

样式仿「投资账本」对比图：
- 策略净值（红） vs 集思录等权指数（蓝），均从首个共同日期归一、以涨跌幅展示
- 最大回撤区间用橙色带高亮，并标注回撤数值
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any, Dict, List, Optional

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib import font_manager


NAV_CHART_CID = "cb_three_low_nav_chart"
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

COLOR_STRATEGY = "#d93025"  # 策略 红
COLOR_BENCHMARK = "#2c7be5"  # 基准 蓝
COLOR_DRAWDOWN = "#f59e0b"  # 回撤区间 橙


def _resolve_font() -> str:
    available = {f.name for f in font_manager.fontManager.ttflist}
    for family in PREFERRED_FONT_FAMILIES:
        if family in available:
            return family
    return "sans-serif"


def _parse_date(value: str) -> dt.date:
    return dt.date.fromisoformat(str(value)[:10])


def generate_nav_chart(
    history: List[Dict[str, Any]],
    output_path: Path,
    *,
    title: str = "可转债三低轮动 组合净值",
    benchmark: Optional[List[Dict[str, Any]]] = None,
    drawdown: Optional[Dict[str, Any]] = None,
) -> Path:
    """生成净值对比图。

    history: 策略持仓历史（含 date/nav）
    benchmark: align_benchmark 的输出 [{"date","strategy_return","benchmark_return"}]，
               为 None 时只画策略线（净值口径）
    drawdown: find_max_drawdown_window 的输出 {"peak_date","trough_date","max_drawdown"}
    """
    font = _resolve_font()
    plt.rcParams["font.family"] = font
    plt.rcParams["axes.unicode_minus"] = False

    fig, ax = plt.subplots(figsize=(9, 4))

    if benchmark:
        dates = [_parse_date(p["date"]) for p in benchmark]
        strategy_pct = [p["strategy_return"] * 100 for p in benchmark]
        benchmark_pct = [p["benchmark_return"] * 100 for p in benchmark]
        ax.plot(dates, strategy_pct, color=COLOR_STRATEGY, linewidth=2, marker="o",
                markersize=3, label="三低轮动", zorder=3)
        ax.plot(dates, benchmark_pct, color=COLOR_BENCHMARK, linewidth=1.5, marker="o",
                markersize=2.5, alpha=0.9, label="集思录等权", zorder=2)
        ax.axhline(0.0, color="#9aa0a6", linewidth=1, linestyle="--")
        ax.legend(loc="upper left", frameon=False, fontsize=10)
        ax.set_ylabel("区间涨跌幅 (%)")
    else:
        points = [e for e in history if e.get("nav") is not None]
        dates = [_parse_date(e["date"]) for e in points]
        navs = [float(e["nav"]) for e in points]
        if dates:
            ax.plot(dates, navs, color=COLOR_STRATEGY, linewidth=2, marker="o", markersize=3)
            ax.fill_between(
                dates, 1.0, navs, where=[v >= 1.0 for v in navs],
                color=COLOR_STRATEGY, alpha=0.08, interpolate=True,
            )
            ax.fill_between(
                dates, navs, 1.0, where=[v < 1.0 for v in navs],
                color="#2E7D32", alpha=0.08, interpolate=True,
            )
            ax.axhline(1.0, color="#9aa0a6", linewidth=1, linestyle="--")
        ax.set_ylabel("组合净值")

    # 最大回撤区间高亮 + 标注
    if drawdown and drawdown.get("trough_date") and dates:
        peak_date = drawdown.get("peak_date")
        # peak_date 为 None 表示起点即最高点，用首个数据日代替
        band_start = _parse_date(peak_date) if peak_date else dates[0]
        band_end = _parse_date(drawdown["trough_date"])
        ax.axvspan(band_start, band_end, color=COLOR_DRAWDOWN, alpha=0.15, zorder=1)
        trough_x = band_end
        trough_idx = min(range(len(dates)), key=lambda i: abs((dates[i] - band_end).days))
        if benchmark:
            trough_y = strategy_pct[trough_idx]
        else:
            trough_y = navs[trough_idx] if dates else 0.0
        dd_pct = float(drawdown["max_drawdown"]) * 100
        ax.annotate(
            f"最大回撤 {dd_pct:.2f}%",
            xy=(trough_x, trough_y),
            xytext=(12, -22),
            textcoords="offset points",
            fontsize=9,
            color="#ffffff",
            fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.35", fc=COLOR_DRAWDOWN, ec="none", alpha=0.95),
            arrowprops=dict(arrowstyle="-", color=COLOR_DRAWDOWN, lw=1),
            zorder=4,
        )

    ax.set_title(title, fontsize=13)
    ax.grid(True, linestyle=":", alpha=0.4)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
    fig.autofmt_xdate()
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=130)
    plt.close(fig)
    return output_path
