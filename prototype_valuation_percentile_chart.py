from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.figure import Figure
from matplotlib.ticker import FormatStrFormatter
import numpy as np
import pandas as pd

import monitor_drawdown as md


FIGURE_DPI = 180
FIGURE_SIZE = (14, 5.2)
PREFERRED_CJK_FONTS = [
    "Noto Sans CJK SC",
    "Noto Sans CJK JP",
    "Microsoft YaHei",
    "SimHei",
    "PingFang SC",
    "WenQuanYi Zen Hei",
]
AX_BOUNDS = {
    "chart": [0.07, 0.16, 0.90, 0.70],
    "footer": [0.04, 0.03, 0.92, 0.07],
}
PALETTE = {
    "background": "#ffffff",
    "orange": "#ed7c2b",
    "text_primary": "#1f1f1f",
    "text_muted": "#8a8a8a",
    "grid": "#f0f0f0",
    "spine": "#d0d0d0",
    "pct_low": "#2f9e4f",
    "pct_mid": "#9aa0a6",
    "pct_high": "#d94f3a",
}
FONT_SIZES = {
    "legend": 12,
    "main_title": 14,
    "y_tick": 10,
    "x_tick": 11,
    "latest_label": 11,
    "footer": 9,
}


def pick_available_font_family() -> list[str]:
    available = {font.name for font in font_manager.fontManager.ttflist}
    selected = [name for name in PREFERRED_CJK_FONTS if name in available]
    return selected + ["DejaVu Sans"]


def _resolve_chart_item(target: Dict) -> Optional[Dict]:
    item = dict(target)
    if not item.get("index_code"):
        item["index_code"] = md.resolve_target_index_code(target) or target.get("code")

    need_metrics = not item.get("index_valuation_metrics")
    need_dividend = item.get("index_dividend_yield") is None
    if need_metrics or need_dividend:
        fetched = md.fetch_target_index_metrics(target)
        if fetched:
            for key, value in fetched.items():
                if item.get(key) in ("", None, {}):
                    item[key] = value

    index_code = str(item.get("index_code") or item.get("code") or "").strip()
    if not index_code:
        return None

    if not item.get("index_name"):
        item["index_name"] = str(item.get("name") or index_code).strip()
    return item


def _build_history_frame(item: Dict) -> Tuple[pd.DataFrame, Optional[str]]:
    index_code = str(item.get("index_code") or item.get("code") or "").strip()
    valuation_url = str(
        item.get("index_valuation_percentile_source")
        or item.get("index_valuation_percentile_url")
        or ""
    ).strip()
    pe_df = md.fetch_index_pe_history(index_code=index_code, url=valuation_url)
    pe_df = pe_df.dropna(subset=["date", "pe"]).copy()
    pe_df["date"] = pd.to_datetime(pe_df["date"], errors="coerce")
    pe_df["pe"] = pd.to_numeric(pe_df["pe"], errors="coerce")
    pe_df = pe_df.dropna(subset=["date", "pe"])
    pe_df = pe_df[pe_df["pe"] > 0].sort_values("date").reset_index(drop=True)
    if len(pe_df) < 20:
        return pd.DataFrame(columns=["date", "pe"]), None

    latest_date = pd.Timestamp(pe_df["date"].iloc[-1])
    cutoff = latest_date - pd.DateOffset(years=5)
    history_5y = pe_df[pe_df["date"] >= cutoff].copy().reset_index(drop=True)
    if len(history_5y) >= 20:
        return history_5y, None
    return pe_df, "使用全历史窗口（5Y 数据不足）"


def _prepare_chart_data(target: Dict) -> Optional[Dict]:
    item = _resolve_chart_item(target)
    if not item:
        return None

    history, footnote = _build_history_frame(item)
    if len(history) < 20:
        return None

    q30, q50, q70 = [float(value) for value in history["pe"].quantile([0.3, 0.5, 0.7]).tolist()]
    return {
        "item": item,
        "history": history,
        "q30": q30,
        "q50": q50,
        "q70": q70,
        "footnote": footnote,
    }


def _draw_main_chart(ax, data: Dict) -> None:
    history = data["history"]
    dates = pd.to_datetime(history["date"])
    pes = history["pe"].astype(float)

    ax.text(
        0.00,
        1.08,
        "PE走势",
        transform=ax.transAxes,
        fontsize=FONT_SIZES["main_title"],
        fontweight="bold",
        color=PALETTE["text_primary"],
        ha="left",
        va="baseline",
    )
    ax.text(
        0.00,
        1.00,
        f"30分位值{data['q30']:.2f}",
        transform=ax.transAxes,
        fontsize=FONT_SIZES["legend"],
        color=PALETTE["pct_low"],
        ha="left",
        va="baseline",
    )
    ax.text(
        0.16,
        1.00,
        f"中位值{data['q50']:.2f}",
        transform=ax.transAxes,
        fontsize=FONT_SIZES["legend"],
        color=PALETTE["pct_mid"],
        ha="left",
        va="baseline",
    )
    ax.text(
        0.31,
        1.00,
        f"70分位值{data['q70']:.2f}",
        transform=ax.transAxes,
        fontsize=FONT_SIZES["legend"],
        color=PALETTE["pct_high"],
        ha="left",
        va="baseline",
    )

    ax.plot(
        dates,
        pes,
        color=PALETTE["orange"],
        linewidth=1.2,
        solid_joinstyle="round",
        solid_capstyle="round",
    )
    ax.axhline(
        data["q30"],
        color=PALETTE["pct_low"],
        linestyle=(0, (5, 4)),
        linewidth=1.0,
        alpha=0.95,
        zorder=1,
    )
    ax.axhline(
        data["q50"],
        color=PALETTE["pct_mid"],
        linestyle=(0, (5, 4)),
        linewidth=1.0,
        alpha=0.95,
        zorder=1,
    )
    ax.axhline(
        data["q70"],
        color=PALETTE["pct_high"],
        linestyle=(0, (5, 4)),
        linewidth=1.0,
        alpha=0.95,
        zorder=1,
    )
    ax.annotate(
        f"{pes.iloc[-1]:.2f}",
        xy=(dates.iloc[-1], pes.iloc[-1]),
        xytext=(6, 6),
        textcoords="offset points",
        color=PALETTE["orange"],
        fontsize=FONT_SIZES["latest_label"],
        fontweight="bold",
    )

    ax.yaxis.grid(True, color=PALETTE["grid"], linewidth=0.8, alpha=1.0)
    ax.xaxis.grid(False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(PALETTE["spine"])
    ax.spines["left"].set_linewidth(0.8)
    ax.spines["bottom"].set_color(PALETTE["spine"])
    ax.spines["bottom"].set_linewidth(0.8)
    ax.tick_params(axis="both", which="both", length=0, colors=PALETTE["text_muted"])

    pe_min = float(pes.min())
    pe_max = float(pes.max())
    if pe_min == pe_max:
        pe_min -= 1
        pe_max += 1
    ax.set_ylim(pe_min * 0.985, pe_max * 1.015)
    ax.set_yticks(np.linspace(pe_min, pe_max, 5))
    ax.yaxis.set_major_formatter(FormatStrFormatter("%.2f"))
    for label in ax.get_yticklabels():
        label.set_fontsize(FONT_SIZES["y_tick"])
        label.set_color(PALETTE["text_muted"])

    first_date = pd.Timestamp(dates.iloc[0])
    last_date = pd.Timestamp(dates.iloc[-1])
    min_gap = pd.Timedelta(days=45)
    year_ticks = [
        pd.Timestamp(year=year, month=1, day=1)
        for year in range(first_date.year + 1, last_date.year + 1)
    ]
    year_ticks = [
        tick for tick in year_ticks
        if (tick - first_date) >= min_gap and (last_date - tick) >= min_gap
    ]
    xtick_values = [first_date, *year_ticks, last_date]
    xtick_labels = [
        first_date.strftime("%Y-%m-%d"),
        *(tick.strftime("%Y") for tick in year_ticks),
        last_date.strftime("%Y-%m-%d"),
    ]
    ax.set_xticks(xtick_values)
    ax.set_xticklabels(xtick_labels)
    ax.minorticks_off()
    for label in ax.get_xticklabels():
        label.set_fontsize(FONT_SIZES["x_tick"])
        label.set_color(PALETTE["text_muted"])


def _draw_footer(ax, data: Dict) -> None:
    ax.set_axis_off()
    text = f"数据源：易方达估值中心 + 指数详情接口 · 生成时间 {md.now_in_beijing().strftime('%Y-%m-%d %H:%M')}"
    if data["footnote"]:
        text = f"{text} · {data['footnote']}"
    ax.text(
        0.00,
        0.20,
        text,
        transform=ax.transAxes,
        fontsize=FONT_SIZES["footer"],
        color=PALETTE["text_muted"],
        ha="left",
        va="bottom",
    )


def _build_figure(target: Dict, data: Dict) -> Figure:
    del target
    plt.rcParams["font.sans-serif"] = pick_available_font_family()
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["axes.unicode_minus"] = False

    fig = plt.figure(figsize=FIGURE_SIZE, dpi=FIGURE_DPI, facecolor=PALETTE["background"])
    chart_ax = fig.add_axes(AX_BOUNDS["chart"])
    footer_ax = fig.add_axes(AX_BOUNDS["footer"])

    _draw_main_chart(chart_ax, data)
    _draw_footer(footer_ax, data)
    return fig


def generate_valuation_percentile_chart(target: Dict, output_dir: Path) -> Optional[Path]:
    data = _prepare_chart_data(target)
    if data is None:
        return None

    fig = _build_figure(target, data)
    output_dir.mkdir(parents=True, exist_ok=True)
    index_code = str(data["item"].get("index_code") or data["item"].get("code") or "").strip()
    output_path = output_dir / f"valuation_percentile_{index_code}.png"
    fig.savefig(
        output_path,
        dpi=FIGURE_DPI,
        facecolor=PALETTE["background"],
        edgecolor="none",
    )
    plt.close(fig)
    return output_path
