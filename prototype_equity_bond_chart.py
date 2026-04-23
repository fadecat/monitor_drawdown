from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.offsetbox import AnchoredOffsetbox, HPacker, TextArea
from matplotlib.patches import Circle, FancyBboxPatch, Wedge
import pandas as pd

import monitor_drawdown as md


GAUGE_COLORS = ["#c5d9f0", "#dde6f2", "#f5e6d3", "#f4b9a0", "#d94f3a"]
BAND_COLORS = ["#dbe6f4", "#e8ebee", "#f5efe2", "#efc4ac", "#dc8772"]
LEVELS = ["极低", "较低", "适中", "较高", "极高"]
PREFERRED_CJK_FONTS = [
    "Noto Sans CJK SC",
    "Noto Sans CJK JP",
    "Microsoft YaHei",
    "SimHei",
    "PingFang SC",
    "WenQuanYi Zen Hei",
]


def pick_available_font_family() -> List[str]:
    available = {font.name for font in font_manager.fontManager.ttflist}
    selected = [name for name in PREFERRED_CJK_FONTS if name in available]
    return selected + ["DejaVu Sans"]


def pick_target_from_config(config_path: str) -> Dict:
    targets = md.load_config(config_path)
    for target in targets:
        if str(target.get("type", "")).strip().lower() == "valuation":
            return target
    raise RuntimeError("config.yaml 中未找到 type=valuation 的标的")


def classify_level(current: float, series: pd.Series) -> str:
    q20, q40, q60, q80 = series.quantile([0.2, 0.4, 0.6, 0.8]).tolist()
    if current <= q20:
        return "极低"
    if current <= q40:
        return "较低"
    if current <= q60:
        return "适中"
    if current <= q80:
        return "较高"
    return "极高"


def get_quantile_edges(series: pd.Series) -> Tuple[float, float, float, float]:
    q20, q40, q60, q80 = series.quantile([0.2, 0.4, 0.6, 0.8]).tolist()
    return float(q20), float(q40), float(q60), float(q80)


def level_to_category_and_advice(level: str) -> Tuple[str, str]:
    if level == "极低":
        return "债券", "可考虑加大配置债券"
    if level == "较低":
        return "债券", "可考虑偏向债券"
    if level == "适中":
        return "均衡", "可考虑平衡配置股债资产"
    if level == "较高":
        return "股票", "可考虑偏向股票"
    return "股票", "可考虑加大配置股票"


def build_metric_item(target: Dict) -> Dict:
    metrics = md.fetch_target_index_metrics(target)
    if not metrics:
        raise RuntimeError("未拉取到指数估值/股息率数据")

    item: Dict = {"name": target.get("name"), "code": target.get("code")}
    item.update(metrics)

    bond_yield = md.fetch_cn_10y_bond_yield()
    if bond_yield is None:
        raise RuntimeError("未拉取到 10Y 国债收益率")
    bond_history = md.fetch_cn_10y_bond_history()

    md.attach_equity_bond_ratio(item, bond_yield)
    md.attach_equity_bond_spread(item, bond_history)
    return item


def build_spread_history(item: Dict) -> pd.DataFrame:
    index_code = str(item.get("index_code") or item.get("code") or "").strip()
    valuation_url = str(item.get("index_valuation_percentile_source") or "").strip()
    pe_df = md.fetch_index_pe_history(index_code=index_code, url=valuation_url)
    bond_df = md.fetch_cn_10y_bond_history(lookback_years=11)
    merged = pd.merge(pe_df, bond_df, on="date", how="inner").dropna()
    merged = merged[merged["pe"] > 0].sort_values("date").reset_index(drop=True)
    if merged.empty:
        raise RuntimeError("股债序列为空")
    merged["spread"] = (1.0 / merged["pe"]) * 100.0 - merged["yield_pct"]
    latest = merged["date"].iloc[-1]
    start = latest - pd.DateOffset(years=5)
    merged = merged[merged["date"] >= start].copy()
    return merged.reset_index(drop=True)


def build_index_history(item: Dict, end_date: pd.Timestamp) -> pd.DataFrame:
    index_code = str(item.get("index_code") or item.get("code") or "").strip()
    start_date = (pd.Timestamp(end_date) - pd.DateOffset(years=5)).strftime("%Y%m%d")
    end_date_str = pd.Timestamp(end_date).strftime("%Y%m%d")
    raw = md.fetch_index_data(index_code, start_date, end_date_str)
    if raw.empty:
        raise RuntimeError("指数收盘价序列为空")
    out = raw[["date", "close"]].copy().sort_values("date").reset_index(drop=True)
    return out


def build_trend_frame(item: Dict) -> pd.DataFrame:
    spread_df = build_spread_history(item)
    index_df = build_index_history(item, spread_df["date"].iloc[-1])
    trend = pd.merge(spread_df[["date", "spread"]], index_df, on="date", how="inner").dropna()
    trend = trend.sort_values("date").reset_index(drop=True)
    if trend.empty:
        raise RuntimeError("股债与指数对齐后为空")
    trend = trend[trend["date"] >= trend["date"].iloc[-1] - pd.DateOffset(years=5)].copy()
    trend = trend.sort_values("date").reset_index(drop=True)
    return trend


def render_gauge(ax, current: float, series: pd.Series) -> None:
    q20, q40, q60, q80 = get_quantile_edges(series)
    vmin = float(series.min())
    vmax = float(series.max())
    bounds = [vmin, q20, q40, q60, q80, vmax]

    ax.set_aspect("equal")
    ax.axis("off")

    for i in range(5):
        left = bounds[i]
        right = bounds[i + 1]
        if right <= left:
            continue
        start_theta = 180 * (1 - (left - vmin) / (vmax - vmin))
        end_theta = 180 * (1 - (right - vmin) / (vmax - vmin))
        ax.add_patch(
            Wedge((0, 0), 1.0, end_theta, start_theta, width=0.25, facecolor=GAUGE_COLORS[i], edgecolor="white")
        )

    value_clamped = max(vmin, min(vmax, current))
    angle = math.pi * (1 - (value_clamped - vmin) / (vmax - vmin))
    needle_x = 0.72 * math.cos(angle)
    needle_y = 0.72 * math.sin(angle)
    ax.plot([0, needle_x], [0, needle_y], color="#b91c1c", linewidth=2.2)
    ax.add_patch(Circle((0, 0), 0.035, color="#b91c1c"))

    level = classify_level(current, series)
    ax.text(-1.05, -0.05, "债券", fontsize=11, color="#7a6f65", ha="left", va="center")
    ax.text(1.05, -0.05, "股票", fontsize=11, color="#7a6f65", ha="right", va="center")
    ax.text(0, 0.18, f"{current:+.2f}%", fontsize=17, fontweight="bold", color="#1f2937", ha="center")
    ax.set_xlim(-1.2, 1.2)
    ax.set_ylim(-0.55, 1.15)


def build_plot(item: Dict, trend: pd.DataFrame, output_path: Path) -> None:
    spread_current = float(trend["spread"].iloc[-1])
    spread_avg_5y = float(trend["spread"].mean())
    spread_pct_5y = float((trend["spread"] < spread_current).mean() * 100.0)
    level = classify_level(spread_current, trend["spread"])
    index_name = str(item.get("index_name") or item.get("name") or "").strip()
    target_name = str(item.get("name") or "").strip()
    index_code = str(item.get("index_code") or item.get("code") or "").strip()
    index_close = float(trend["close"].iloc[-1])
    relation = "高于" if spread_current > spread_avg_5y else "低于"
    category, advice = level_to_category_and_advice(level)

    plt.rcParams["font.sans-serif"] = pick_available_font_family()
    plt.rcParams["axes.unicode_minus"] = False

    fig = plt.figure(figsize=(960 / 180, 1360 / 180), dpi=180)
    fig.patch.set_facecolor("#faf7f4")
    gs = fig.add_gridspec(4, 1, height_ratios=[1.1, 0.75, 2.1, 0.25], hspace=0.42)

    banner_parts = [
        TextArea("当前「", textprops={"fontsize": 14, "color": "#374151"}),
        TextArea(category, textprops={"fontsize": 14, "color": "#d94f3a", "fontweight": "bold"}),
        TextArea(f"」性价比 {level}，{advice}", textprops={"fontsize": 14, "color": "#374151"}),
    ]
    banner_box = HPacker(children=banner_parts, align="center", pad=0, sep=0)
    anchored_banner = AnchoredOffsetbox(
        loc="upper left",
        child=banner_box,
        pad=0,
        borderpad=0,
        frameon=False,
        bbox_to_anchor=(0.04, 0.995),
        bbox_transform=fig.transFigure,
    )
    fig.add_artist(anchored_banner)

    top_gs = gs[0].subgridspec(1, 2, width_ratios=[1.05, 1.0], wspace=0.18)
    ax_gauge = fig.add_subplot(top_gs[0, 0])
    ax_gauge.set_facecolor("#faf7f4")
    render_gauge(ax_gauge, spread_current, trend["spread"])

    ax_top_text = fig.add_subplot(top_gs[0, 1])
    ax_top_text.set_facecolor("#faf7f4")
    ax_top_text.axis("off")
    ax_top_text.text(
        0.02,
        0.80,
        f"股债性价比 {level}",
        fontsize=19,
        fontweight="bold",
        color="#374151",
        ha="left",
    )
    ax_top_text.text(
        0.02,
        0.57,
        f"从近5年看，当前值 {spread_current:+.2f}%",
        fontsize=11.5,
        color="#6b6157",
        ha="left",
    )
    ax_top_text.text(
        0.02,
        0.43,
        f"位于近5年 {spread_pct_5y:.2f} 分位（{level}）",
        fontsize=11.5,
        color="#6b6157",
        ha="left",
    )

    ax_info = fig.add_subplot(gs[1, 0])
    ax_info.set_facecolor("#faf7f4")
    ax_info.axis("off")
    ax_info.text(0.01, 0.86, "股债性价比走势", fontsize=15, fontweight="bold", color="#2f2f2f", ha="left")
    ax_info.text(
        0.01,
        0.58,
        f"● 股债利差：{spread_current:.2f}%",
        fontsize=11.5,
        color="#d94f3a",
        ha="left",
        transform=ax_info.transAxes,
    )
    metric_label = target_name or index_code or str(item.get("code") or "").strip()
    ax_info.text(
        0.99,
        0.58,
        f"● {metric_label}：{index_close:,.2f}",
        fontsize=11.5,
        color="#3a7bd5",
        ha="right",
        transform=ax_info.transAxes,
    )
    decode_box = FancyBboxPatch(
        (0.01, 0.05),
        0.98,
        0.38,
        boxstyle="round,pad=0.012,rounding_size=0.02",
        linewidth=0.8,
        edgecolor="#efc9a8",
        facecolor="#fdecd4",
        transform=ax_info.transAxes,
    )
    ax_info.add_patch(decode_box)
    ax_info.text(
        0.03,
        0.23,
        (
            f"当前股债利差 {spread_current:+.2f}%，位于近5年 {spread_pct_5y:.2f} 分位（{level}），"
            f"{relation}过去5年均值 {spread_avg_5y:+.2f}%。"
        ),
        fontsize=11,
        color="#6b6157",
        ha="left",
        va="center",
        transform=ax_info.transAxes,
    )

    ax_left = fig.add_subplot(gs[2, 0])
    ax_right = ax_left.twinx()
    ax_left.set_facecolor("#faf7f4")
    ax_right.set_facecolor("#faf7f4")

    y_min = float(trend["spread"].min())
    y_max = float(trend["spread"].max())
    q20, q40, q60, q80 = get_quantile_edges(trend["spread"])
    band_bounds = [y_min, q20, q40, q60, q80, y_max]
    for i in range(5):
        lower = band_bounds[i]
        upper = band_bounds[i + 1]
        if upper > lower:
            ax_left.axhspan(lower, upper, color=BAND_COLORS[i], alpha=0.85, zorder=0)
            y_label = (lower + upper) / 2.0
            ax_left.text(
                0.012,
                y_label,
                LEVELS[i],
                fontsize=9,
                color="#8a7e74",
                alpha=0.75,
                ha="left",
                va="center",
                zorder=1,
                transform=ax_left.get_yaxis_transform(),
            )

    ax_left.plot(trend["date"], trend["spread"], color="#d94f3a", linewidth=1.4, zorder=3)
    ax_left.scatter(trend["date"].iloc[-1], trend["spread"].iloc[-1], color="#d94f3a", s=16, zorder=4)
    ax_left.set_ylabel("股债利差(%)", color="#d94f3a", fontsize=10.5)
    ax_left.tick_params(axis="y", colors="#d94f3a")
    ax_left.grid(axis="y", alpha=0.15)
    ax_left.grid(axis="x", visible=False)

    ax_right.plot(trend["date"], trend["close"], color="#3a7bd5", linewidth=1.4, zorder=2)
    ax_right.scatter(trend["date"].iloc[-1], trend["close"].iloc[-1], color="#3a7bd5", s=16, zorder=4)
    ax_right.set_ylabel("指数点位", color="#3a7bd5", fontsize=10.5)
    ax_right.tick_params(axis="y", colors="#3a7bd5")

    spread_pad = max((y_max - y_min) * 0.10, 0.35)
    ax_left.set_ylim(y_min - spread_pad, y_max + spread_pad)
    idx_min = float(trend["close"].min())
    idx_max = float(trend["close"].max())
    idx_pad = max((idx_max - idx_min) * 0.05, max(idx_max * 0.01, 1.0))
    ax_right.set_ylim(idx_min - idx_pad, idx_max + idx_pad)

    start_dt = trend["date"].iloc[0].strftime("%Y-%m-%d")
    end_dt = trend["date"].iloc[-1].strftime("%Y-%m-%d")
    ax_left.xaxis.set_major_locator(mdates.YearLocator(base=2))
    ax_left.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax_left.text(
        0,
        -0.12,
        f"{start_dt} 至 {end_dt}",
        transform=ax_left.transAxes,
        fontsize=9,
        color="#9a8f85",
        ha="left",
        va="top",
    )

    ax_legend = fig.add_subplot(gs[3, 0])
    ax_legend.set_facecolor("#faf7f4")
    ax_legend.axis("off")
    xpos = [0.08, 0.28, 0.48, 0.68, 0.88]
    for x, color, label in zip(xpos, BAND_COLORS, LEVELS):
        ax_legend.text(x, 0.52, "●", color=color, fontsize=12.5, ha="center", va="center")
        ax_legend.text(x + 0.03, 0.52, label, color="#6b6157", fontsize=10, ha="left", va="center")

    footnote = f"数据源：易方达估值中心 + AKShare 国债收益率 & 指数行情 · 生成时间 {pd.Timestamp.now().strftime('%Y-%m-%d')}"
    fig.text(0.012, 0.01, footnote, fontsize=9, color="#9a8f85")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)


def generate_equity_bond_chart(target: Dict, output_dir: Path) -> Optional[Path]:
    """
    为单个 valuation 标的生成股债性价比图。
    成功返回 PNG 路径，失败返回 None（不抛异常）。
    """
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        item = build_metric_item(target)
        trend = build_trend_frame(item)
        index_code = str(item.get("index_code") or target.get("code") or "unknown").strip()
        output_path = output_dir / f"equity_bond_prototype_{index_code}.png"
        build_plot(item, trend, output_path)
        return output_path
    except Exception as exc:  # noqa: BLE001
        print(f"[WARN] {target.get('name')} 图表生成失败: {exc}")
        return None


def main() -> int:
    config_path = os.getenv("CONFIG_PATH", "./config.yaml")
    targets = md.load_config(config_path)
    valuation_targets = [t for t in targets if str(t.get("type", "")).strip().lower() == "valuation"]
    if not valuation_targets:
        print("[ERROR] config.yaml 中无 type=valuation 标的")
        return 1

    output_dir = Path(".test_artifacts")
    successes: List[Path] = []
    failures: List[str] = []
    for target in valuation_targets:
        result = generate_equity_bond_chart(target, output_dir)
        if result is not None:
            successes.append(result)
        else:
            failures.append(str(target.get("name") or target.get("code") or "?"))

    print(f"[OK] 成功 {len(successes)}/{len(valuation_targets)}：")
    for path in successes:
        print(f"     {path}")
    if failures:
        print(f"[WARN] 失败 {len(failures)}：{', '.join(failures)}")
    return 0 if successes else 2


if __name__ == "__main__":
    raise SystemExit(main())
