from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.ticker import FuncFormatter
import pandas as pd


PREFERRED_CJK_FONTS = [
    "Noto Sans CJK SC",
    "Noto Sans CJK JP",
    "Microsoft YaHei",
    "SimHei",
    "PingFang SC",
    "WenQuanYi Zen Hei",
    "Source Han Sans SC",
    "Arial Unicode MS",
]

FIGURE_SIZE = (13.5, 6.2)
FIGURE_DPI = 180
POSITIVE_FILL = "#f6c1bb"
NEGATIVE_FILL = "#c9e8d0"
SPREAD_LINE = "#111111"
SPREAD_LINE_WIDTH = 1.6 / 3
ZERO_LINE = "#7a7a7a"
LATEST_X_AXIS_LABEL_COLOR = "#111111"


def _is_supported_series_like(value: Any) -> bool:
    if isinstance(value, (str, bytes)):
        return False
    return hasattr(value, "__iter__") and hasattr(value, "__len__")


def get_available_cjk_fonts() -> list[str]:
    available = {font.name for font in font_manager.fontManager.ttflist}
    return [name for name in PREFERRED_CJK_FONTS if name in available]


def configure_matplotlib_fonts() -> None:
    selected = get_available_cjk_fonts()
    if not selected:
        raise RuntimeError("未找到可用中文字体，请安装至少一种首选中文字体")
    plt.rcParams["font.sans-serif"] = selected + ["DejaVu Sans"]
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["axes.unicode_minus"] = False


def _extract_series(payload: dict[str, Any]) -> tuple[pd.DatetimeIndex, pd.Series]:
    if not isinstance(payload, Mapping):
        raise ValueError("payload must be a mapping")

    series = payload.get("series")
    if series is None:
        series = {}
    if not isinstance(series, Mapping):
        raise ValueError("payload['series'] must be a mapping")

    raw_dates = series["dates"] if "dates" in series else []
    raw_spread = series["spread"] if "spread" in series else []

    if not _is_supported_series_like(raw_dates):
        raise ValueError("series['dates'] must be a sequence")
    if not _is_supported_series_like(raw_spread):
        raise ValueError("series['spread'] must be a sequence")
    if len(raw_dates) != len(raw_spread):
        raise ValueError("series['dates'] and series['spread'] length mismatch")

    dates = pd.to_datetime(list(raw_dates), errors="coerce")
    spread = pd.to_numeric(list(raw_spread), errors="coerce")
    if pd.isna(dates).any():
        raise ValueError("series['dates'] contains invalid date values")
    if pd.isna(spread).any():
        raise ValueError("series['spread'] contains invalid numeric values")

    frame = pd.DataFrame({"date": dates, "spread": spread})
    frame = frame.sort_values("date").drop_duplicates(subset=["date"], keep="last").reset_index(drop=True)
    if frame.empty:
        raise ValueError("style rotation payload has no valid spread data")
    return pd.DatetimeIndex(frame["date"]), frame["spread"]


def _build_chart_title(meta: Mapping[str, Any]) -> str:
    left_name = str(meta.get("left_name") or "左侧标的").strip()
    right_name = str(meta.get("right_name") or "右侧标的").strip()
    left_symbol = str(meta.get("left_symbol") or "").strip()
    right_symbol = str(meta.get("right_symbol") or "").strip()
    left_label = f"{left_name}({left_symbol})" if left_symbol else left_name
    right_label = f"{right_name}({right_symbol})" if right_symbol else right_name
    return f"风格轮动收益率差值（{left_label} vs {right_label}）"


def _build_footer_text(payload: Mapping[str, Any]) -> str:
    dates, spread = _extract_series(payload)
    latest_date_dt = dates[-1].to_pydatetime()
    latest_date = f"{latest_date_dt.year}年{latest_date_dt.month}月{latest_date_dt.day}日"
    latest_spread = float(spread.iloc[-1])
    return f"最新日期：{latest_date}    最新差值：{latest_spread:.2f}%"


def _build_latest_x_axis_label(payload: Mapping[str, Any]) -> str:
    dates, _ = _extract_series(payload)
    return dates[-1].strftime("%Y-%m-%d")


def _hide_matching_x_tick_labels(labels: list[str], target_label: str) -> list[str]:
    output = list(labels)
    for index, label in enumerate(output):
        if label == target_label:
            output[index] = ""
    return output


def _hide_matching_tick_label_objects(tick_labels: list[Any], target_label: str) -> None:
    for tick_label in tick_labels:
        if tick_label.get_text() == target_label:
            tick_label.set_visible(False)


def _hide_last_x_tick_label(labels: list[str]) -> list[str]:
    if not labels:
        return labels
    output = list(labels)
    output[-1] = ""
    return output


def _hide_last_tick_label_objects(tick_labels: list[Any]) -> None:
    if not tick_labels:
        return
    tick_labels[-1].set_visible(False)


def generate_style_rotation_chart(payload: dict[str, Any], output_dir: Path) -> Path:
    configure_matplotlib_fonts()

    dates, spread = _extract_series(payload)
    meta = payload.get("meta")
    if meta is None:
        meta = {}
    if not isinstance(meta, Mapping):
        raise ValueError("payload['meta'] must be a mapping")

    title = _build_chart_title(meta)
    footer_text = _build_footer_text(payload)
    latest_x_axis_label = _build_latest_x_axis_label(payload)

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "style_rotation_preview.png"

    fig, ax = plt.subplots(figsize=FIGURE_SIZE, dpi=FIGURE_DPI)
    try:
        fig.patch.set_facecolor("white")
        ax.set_facecolor("white")

        x_values = dates.to_pydatetime()
        y_values = spread.astype(float).tolist()
        y_zero = [0.0] * len(y_values)

        ax.fill_between(
            x_values,
            y_values,
            y_zero,
            where=[value >= 0 for value in y_values],
            interpolate=True,
            color=POSITIVE_FILL,
            alpha=0.95,
        )
        ax.fill_between(
            x_values,
            y_values,
            y_zero,
            where=[value < 0 for value in y_values],
            interpolate=True,
            color=NEGATIVE_FILL,
            alpha=0.95,
        )
        ax.plot(
            x_values,
            y_values,
            color=SPREAD_LINE,
            linewidth=SPREAD_LINE_WIDTH,
            solid_capstyle="round",
            solid_joinstyle="round",
        )
        ax.axhline(0, color=ZERO_LINE, linestyle=(0, (4, 4)), linewidth=1.1)

        ax.set_title(
            title,
            fontsize=18,
            fontweight="bold",
            pad=16,
        )

        ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=4, maxticks=7))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
        ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:.2f}%"))
        fig.canvas.draw()
        _hide_matching_tick_label_objects(list(ax.get_xticklabels()), latest_x_axis_label)

        y_min = min(y_values)
        y_max = max(y_values)
        y_span = max(y_max - y_min, 1.0)
        y_margin = max(y_span * 0.18, 0.8)
        ax.set_ylim(y_min - y_margin, y_max + y_margin)

        ax.grid(axis="y", color="#E5E7EB", linewidth=0.8)
        ax.grid(axis="x", visible=False)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color("#D0D7E2")
        ax.spines["bottom"].set_color("#D0D7E2")
        ax.tick_params(axis="x", labelrotation=0, labelsize=9, colors="#4C5563")
        ax.tick_params(axis="y", labelsize=10, colors="#4C5563")
        ax.text(
            0.998,
            -0.02,
            latest_x_axis_label,
            transform=ax.transAxes,
            ha="right",
            va="top",
            fontsize=9,
            color=LATEST_X_AXIS_LABEL_COLOR,
        )

        fig.text(
            0.5,
            0.02,
            footer_text,
            ha="center",
            va="bottom",
            fontsize=11,
            color="#4C5563",
        )

        plt.tight_layout(rect=(0.02, 0.06, 0.98, 0.96))
        fig.savefig(output_path, facecolor="white", bbox_inches="tight")
        return output_path
    finally:
        plt.close(fig)
