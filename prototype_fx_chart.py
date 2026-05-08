from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Dict, Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.figure import Figure
from matplotlib.ticker import FormatStrFormatter
import pandas as pd

import akshare as ak


FIGURE_DPI = 180
FIGURE_SIZE = (14, 5.2)
DEFAULT_DAYS = 3650
DEFAULT_HIST_SYMBOL = "USDCNH"
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
    "line": "#ed7c2b",
    "text_primary": "#1f1f1f",
    "text_muted": "#8a8a8a",
    "grid": "#f0f0f0",
    "spine": "#d0d0d0",
}
FONT_SIZES = {
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


def _build_hist_df(symbol: str) -> pd.DataFrame:
    df = ak.forex_hist_em(symbol=symbol).copy()
    df["日期"] = pd.to_datetime(df["日期"], errors="coerce")
    df["市场价"] = pd.to_numeric(df["最新价"], errors="coerce")
    df = df[["日期", "代码", "名称", "市场价"]].dropna().sort_values("日期").reset_index(drop=True)
    return df


def _prepare_chart_data(days: int = DEFAULT_DAYS, hist_symbol: str = DEFAULT_HIST_SYMBOL) -> Optional[Dict]:
    hist_df = _build_hist_df(hist_symbol)
    if hist_df.empty:
        return None

    end_date = hist_df["日期"].max()
    start_date = end_date - timedelta(days=days)
    hist_recent = hist_df[hist_df["日期"] >= start_date].copy().reset_index(drop=True)
    if hist_recent.empty:
        return None

    latest_hist = float(hist_recent.iloc[-1]["市场价"])
    return {
        "hist_df": hist_recent,
        "hist_symbol": hist_symbol,
        "start_date": pd.Timestamp(start_date),
        "end_date": pd.Timestamp(end_date),
        "latest_hist": latest_hist,
        "hist_name": str(hist_recent.iloc[-1].get("名称") or hist_symbol),
    }


def _build_figure(data: Dict) -> Figure:
    plt.rcParams["font.sans-serif"] = pick_available_font_family()
    plt.rcParams["axes.unicode_minus"] = False

    fig = plt.figure(figsize=FIGURE_SIZE, dpi=FIGURE_DPI)
    fig.patch.set_facecolor(PALETTE["background"])

    chart_ax = fig.add_axes(AX_BOUNDS["chart"])
    footer_ax = fig.add_axes(AX_BOUNDS["footer"])

    chart_ax.set_facecolor(PALETTE["background"])
    chart_ax.grid(True, axis="y", color=PALETTE["grid"], linewidth=0.8, alpha=1.0)
    chart_ax.grid(False, axis="x")
    chart_ax.spines["top"].set_visible(False)
    chart_ax.spines["right"].set_visible(False)
    chart_ax.spines["left"].set_color(PALETTE["spine"])
    chart_ax.spines["left"].set_linewidth(0.8)
    chart_ax.spines["bottom"].set_color(PALETTE["spine"])
    chart_ax.spines["bottom"].set_linewidth(0.8)
    chart_ax.tick_params(axis="both", which="both", length=0, colors=PALETTE["text_muted"])

    hist_df = data["hist_df"]
    hist_symbol = data["hist_symbol"]
    dates = pd.to_datetime(hist_df["日期"])
    prices = hist_df["市场价"].astype(float)

    chart_ax.text(
        0.00,
        1.08,
        f"{hist_symbol} 市场价走势",
        transform=chart_ax.transAxes,
        fontsize=FONT_SIZES["main_title"],
        fontweight="bold",
        color=PALETTE["text_primary"],
        ha="left",
        va="baseline",
    )
    chart_ax.plot(
        dates,
        prices,
        color=PALETTE["line"],
        linewidth=1.2,
        solid_joinstyle="round",
        solid_capstyle="round",
    )
    chart_ax.scatter([dates.iloc[-1]], [prices.iloc[-1]], s=36, color=PALETTE["line"], zorder=5)
    chart_ax.annotate(
        f"{prices.iloc[-1]:.4f}",
        xy=(dates.iloc[-1], prices.iloc[-1]),
        xytext=(6, 6),
        textcoords="offset points",
        color=PALETTE["line"],
        fontsize=FONT_SIZES["latest_label"],
        fontweight="bold",
    )

    price_min = float(prices.min())
    price_max = float(prices.max())
    if price_min == price_max:
        price_min -= 0.01
        price_max += 0.01
    pad = max((price_max - price_min) * 0.05, 0.01)
    chart_ax.set_ylim(price_min - pad, price_max + pad)
    chart_ax.yaxis.set_major_formatter(FormatStrFormatter("%.2f"))
    for label in chart_ax.get_yticklabels():
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
    chart_ax.set_xticks(xtick_values)
    chart_ax.set_xticklabels(xtick_labels)
    chart_ax.minorticks_off()
    for label in chart_ax.get_xticklabels():
        label.set_fontsize(FONT_SIZES["x_tick"])
        label.set_color(PALETTE["text_muted"])

    footer_ax.axis("off")
    footer_ax.text(
        0.0,
        0.50,
        f"区间: {data['start_date'].date()} ~ {data['end_date'].date()}    最新值: {data['latest_hist']:.4f}    数据来源: AKShare · forex_hist_em",
        ha="left",
        va="center",
        fontsize=FONT_SIZES["footer"],
        color=PALETTE["text_muted"],
    )
    return fig


def generate_fx_chart(
    output_dir: Path,
    *,
    days: int = DEFAULT_DAYS,
    hist_symbol: str = DEFAULT_HIST_SYMBOL,
    slug: str = "fx_usd_cny_vs_mid_10y",
) -> Optional[Path]:
    data = _prepare_chart_data(days=days, hist_symbol=hist_symbol)
    if data is None:
        return None

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{slug}.png"
    fig = _build_figure(data)
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)
    return output_path
