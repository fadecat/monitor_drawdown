from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.ticker import FormatStrFormatter
import numpy as np
import pandas as pd

import monitor_drawdown as md


FIGURE_DPI = 180
FIGURE_SIZE = (14, 7.8)
PREFERRED_CJK_FONTS = [
    "Noto Sans CJK SC",
    "Noto Sans CJK JP",
    "Microsoft YaHei",
    "SimHei",
    "PingFang SC",
    "WenQuanYi Zen Hei",
]
AX_BOUNDS = {
    "header": [0.04, 0.80, 0.92, 0.17],
    "metrics": [0.04, 0.68, 0.92, 0.09],
    "chart": [0.07, 0.10, 0.90, 0.52],
    "footer": [0.04, 0.02, 0.92, 0.04],
}
PALETTE = {
    "background": "#ffffff",
    "orange": "#ed7c2b",
    "orange_soft": "#ef8a3f",
    "text_primary": "#1f1f1f",
    "text_metric": "#242424",
    "text_muted": "#8a8a8a",
    "divider": "#ececec",
    "grid": "#f0f0f0",
    "spine": "#d0d0d0",
    "pct_low": "#2f9e4f",
    "pct_mid": "#9aa0a6",
    "pct_high": "#d94f3a",
    "level_low": "#2f9e4f",
    "level_belowmid": "#6fbf73",
    "level_mid": "#9aa0a6",
    "level_abovemid": "#e89b3b",
    "level_high": "#d94f3a",
}
FONT_SIZES = {
    "index_name": 26,
    "index_name_medium": 22,
    "index_name_small": 20,
    "lead": 13,
    "level": 26,
    "pe_label": 12,
    "headline_value": 22,
    "metric_label": 12,
    "metric_value": 18,
    "legend": 12,
    "main_title": 14,
    "y_tick": 10,
    "x_tick": 11,
    "latest_label": 11,
    "footer": 9,
    "window_note": 9,
}
WINDOW_LABELS = {"1Y": "近1年", "3Y": "近3年", "5Y": "近5年", "10Y": "近10年"}
LEVEL_ORDER = {
    10: ("估值极低", PALETTE["level_low"]),
    30: ("估值偏低", PALETTE["level_belowmid"]),
    50: ("估值合理", PALETTE["level_mid"]),
    70: ("估值偏高", PALETTE["level_abovemid"]),
    90: ("估值极高", PALETTE["level_high"]),
}


def pick_available_font_family() -> list[str]:
    available = {font.name for font in font_manager.fontManager.ttflist}
    selected = [name for name in PREFERRED_CJK_FONTS if name in available]
    return selected + ["DejaVu Sans"]


def classify_level_by_percentile(pct: float) -> tuple[str, str]:
    if pct < 20:
        return "估值极低", PALETTE["level_low"]
    if pct < 40:
        return "估值偏低", PALETTE["level_belowmid"]
    if pct < 60:
        return "估值合理", PALETTE["level_mid"]
    if pct < 80:
        return "估值偏高", PALETTE["level_abovemid"]
    return "估值极高", PALETTE["level_high"]


def _parse_float(value: object) -> Optional[float]:
    return md.parse_float(value)


def _format_number(value: object, suffix: str = "", decimals: int = 2) -> str:
    parsed = _parse_float(value)
    if parsed is None:
        return "-"
    return f"{parsed:.{decimals}f}{suffix}"


def _get_metric_block(item: Dict, metric_name: str) -> Dict:
    metrics = item.get("index_valuation_metrics")
    if not isinstance(metrics, dict):
        return {}
    metric = metrics.get(metric_name)
    return metric if isinstance(metric, dict) else {}


def _get_metric_current(item: Dict, metric_name: str) -> Optional[float]:
    return _parse_float(_get_metric_block(item, metric_name).get("current"))


def _get_metric_percentile(item: Dict, metric_name: str, label: str) -> Optional[float]:
    metric = _get_metric_block(item, metric_name)
    percentiles = metric.get("percentiles")
    if not isinstance(percentiles, dict):
        return None
    return _parse_float(percentiles.get(label))


def _pick_percentile_window(item: Dict, metric_name: str) -> Tuple[Optional[str], Optional[float]]:
    for label in ("5Y", "10Y", "3Y", "1Y"):
        value = _get_metric_percentile(item, metric_name, label)
        if value is not None:
            return label, value
    return None, None


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

    pct_label, pct_value = _pick_percentile_window(item, "PE(TTM)")
    pe_current = _get_metric_current(item, "PE(TTM)")
    if pct_label is None or pct_value is None or pe_current is None:
        return None

    history, footnote = _build_history_frame(item)
    if len(history) < 20:
        return None

    q30, q50, q70 = [float(value) for value in history["pe"].quantile([0.3, 0.5, 0.7]).tolist()]
    latest_date = pd.Timestamp(history["date"].iloc[-1])
    level_text, level_color = classify_level_by_percentile(pct_value)
    return {
        "item": item,
        "history": history,
        "pe_current": pe_current,
        "pct_label": pct_label,
        "pct_value": pct_value,
        "pb_current": _get_metric_current(item, "PB(LF)"),
        "pb_percentile": _get_metric_percentile(item, "PB(LF)", "5Y"),
        "dividend_yield": _parse_float(item.get("index_dividend_yield")),
        "q30": q30,
        "q50": q50,
        "q70": q70,
        "latest_date": latest_date,
        "level_text": level_text,
        "level_color": level_color,
        "lower_time_pct": 100.0 - pct_value,
        "window_note": "" if pct_label == "5Y" else f"分位窗口：{WINDOW_LABELS.get(pct_label, pct_label)}",
        "footnote": footnote,
    }


def _draw_header(ax, data: Dict) -> None:
    item = data["item"]
    latest_date = pd.Timestamp(data["latest_date"])
    pct_value = float(data["pct_value"])
    ax.set_axis_off()
    ax.text(
        0.00,
        0.55,
        "比过去",
        transform=ax.transAxes,
        fontsize=FONT_SIZES["lead"],
        color=PALETTE["text_muted"],
        ha="left",
        va="center",
    )
    ax.text(
        0.075,
        0.55,
        f"{data['lower_time_pct']:.2f}%",
        transform=ax.transAxes,
        fontsize=FONT_SIZES["lead"],
        color=PALETTE["orange"],
        ha="left",
        va="center",
    )
    ax.text(
        0.165,
        0.55,
        "的时间低",
        transform=ax.transAxes,
        fontsize=FONT_SIZES["lead"],
        color=PALETTE["text_muted"],
        ha="left",
        va="center",
    )
    ax.text(
        0.00,
        0.18,
        data["level_text"],
        transform=ax.transAxes,
        fontsize=FONT_SIZES["level"],
        fontweight="bold",
        color=data["level_color"],
        ha="left",
        va="bottom",
    )
    if data["window_note"]:
        ax.text(
            0.00,
            0.05,
            data["window_note"],
            transform=ax.transAxes,
            fontsize=FONT_SIZES["window_note"],
            color=PALETTE["text_muted"],
            ha="left",
            va="bottom",
        )

    ax.plot([0.30, 0.30], [0.12, 0.88], transform=ax.transAxes, color=PALETTE["divider"], linewidth=1)
    ax.text(
        0.35,
        0.72,
        f"PE {latest_date.strftime('%m-%d')}",
        transform=ax.transAxes,
        fontsize=FONT_SIZES["pe_label"],
        color=PALETTE["text_muted"],
        ha="left",
        va="center",
    )
    ax.text(
        0.35,
        0.30,
        f"{data['pe_current']:.2f}",
        transform=ax.transAxes,
        fontsize=FONT_SIZES["headline_value"],
        fontweight="semibold",
        color=PALETTE["text_primary"],
        ha="left",
        va="center",
    )
    ax.text(
        0.60,
        0.72,
        "PE百分位",
        transform=ax.transAxes,
        fontsize=FONT_SIZES["pe_label"],
        color=PALETTE["text_muted"],
        ha="left",
        va="center",
    )
    ax.text(
        0.60,
        0.30,
        f"{pct_value:.2f}%",
        transform=ax.transAxes,
        fontsize=FONT_SIZES["headline_value"],
        fontweight="semibold",
        color=PALETTE["text_primary"],
        ha="left",
        va="center",
    )


def _draw_metric_band(ax, data: Dict) -> None:
    cells = [
        ("PB", _format_number(data["pb_current"])),
        ("PB百分位", _format_number(data["pb_percentile"], suffix="%")),
        ("股息率", _format_number(data["dividend_yield"], suffix="%")),
    ]
    centers = [0.167, 0.500, 0.833]

    ax.set_axis_off()
    for divider_x in (0.333, 0.667):
        ax.plot([divider_x, divider_x], [0.15, 0.85], transform=ax.transAxes, color=PALETTE["divider"], linewidth=1)

    for (label, value), center_x in zip(cells, centers):
        ax.text(
            center_x,
            0.75,
            label,
            transform=ax.transAxes,
            fontsize=FONT_SIZES["metric_label"],
            color=PALETTE["text_muted"],
            ha="center",
            va="center",
        )
        ax.text(
            center_x,
            0.30,
            value,
            transform=ax.transAxes,
            fontsize=FONT_SIZES["metric_value"],
            color=PALETTE["text_metric"],
            ha="center",
            va="center",
        )


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
        linewidth=1.8,
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
    ax.scatter([dates.iloc[-1]], [pes.iloc[-1]], s=36, color=PALETTE["orange"], zorder=5)
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

    ax.set_xticks([dates.iloc[0], dates.iloc[-1]])
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
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
    header_ax = fig.add_axes(AX_BOUNDS["header"])
    metrics_ax = fig.add_axes(AX_BOUNDS["metrics"])
    chart_ax = fig.add_axes(AX_BOUNDS["chart"])
    footer_ax = fig.add_axes(AX_BOUNDS["footer"])

    for y in (0.78, 0.66):
        fig.add_artist(
            Line2D(
                [0.04, 0.96],
                [y, y],
                transform=fig.transFigure,
                color=PALETTE["divider"],
                linewidth=0.8,
            )
        )

    _draw_header(header_ax, data)
    _draw_metric_band(metrics_ax, data)
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
