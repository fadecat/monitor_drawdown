from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.ticker import FuncFormatter


DEFAULT_COLORS = [
    "#1558D6",
    "#6BA6FF",
    "#D69A00",
    "#F3B55D",
    "#E35B1F",
    "#F08B57",
]

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


def parse_display_return(value: str) -> float:
    return float(value.replace("%", ""))


def configure_matplotlib_fonts() -> None:
    available = {font.name for font in font_manager.fontManager.ttflist}
    selected = [name for name in PREFERRED_FONT_FAMILIES if name in available]
    if selected:
        plt.rcParams["font.sans-serif"] = selected + ["DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False


def build_one_month_chart_series(
    table_rows: list[dict[str, str]],
    curve_payloads: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    series: list[dict[str, Any]] = []
    for index, row in enumerate(table_rows):
        code = row["code"]
        curve = curve_payloads.get(code) or []
        if not curve:
            continue
        points = [
            {
                "date": datetime.strptime(item["date"], "%Y-%m-%d"),
                "return_pct": float(item["return_pct"]),
            }
            for item in curve
        ]
        series.append(
            {
                "name": row["name"],
                "code": code,
                "color": DEFAULT_COLORS[index % len(DEFAULT_COLORS)],
                "points": points,
                "last_return_pct": float(points[-1]["return_pct"]),
                "display_return": row["return_1m"],
            }
        )
    series.sort(key=lambda item: item["last_return_pct"])
    return series


def compute_label_positions(values: list[float], min_gap: float = 0.35) -> list[float]:
    if not values:
        return []

    indexed = sorted(enumerate(values), key=lambda item: item[1])
    adjusted = []
    previous = None
    for original_index, value in indexed:
        new_value = value if previous is None else max(value, previous + min_gap)
        adjusted.append((original_index, new_value))
        previous = new_value

    adjusted.sort(key=lambda item: item[0])
    return [value for _, value in adjusted]


def build_tail_label_text(item: dict[str, Any]) -> str:
    return f"{item['name']} {item['display_return']}"


def generate_one_month_return_chart(
    table_rows: list[dict[str, str]],
    curve_payloads: dict[str, list[dict[str, Any]]],
    output_dir: Path = Path(".email_chart_cache"),
) -> Path:
    configure_matplotlib_fonts()
    series = build_one_month_chart_series(table_rows, curve_payloads)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "one_month_return_chart.png"

    fig, ax = plt.subplots(figsize=(14, 7), dpi=150)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    for item in series:
        x_values = [point["date"] for point in item["points"]]
        y_values = [point["return_pct"] for point in item["points"]]
        ax.plot(
            x_values,
            y_values,
            linewidth=2.2,
            color=item["color"],
            label=item["name"],
            solid_capstyle="round",
        )

    all_values = [item["last_return_pct"] for item in series]
    label_positions = compute_label_positions(all_values, min_gap=0.65)
    x_last = max(point["date"] for item in series for point in item["points"])
    x_text = x_last + (x_last - min(point["date"] for item in series for point in item["points"])) / 18

    for item, label_y in zip(series, label_positions):
        end_point = item["points"][-1]
        ax.plot(
            [end_point["date"], x_text],
            [end_point["return_pct"], label_y],
            color=item["color"],
            linewidth=0.9,
            alpha=0.7,
        )
        ax.text(
            x_text,
            label_y,
            build_tail_label_text(item),
            color=item["color"],
            fontsize=10,
            va="center",
            ha="left",
            fontweight="bold",
        )

    y_all = [point["return_pct"] for item in series for point in item["points"]]
    y_min = min(y_all)
    y_max = max(y_all)
    y_margin = max((y_max - y_min) * 0.15, 1.5)
    ax.set_ylim(y_min - y_margin, y_max + y_margin)

    ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=4, maxticks=6))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:.2f}%"))
    ax.grid(axis="y", color="#D9DDE4", linewidth=0.8)
    ax.grid(axis="x", visible=False)

    ax.set_title("近1月收益率", fontsize=18, fontweight="bold", pad=18)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#D0D7E2")
    ax.spines["bottom"].set_color("#D0D7E2")
    ax.tick_params(axis="x", labelrotation=0, labelsize=9, colors="#4C5563")
    ax.tick_params(axis="y", labelsize=10, colors="#4C5563")

    legend = ax.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, -0.08),
        ncol=min(3, max(1, len(series))),
        frameon=False,
        fontsize=9,
    )
    for line in legend.get_lines():
        line.set_linewidth(3)

    plt.tight_layout(rect=(0.03, 0.05, 0.97, 0.98))
    fig.savefig(output_path, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    return output_path
