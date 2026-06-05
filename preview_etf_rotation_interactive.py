from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any

import run_etf_rotation_strategy as runner


DEFAULT_OUTPUT_PATH = Path(
    ".test_artifacts/etf_rotation_backtest/interactive_rotation_preview.html"
)
DEFAULT_BACKTEST_OUTPUT_ROOT = Path(".test_artifacts/etf_rotation_backtest")

SERIES_COLORS = [
    "#111111",
    "#7A7A7A",
    "#C0392B",
    "#0F8B8D",
    "#6C5CE7",
    "#D68910",
    "#1F618D",
    "#117A65",
    "#AF601A",
    "#7D3C98",
]


def _clean_float(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric):
        return None
    return numeric


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _normalize_series_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in records:
        date_text = str(row.get("date") or "").strip()
        close_value = _clean_float(row.get("close"))
        if not date_text or close_value is None:
            continue
        normalized.append({"date": date_text, "close": close_value})
    return sorted(normalized, key=lambda item: item["date"])


def build_aligned_normalized_series(
    plot_dates: list[str],
    series_records: list[dict[str, Any]],
    start_date: str,
) -> list[float | None]:
    normalized_records = _normalize_series_records(series_records)
    if not plot_dates or not normalized_records:
        return [None for _ in plot_dates]

    base_close: float | None = None
    current_close: float | None = None
    cursor = 0
    while cursor < len(normalized_records) and normalized_records[cursor]["date"] <= start_date:
        current_close = float(normalized_records[cursor]["close"])
        base_close = current_close
        cursor += 1

    if base_close is None or base_close <= 0:
        return [None for _ in plot_dates]

    values: list[float | None] = []
    for plot_date in plot_dates:
        while cursor < len(normalized_records) and normalized_records[cursor]["date"] <= plot_date:
            current_close = float(normalized_records[cursor]["close"])
            cursor += 1
        if current_close is None or current_close <= 0:
            values.append(None)
            continue
        values.append(round(current_close / base_close, 12))
    return values


def _normalize_trade_rows(
    rows: list[dict[str, str]],
    daily_positions: list[dict[str, str]],
) -> list[dict[str, Any]]:
    position_date_by_signal = {
        str(row.get("signal_date") or "").strip(): str(row.get("date") or "").strip()
        for row in daily_positions
        if str(row.get("signal_date") or "").strip() and str(row.get("date") or "").strip()
    }
    normalized: list[dict[str, Any]] = []
    for row in rows:
        signal_date = str(row.get("signal_date") or "").strip()
        if not signal_date:
            continue
        normalized.append(
            {
                "signal_date": signal_date,
                "position_date": position_date_by_signal.get(signal_date, signal_date),
                "from_symbol": str(row.get("from_symbol") or "").strip(),
                "from_name": str(row.get("from_name") or "").strip(),
                "to_symbol": str(row.get("to_symbol") or "").strip(),
                "to_name": str(row.get("to_name") or "").strip(),
                "reason": str(row.get("reason") or "").strip(),
                "from_20d_return": _clean_float(row.get("from_20d_return")),
                "to_20d_return": _clean_float(row.get("to_20d_return")),
                "rank_1_symbol": str(row.get("rank_1_symbol") or "").strip(),
            }
        )
    return normalized


def _normalize_holding_period_rows(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        start_date = str(row.get("start_date") or "").strip()
        end_date = str(row.get("end_date") or "").strip()
        if not start_date or not end_date:
            continue
        symbol = str(row.get("symbol") or "").strip() or "CASH"
        name = str(row.get("name") or "").strip() or "空仓"
        normalized.append(
            {
                "start_date": start_date,
                "end_date": end_date,
                "symbol": symbol,
                "name": name,
                "holding_days": int(row.get("holding_days") or 0),
                "period_return": _clean_float(row.get("period_return")) or 0.0,
                "contribution_to_total_return": _clean_float(
                    row.get("contribution_to_total_return")
                )
                or 0.0,
                "max_drawdown_during_holding": _clean_float(
                    row.get("max_drawdown_during_holding")
                )
                or 0.0,
            }
        )
    return normalized


def load_interactive_rotation_payload(
    config_path: Path | str = runner.DEFAULT_CONFIG_PATH,
    source_output_root: Path | str = runner.SOURCE_OUTPUT_ROOT,
    backtest_output_root: Path | str = DEFAULT_BACKTEST_OUTPUT_ROOT,
) -> dict[str, Any]:
    config = runner.load_rotation_config(config_path)
    resolved_source_root = Path(source_output_root)
    resolved_backtest_root = Path(backtest_output_root)
    daily_positions_path = resolved_backtest_root / "daily_positions.csv"
    if not daily_positions_path.exists():
        raise FileNotFoundError(
            f"missing backtest artifact: {daily_positions_path}"
        )

    daily_positions = _read_csv_rows(daily_positions_path)
    plot_dates = [
        str(row.get("date") or "").strip()
        for row in daily_positions
        if str(row.get("date") or "").strip()
    ]
    strategy_values = [
        round(float(row["strategy_nav"]), 12)
        for row in daily_positions
        if str(row.get("date") or "").strip()
    ]
    if not plot_dates or not strategy_values:
        raise ValueError("daily_positions.csv has no usable rows")

    start_date = plot_dates[0]
    end_date = plot_dates[-1]
    symbol_colors: dict[str, str] = {"CASH": "#B7ADA1"}
    series: list[dict[str, Any]] = [
        {
            "id": "strategy_nav",
            "name": "策略净值",
            "values": strategy_values,
            "color": SERIES_COLORS[0],
            "width": 2.6,
        },
        {
            "id": "baseline",
            "name": "静止线",
            "values": [1.0 for _ in plot_dates],
            "color": SERIES_COLORS[1],
            "width": 1.4,
            "dash": "7 5",
        },
    ]

    targets = list(config.get("targets") or []) + list(config.get("defensive_targets") or [])
    for index, target in enumerate(targets, start=2):
        label = str(target.get("label") or "").strip()
        code = str(target.get("code") or "").strip()
        kind = str(target.get("kind") or "").strip()
        if not label or not code or not kind:
            continue
        selected_primary = {"label": label, "code": code, "kind": kind, "name": label}
        series_records = runner.load_series_records(
            selected_primary=selected_primary,
            source_output_root=resolved_source_root,
        )
        color = SERIES_COLORS[index % len(SERIES_COLORS)]
        symbol_colors[code] = color
        series.append(
            {
                "id": f"{kind}_{code}",
                "name": label,
                "symbol": code,
                "values": build_aligned_normalized_series(
                    plot_dates=plot_dates,
                    series_records=series_records,
                    start_date=start_date,
                ),
                "color": color,
                "width": 1.6,
            }
        )

    trades_path = resolved_backtest_root / "trades.csv"
    holding_periods_path = resolved_backtest_root / "holding_periods.csv"
    trades = (
        _normalize_trade_rows(_read_csv_rows(trades_path), daily_positions)
        if trades_path.exists()
        else []
    )
    holding_periods = (
        _normalize_holding_period_rows(_read_csv_rows(holding_periods_path))
        if holding_periods_path.exists()
        else []
    )

    return {
        "meta": {
            "title": "ETF轮动策略交互预览",
            "start_date": start_date,
            "end_date": end_date,
            "notes": [
                "策略净值来自已生成的回测结果。",
                "标的曲线仅用于显示对齐：从回测起点归一化到 1.0，并对缺失交易日做前值延续。",
                "主图区支持滚轮缩放、拖动平移，底部滑块可快速切窗。",
                "底部持仓时间带展示每段持仓，主图调仓点可查看换仓原因和切换前后20日涨幅。",
                "主图区浅色背景表示持仓阶段，阶段收益标签展示完整持仓段收益。",
                "legend 单击标的可聚焦对应曲线与持仓阶段，Shift+单击保留显隐。",
            ],
        },
        "dates": plot_dates,
        "series": series,
        "trades": trades,
        "holding_periods": holding_periods,
        "symbol_colors": symbol_colors,
    }


def render_interactive_rotation_html(payload: dict[str, Any]) -> str:
    meta = payload.get("meta") or {}
    title = str(meta.get("title") or "ETF轮动策略交互预览").strip()
    notes = meta.get("notes") or []
    notes_html = "".join(
        f"<li>{str(note)}</li>"
        for note in notes
        if str(note).strip()
    )
    payload_json = json.dumps(payload, ensure_ascii=False)

    html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>__TITLE__</title>
  <style>
    :root {
      --bg: #f5f3ee;
      --card: #fffdf8;
      --ink: #171411;
      --muted: #6e665c;
      --grid: #e3ddd3;
      --accent: #9f7a34;
      --border: #d6cec1;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      padding: 24px;
      font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, #efe2bf 0, transparent 32%),
        linear-gradient(180deg, #f7f4ee 0%, #f1ede5 100%);
    }
    .wrap {
      max-width: 1320px;
      margin: 0 auto;
    }
    .card {
      background: rgba(255, 253, 248, 0.96);
      border: 1px solid var(--border);
      border-radius: 20px;
      box-shadow: 0 14px 36px rgba(55, 43, 29, 0.08);
      overflow: hidden;
    }
    .head {
      padding: 24px 28px 12px;
      border-bottom: 1px solid rgba(214, 206, 193, 0.7);
    }
    h1 {
      margin: 0;
      font-size: 30px;
      line-height: 1.1;
      letter-spacing: 0.02em;
    }
    .sub {
      margin-top: 10px;
      color: var(--muted);
      font-size: 14px;
    }
    .notes {
      margin: 14px 0 0;
      padding-left: 20px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.55;
    }
    .controls {
      display: flex;
      flex-wrap: wrap;
      gap: 10px 14px;
      align-items: center;
      padding: 18px 28px 8px;
    }
    .buttons {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }
    button {
      border: 1px solid var(--border);
      background: #fff8eb;
      color: var(--ink);
      border-radius: 999px;
      padding: 8px 14px;
      cursor: pointer;
      font-size: 13px;
    }
    button:hover {
      border-color: #c19b4d;
      background: #fff2d8;
    }
    .toggle {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 13px;
      color: var(--muted);
    }
    .window-label {
      margin-left: auto;
      font-size: 13px;
      color: var(--muted);
      white-space: nowrap;
    }
    .legend {
      display: flex;
      flex-wrap: wrap;
      gap: 10px 14px;
      padding: 0 28px 10px;
    }
    .legend-item {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      border-radius: 999px;
      padding: 6px 10px;
      border: 1px solid rgba(214, 206, 193, 0.8);
      background: rgba(255, 250, 241, 0.9);
      cursor: pointer;
      user-select: none;
      font-size: 13px;
    }
    .legend-item.off {
      opacity: 0.45;
      text-decoration: line-through;
    }
    .legend-item.focused {
      border-color: #9f7a34;
      box-shadow: inset 0 0 0 1px rgba(159, 122, 52, 0.22);
      background: #fff3d8;
    }
    .legend-item.dimmed {
      opacity: 0.4;
    }
    .legend-swatch {
      width: 12px;
      height: 12px;
      border-radius: 999px;
      flex: 0 0 auto;
    }
    .series-item.dimmed {
      opacity: 0.18;
    }
    .series-item.focused {
      opacity: 1;
    }
    .phase-layer {
      opacity: 0.1;
    }
    .phase-layer.dimmed {
      opacity: 0.035;
    }
    .phase-layer.focused {
      opacity: 0.16;
    }
    .phase-strip {
      opacity: 0.2;
    }
    .phase-strip.dimmed {
      opacity: 0.08;
    }
    .phase-strip.focused {
      opacity: 0.34;
    }
    .phase-label {
      fill: #5e4832;
      font-size: 11px;
      font-weight: 600;
      letter-spacing: 0.01em;
    }
    .phase-label.dimmed {
      opacity: 0.32;
    }
    .holding-band-item.dimmed {
      opacity: 0.18;
    }
    .holding-band-item.focused {
      opacity: 0.92;
    }
    .holding-band-label.dimmed {
      opacity: 0.36;
    }
    .trade-item.dimmed {
      opacity: 0.12;
    }
    .trade-item.focused {
      opacity: 0.98;
    }
    .chart-wrap {
      position: relative;
      padding: 6px 20px 0;
    }
    #chart-svg {
      width: 100%;
      height: 580px;
      display: block;
    }
    .tooltip {
      position: absolute;
      min-width: 190px;
      max-width: 320px;
      pointer-events: none;
      background: rgba(23, 20, 17, 0.92);
      color: #fffdf8;
      border-radius: 14px;
      padding: 10px 12px;
      font-size: 12px;
      line-height: 1.5;
      box-shadow: 0 12px 30px rgba(23, 20, 17, 0.25);
      opacity: 0;
      transform: translate(10px, 10px);
      transition: opacity 120ms ease;
    }
    .tooltip strong {
      display: block;
      margin-bottom: 6px;
      color: #f6d99a;
      font-size: 12px;
    }
    .tooltip-row {
      display: flex;
      justify-content: space-between;
      gap: 12px;
    }
    .tooltip-name {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .slider-wrap {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px 18px;
      padding: 10px 28px 22px;
    }
    .holding-band-wrap {
      padding: 4px 20px 2px;
    }
    .holding-band-head {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      padding: 0 8px 6px;
      color: var(--muted);
      font-size: 12px;
    }
    .holding-band-head strong {
      color: var(--ink);
      font-size: 13px;
      font-weight: 600;
    }
    #holding-band {
      width: 100%;
      height: 120px;
      display: block;
    }
    .slider-group {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .slider-group label {
      font-size: 12px;
      color: var(--muted);
    }
    input[type="range"] {
      width: 100%;
      accent-color: var(--accent);
    }
    .foot {
      padding: 0 28px 24px;
      color: var(--muted);
      font-size: 12px;
    }
    @media (max-width: 860px) {
      body { padding: 14px; }
      h1 { font-size: 24px; }
      .controls { padding-top: 14px; }
      .window-label { width: 100%; margin-left: 0; }
      .slider-wrap { grid-template-columns: 1fr; }
      #chart-svg { height: 500px; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <div class="head">
        <h1>__TITLE__</h1>
        <div class="sub">区间：__START__ 到 __END__</div>
        <ul class="notes">__NOTES__</ul>
      </div>
      <div class="controls">
        <div class="buttons">
          <button type="button" data-window="all">全部</button>
          <button type="button" data-window="5y">近5年</button>
          <button type="button" data-window="3y">近3年</button>
          <button type="button" data-window="1y">近1年</button>
        </div>
        <label class="toggle">
          <input id="toggle-log" type="checkbox">
          对数坐标
        </label>
        <div id="window-label" class="window-label"></div>
      </div>
      <div id="legend" class="legend"></div>
      <div class="chart-wrap">
        <svg id="chart-svg" viewBox="0 0 1200 580" preserveAspectRatio="none"></svg>
        <div id="tooltip" class="tooltip"></div>
      </div>
      <div class="holding-band-wrap">
        <div class="holding-band-head">
          <strong>持仓时间带</strong>
          <span>hover 查看阶段持仓收益与贡献</span>
        </div>
        <svg id="holding-band" viewBox="0 0 1200 120" preserveAspectRatio="none"></svg>
      </div>
      <div class="slider-wrap">
        <div class="slider-group">
          <label for="window-start">起始位置</label>
          <input id="window-start" type="range" min="0" max="0" value="0">
        </div>
        <div class="slider-group">
          <label for="window-end">结束位置</label>
          <input id="window-end" type="range" min="0" max="0" value="0">
        </div>
      </div>
      <div class="foot">操作：标的 legend 单击聚焦，Shift+单击显隐；滚轮 zoom，drag to pan，底部双滑块可精确切窗。主图区浅色背景表示当前持仓，阶段收益标签展示完整持仓段收益。</div>
    </div>
  </div>
  <script>
    const payload = __PAYLOAD_JSON__;
    const svg = document.getElementById("chart-svg");
    const holdingBand = document.getElementById("holding-band");
    const tooltip = document.getElementById("tooltip");
    const legend = document.getElementById("legend");
    const startSlider = document.getElementById("window-start");
    const endSlider = document.getElementById("window-end");
    const windowLabel = document.getElementById("window-label");
    const toggleLog = document.getElementById("toggle-log");
    const NS = "http://www.w3.org/2000/svg";
    const dates = payload.dates || [];
    const series = (payload.series || []).map((item) => ({
      ...item,
      visible: true,
      width: item.width || 1.5,
      dash: item.dash || "",
    }));
    const trades = payload.trades || [];
    const holdingPeriods = payload.holding_periods || [];
    const symbolColors = payload.symbol_colors || {};
    const minGap = Math.min(Math.max(dates.length > 1 ? 20 : 1, 1), Math.max(dates.length - 1, 1));
    const state = {
      start: 0,
      end: Math.max(dates.length - 1, 0),
      logScale: false,
      dragging: false,
      dragOriginX: 0,
      dragWindow: [0, 0],
      hoverIndex: null,
      plotBox: null,
      crosshair: null,
      focusSymbol: null,
    };

    function clamp(value, minValue, maxValue) {
      return Math.max(minValue, Math.min(maxValue, value));
    }

    function setWindow(start, end) {
      if (!dates.length) {
        state.start = 0;
        state.end = 0;
        return;
      }
      const maxIndex = dates.length - 1;
      let nextStart = clamp(Math.round(start), 0, maxIndex);
      let nextEnd = clamp(Math.round(end), 0, maxIndex);
      if (nextEnd - nextStart < minGap) {
        if (nextEnd >= maxIndex) {
          nextStart = clamp(nextEnd - minGap, 0, maxIndex);
        } else {
          nextEnd = clamp(nextStart + minGap, 0, maxIndex);
        }
      }
      state.start = clamp(nextStart, 0, maxIndex);
      state.end = clamp(nextEnd, state.start, maxIndex);
      if (state.end - state.start < minGap) {
        state.start = clamp(state.end - minGap, 0, maxIndex);
      }
      syncControls();
      render();
    }

    function applyPreset(windowName) {
      if (!dates.length) {
        return;
      }
      const maxIndex = dates.length - 1;
      if (windowName === "all") {
        setWindow(0, maxIndex);
        return;
      }
      const lookback = {
        "1y": 252,
        "3y": 252 * 3,
        "5y": 252 * 5,
      }[windowName] || maxIndex;
      setWindow(Math.max(0, maxIndex - lookback), maxIndex);
    }

    function syncControls() {
      const maxIndex = Math.max(dates.length - 1, 0);
      startSlider.max = String(maxIndex);
      endSlider.max = String(maxIndex);
      startSlider.value = String(state.start);
      endSlider.value = String(state.end);
      windowLabel.textContent = dates.length
        ? dates[state.start] + " -> " + dates[state.end] + "（" + (state.end - state.start + 1) + " 点）"
        : "无数据";
    }

    function buildLegend() {
      legend.innerHTML = "";
      series.forEach((item, index) => {
        const node = document.createElement("button");
        node.type = "button";
        node.className = "legend-item";
        node.dataset.index = String(index);
        if (item.symbol) {
          node.title = "单击聚焦，Shift+单击显隐";
        }
        const swatch = document.createElement("span");
        swatch.className = "legend-swatch";
        swatch.style.background = item.color;
        const label = document.createElement("span");
        label.textContent = item.name;
        node.appendChild(swatch);
        node.appendChild(label);
        node.addEventListener("click", (event) => {
          if (item.symbol && !event.shiftKey) {
            state.focusSymbol = state.focusSymbol === item.symbol ? null : item.symbol;
            updateLegendState();
            render();
            return;
          }
          item.visible = !item.visible;
          if (!item.visible && state.focusSymbol && item.symbol === state.focusSymbol) {
            state.focusSymbol = null;
          }
          render();
        });
        legend.appendChild(node);
      });
      updateLegendState();
    }

    function updateLegendState() {
      legend.querySelectorAll(".legend-item").forEach((node) => {
        const index = Number(node.dataset.index || "0");
        const item = series[index];
        if (!item) {
          return;
        }
        const isFocused = Boolean(
          state.focusSymbol &&
          item.symbol &&
          item.symbol === state.focusSymbol
        );
        const shouldDim = Boolean(
          state.focusSymbol &&
          item.symbol &&
          item.symbol !== state.focusSymbol
        );
        node.classList.toggle("off", !item.visible);
        node.classList.toggle("focused", isFocused);
        node.classList.toggle("dimmed", shouldDim);
      });
    }

    function createSvgNode(tag, attrs = {}) {
      const node = document.createElementNS(NS, tag);
      Object.entries(attrs).forEach(([key, value]) => {
        node.setAttribute(key, String(value));
      });
      return node;
    }

    function buildLinePath(values, xToPx, yToPx) {
      let path = "";
      let active = false;
      for (let index = state.start; index <= state.end; index += 1) {
        const value = values[index];
        if (value === null || value === undefined || !Number.isFinite(value) || (state.logScale && value <= 0)) {
          active = false;
          continue;
        }
        const x = xToPx(index);
        const y = yToPx(value);
        path += (active ? " L " : " M ") + x.toFixed(2) + " " + y.toFixed(2);
        active = true;
      }
      return path.trim();
    }

    function hideTooltip() {
      tooltip.style.opacity = "0";
    }

    function showTooltip(html, clientX, clientY) {
      if (!html) {
        hideTooltip();
        return;
      }
      tooltip.innerHTML = html;
      tooltip.style.opacity = "1";
      const offsetX = 14;
      const offsetY = 16;
      const maxLeft = window.innerWidth - tooltip.offsetWidth - 12;
      const maxTop = window.innerHeight - tooltip.offsetHeight - 12;
      const left = clamp(clientX + offsetX, 8, maxLeft);
      const top = clamp(clientY + offsetY, 8, maxTop);
      tooltip.style.left = left + "px";
      tooltip.style.top = top + "px";
    }

    function renderCrosshairTooltip(clientX, clientY) {
      if (state.hoverIndex === null || !state.plotBox) {
        tooltip.style.opacity = "0";
        return;
      }
      const hoverDate = dates[state.hoverIndex];
      const rows = [];
      series.forEach((item) => {
        if (!item.visible) {
          return;
        }
        const value = item.values[state.hoverIndex];
        if (value === null || value === undefined || !Number.isFinite(value)) {
          return;
        }
        rows.push(
          '<div class="tooltip-row"><span class="tooltip-name">' +
          item.name +
          '</span><span>' +
          Number(value).toFixed(4) +
          "</span></div>"
        );
      });
      showTooltip("<strong>" + hoverDate + "</strong>" + rows.join(""), clientX, clientY);
    }

    function formatPct(value) {
      if (value === null || value === undefined || !Number.isFinite(Number(value))) {
        return "n/a";
      }
      return (Number(value) * 100).toFixed(2) + "%";
    }

    function buildTradeTooltip(trade) {
      const fromName = trade.from_name || trade.from_symbol || "空仓";
      const toName = trade.to_name || trade.to_symbol || "空仓";
      return (
        "<strong>调仓点 " + (trade.position_date || trade.signal_date || "") + "</strong>" +
        '<div class="tooltip-row"><span class="tooltip-name">信号日期</span><span>' + (trade.signal_date || "n/a") + "</span></div>" +
        '<div class="tooltip-row"><span class="tooltip-name">切换</span><span>' + fromName + " → " + toName + "</span></div>" +
        '<div class="tooltip-row"><span class="tooltip-name">原因</span><span>' + (trade.reason || "n/a") + "</span></div>" +
        '<div class="tooltip-row"><span class="tooltip-name">from 20d</span><span>' + formatPct(trade.from_20d_return) + "</span></div>" +
        '<div class="tooltip-row"><span class="tooltip-name">to 20d</span><span>' + formatPct(trade.to_20d_return) + "</span></div>"
      );
    }

    function buildHoldingTooltip(period) {
      return (
        "<strong>持仓阶段 " + (period.name || period.symbol || "") + "</strong>" +
        '<div class="tooltip-row"><span class="tooltip-name">区间</span><span>' + period.start_date + " → " + period.end_date + "</span></div>" +
        '<div class="tooltip-row"><span class="tooltip-name">持有天数</span><span>' + String(period.holding_days || 0) + "</span></div>" +
        '<div class="tooltip-row"><span class="tooltip-name">阶段收益</span><span>' + formatPct(period.period_return) + "</span></div>" +
        '<div class="tooltip-row"><span class="tooltip-name">收益贡献</span><span>' + Number(period.contribution_to_total_return || 0).toFixed(4) + "</span></div>" +
        '<div class="tooltip-row"><span class="tooltip-name">阶段回撤</span><span>' + formatPct(period.max_drawdown_during_holding) + "</span></div>"
      );
    }

    function bindTooltipEvents(node, htmlBuilder) {
      node.addEventListener("mouseenter", (event) => {
        showTooltip(htmlBuilder(), event.clientX, event.clientY);
      });
      node.addEventListener("mousemove", (event) => {
        showTooltip(htmlBuilder(), event.clientX, event.clientY);
      });
      node.addEventListener("mouseleave", () => {
        hideTooltip();
      });
    }

    function buildPhaseLabelText(period) {
      const phaseName = period.name || period.symbol || "空仓";
      return phaseName + " " + formatPct(period.period_return);
    }

    function isFocusedSymbol(symbol) {
      return Boolean(state.focusSymbol && symbol === state.focusSymbol);
    }

    function isAssetSeries(item) {
      return Boolean(item && item.symbol);
    }

    function getSeriesClassName(item) {
      if (!state.focusSymbol || !isAssetSeries(item)) {
        return "series-item";
      }
      return item.symbol === state.focusSymbol
        ? "series-item focused"
        : "series-item dimmed";
    }

    function getSeriesStrokeWidth(item) {
      if (state.focusSymbol && item.symbol === state.focusSymbol) {
        return Number(item.width || 1.5) + 1.2;
      }
      return item.width;
    }

    function getPhaseClassName(baseClass, symbol) {
      if (!state.focusSymbol) {
        return baseClass;
      }
      return isFocusedSymbol(symbol)
        ? baseClass + " focused"
        : baseClass + " dimmed";
    }

    function getTradeClassName(trade) {
      if (!state.focusSymbol) {
        return "trade-item";
      }
      return (
        trade.to_symbol === state.focusSymbol ||
        trade.from_symbol === state.focusSymbol ||
        trade.rank_1_symbol === state.focusSymbol
      )
        ? "trade-item focused"
        : "trade-item dimmed";
    }

    function getSvgPoint(event) {
      const rect = svg.getBoundingClientRect();
      const safeWidth = rect.width || 1;
      const safeHeight = rect.height || 1;
      return {
        x: ((event.clientX - rect.left) / safeWidth) * 1200,
        y: ((event.clientY - rect.top) / safeHeight) * 580,
      };
    }

    function isPointInsidePlot(point) {
      if (!state.plotBox) {
        return false;
      }
      return (
        point.x >= state.plotBox.left &&
        point.x <= state.plotBox.left + state.plotBox.width &&
        point.y >= state.plotBox.top &&
        point.y <= state.plotBox.top + state.plotBox.height
      );
    }

    function isTooltipLockedTarget(target) {
      return Boolean(
        target &&
        typeof target.getAttribute === "function" &&
        target.getAttribute("data-tooltip-lock") === "true"
      );
    }

    function handleChartMouseMove(event) {
      if (!dates.length || !state.plotBox || !state.crosshair) {
        return;
      }
      const point = getSvgPoint(event);
      if (!isPointInsidePlot(point)) {
        state.hoverIndex = null;
        state.crosshair.setAttribute("visibility", "hidden");
        if (!isTooltipLockedTarget(event.target)) {
          hideTooltip();
        }
        return;
      }
      const ratio = clamp((point.x - state.plotBox.left) / state.plotBox.width, 0, 1);
      state.hoverIndex = Math.round(state.start + ratio * (state.end - state.start));
      const x = state.plotBox.left + ratio * state.plotBox.width;
      state.crosshair.setAttribute("x1", String(x));
      state.crosshair.setAttribute("x2", String(x));
      state.crosshair.setAttribute("visibility", "visible");
      if (!isTooltipLockedTarget(event.target) && !state.dragging) {
        renderCrosshairTooltip(event.clientX, event.clientY);
      }
    }

    function handleChartMouseLeave() {
      state.hoverIndex = null;
      if (state.crosshair) {
        state.crosshair.setAttribute("visibility", "hidden");
      }
      hideTooltip();
    }

    function handleChartWheel(event) {
      if (dates.length <= 2 || !state.plotBox) {
        return;
      }
      const point = getSvgPoint(event);
      if (!isPointInsidePlot(point)) {
        return;
      }
      event.preventDefault();
      const ratio = clamp((point.x - state.plotBox.left) / state.plotBox.width, 0, 1);
      const currentSpan = Math.max(state.end - state.start, minGap);
      const targetSpan = event.deltaY < 0
        ? Math.max(minGap, Math.round(currentSpan * 0.84))
        : Math.min(dates.length - 1, Math.round(currentSpan * 1.18));
      const focusIndex = state.start + ratio * currentSpan;
      const nextStart = Math.round(focusIndex - ratio * targetSpan);
      setWindow(nextStart, nextStart + targetSpan);
    }

    function handleChartMouseDown(event) {
      if (!state.plotBox) {
        return;
      }
      const point = getSvgPoint(event);
      if (!isPointInsidePlot(point)) {
        return;
      }
      state.dragging = true;
      state.dragOriginX = event.clientX;
      state.dragWindow = [state.start, state.end];
    }

    function handleWindowMouseMove(event) {
      if (!state.dragging || !state.plotBox) {
        return;
      }
      const dragSpan = Math.max(state.dragWindow[1] - state.dragWindow[0], minGap);
      const deltaX = event.clientX - state.dragOriginX;
      const shift = Math.round((deltaX / state.plotBox.width) * dragSpan);
      setWindow(state.dragWindow[0] - shift, state.dragWindow[1] - shift);
    }

    function handleWindowMouseUp() {
      state.dragging = false;
      svg.style.cursor = "grab";
    }

    function render() {
      const width = 1200;
      const height = 580;
      const margin = { top: 24, right: 22, bottom: 46, left: 70 };
      const plotWidth = width - margin.left - margin.right;
      const plotHeight = height - margin.top - margin.bottom;
      const span = Math.max(state.end - state.start, 1);
      svg.innerHTML = "";
      holdingBand.innerHTML = "";
      const dateIndexMap = new Map(dates.map((date, index) => [date, index]));
      const visiblePeriods = holdingPeriods.filter((period) => {
        const startIndex = dateIndexMap.get(period.start_date);
        const endIndex = dateIndexMap.get(period.end_date);
        return (
          startIndex !== undefined &&
          endIndex !== undefined &&
          !(endIndex < state.start || startIndex > state.end)
        );
      });

      const visibleSeries = series.filter((item) => item.visible);
      let yMin = Infinity;
      let yMax = -Infinity;
      visibleSeries.forEach((item) => {
        for (let index = state.start; index <= state.end; index += 1) {
          const value = item.values[index];
          if (value === null || value === undefined || !Number.isFinite(value)) {
            continue;
          }
          if (state.logScale && value <= 0) {
            continue;
          }
          yMin = Math.min(yMin, value);
          yMax = Math.max(yMax, value);
        }
      });
      if (!Number.isFinite(yMin) || !Number.isFinite(yMax)) {
        yMin = 0.9;
        yMax = 1.1;
      }
      yMin = Math.min(yMin, 1.0);
      yMax = Math.max(yMax, 1.0);

      let yToPx;
      let tickValues = [];
      if (state.logScale) {
        yMin = Math.max(yMin, 0.0001);
        const logMin = Math.log10(yMin);
        const logMax = Math.log10(yMax);
        const paddedMin = logMin - Math.max((logMax - logMin) * 0.08, 0.04);
        const paddedMax = logMax + Math.max((logMax - logMin) * 0.08, 0.04);
        yToPx = (value) => margin.top + ((paddedMax - Math.log10(value)) / (paddedMax - paddedMin)) * plotHeight;
        for (let step = 0; step <= 5; step += 1) {
          const ratio = step / 5;
          tickValues.push(Math.pow(10, paddedMin + (paddedMax - paddedMin) * ratio));
        }
      } else {
        const pad = Math.max((yMax - yMin) * 0.1, 0.05);
        const paddedMin = yMin - pad;
        const paddedMax = yMax + pad;
        yToPx = (value) => margin.top + ((paddedMax - value) / (paddedMax - paddedMin)) * plotHeight;
        for (let step = 0; step <= 5; step += 1) {
          tickValues.push(paddedMin + ((paddedMax - paddedMin) * step) / 5);
        }
      }

      const xToPx = (index) => margin.left + ((index - state.start) / span) * plotWidth;
      const xStepWidth = plotWidth / Math.max(span, 1);
      const segmentLeftPx = (index) =>
        clamp(xToPx(index) - xStepWidth / 2, margin.left, width - margin.right);
      const segmentRightPx = (index) =>
        clamp(xToPx(index) + xStepWidth / 2, margin.left, width - margin.right);

      visiblePeriods.forEach((period) => {
        const rawStart = dateIndexMap.get(period.start_date);
        const rawEnd = dateIndexMap.get(period.end_date);
        if (rawStart === undefined || rawEnd === undefined) {
          return;
        }
        const startIndex = Math.max(rawStart, state.start);
        const endIndex = Math.min(rawEnd, state.end);
        const leftPx = segmentLeftPx(startIndex);
        const rightPx = segmentRightPx(endIndex);
        const widthPx = Math.max(rightPx - leftPx, 2);
        const color = symbolColors[period.symbol] || "#B7ADA1";
        const phaseLayer = createSvgNode("rect", {
          x: leftPx,
          y: margin.top,
          width: widthPx,
          height: plotHeight,
          fill: color,
          class: getPhaseClassName("phase-layer", period.symbol),
          "data-tooltip-lock": "true",
        });
        svg.appendChild(phaseLayer);
        bindTooltipEvents(phaseLayer, () => buildHoldingTooltip(period));
        svg.appendChild(
          createSvgNode("rect", {
            x: leftPx,
            y: margin.top,
            width: widthPx,
            height: 18,
            fill: color,
            class: getPhaseClassName("phase-strip", period.symbol),
            "pointer-events": "none",
          })
        );
        if (widthPx >= 110) {
          const phaseLabel = createSvgNode("text", {
            x: leftPx + widthPx / 2,
            y: margin.top + 13,
            "text-anchor": "middle",
            class: getPhaseClassName("phase-label", period.symbol),
            "data-tooltip-lock": "true",
          });
          phaseLabel.textContent = buildPhaseLabelText(period);
          svg.appendChild(phaseLabel);
          bindTooltipEvents(phaseLabel, () => buildHoldingTooltip(period));
        }
      });

      for (let step = 0; step <= 5; step += 1) {
        const value = tickValues[step];
        const y = yToPx(value);
        svg.appendChild(
          createSvgNode("line", {
            x1: margin.left,
            y1: y,
            x2: width - margin.right,
            y2: y,
            stroke: "#E3DDD3",
            "stroke-width": 1,
          })
        );
        const label = createSvgNode("text", {
          x: margin.left - 10,
          y: y + 4,
          "text-anchor": "end",
          fill: "#6E665C",
          "font-size": 12,
        });
        label.textContent = Number(value).toFixed(2);
        svg.appendChild(label);
      }

      const xTickCount = Math.min(7, Math.max(state.end - state.start + 1, 2));
      for (let step = 0; step < xTickCount; step += 1) {
        const ratio = xTickCount === 1 ? 0 : step / (xTickCount - 1);
        const index = Math.round(state.start + ratio * (state.end - state.start));
        const x = xToPx(index);
        svg.appendChild(
          createSvgNode("line", {
            x1: x,
            y1: height - margin.bottom,
            x2: x,
            y2: height - margin.bottom + 6,
            stroke: "#8C8479",
            "stroke-width": 1,
          })
        );
        const label = createSvgNode("text", {
          x: x,
          y: height - margin.bottom + 22,
          "text-anchor": "middle",
          fill: "#6E665C",
          "font-size": 12,
        });
        label.textContent = dates[index];
        svg.appendChild(label);
      }

      svg.appendChild(
        createSvgNode("line", {
          x1: margin.left,
          y1: height - margin.bottom,
          x2: width - margin.right,
          y2: height - margin.bottom,
          stroke: "#8C8479",
          "stroke-width": 1.1,
        })
      );
      svg.appendChild(
        createSvgNode("line", {
          x1: margin.left,
          y1: margin.top,
          x2: margin.left,
          y2: height - margin.bottom,
          stroke: "#8C8479",
          "stroke-width": 1.1,
        })
      );

      visibleSeries.forEach((item) => {
        const pathData = buildLinePath(item.values, xToPx, yToPx);
        if (!pathData) {
          return;
        }
        svg.appendChild(
          createSvgNode("path", {
            d: pathData,
            fill: "none",
            stroke: item.color,
            "stroke-width": getSeriesStrokeWidth(item),
            "stroke-linecap": "round",
            "stroke-linejoin": "round",
            "stroke-dasharray": item.dash || "",
            class: getSeriesClassName(item),
          })
        );
      });

      const strategySeries = series.find((item) => item.id === "strategy_nav");
      const visibleTrades = trades.filter((trade) => {
        const tradeDate = trade.position_date || trade.signal_date;
        const index = dateIndexMap.get(tradeDate);
        return index !== undefined && index >= state.start && index <= state.end;
      });
      visibleTrades.forEach((trade) => {
        const tradeDate = trade.position_date || trade.signal_date;
        const index = dateIndexMap.get(tradeDate);
        if (index === undefined) {
          return;
        }
        const x = xToPx(index);
        const line = createSvgNode("line", {
          x1: x,
          y1: margin.top,
          x2: x,
          y2: height - margin.bottom,
          stroke: "#C19B4D",
          "stroke-width": 1,
          "stroke-dasharray": "3 5",
          class: getTradeClassName(trade),
          "data-tooltip-lock": "true",
        });
        svg.appendChild(line);
        bindTooltipEvents(line, () => buildTradeTooltip(trade));
        const markerValue = strategySeries && Number.isFinite(strategySeries.values[index])
          ? strategySeries.values[index]
          : 1.0;
        const circle = createSvgNode("circle", {
          cx: x,
          cy: yToPx(markerValue),
          r: 4.5,
          fill: "#F7F0DE",
          stroke: "#9F7A34",
          "stroke-width": 2,
          class: getTradeClassName(trade),
          "data-tooltip-lock": "true",
        });
        svg.appendChild(circle);
        bindTooltipEvents(circle, () => buildTradeTooltip(trade));
      });

      const crosshair = createSvgNode("line", {
        x1: margin.left,
        y1: margin.top,
        x2: margin.left,
        y2: height - margin.bottom,
        stroke: "#B38C43",
        "stroke-width": 1,
        "stroke-dasharray": "4 4",
        visibility: "hidden",
      });
      svg.appendChild(crosshair);
      svg.style.cursor = state.dragging ? "grabbing" : "grab";
      state.plotBox = {
        left: margin.left,
        top: margin.top,
        width: plotWidth,
        height: plotHeight,
      };
      state.crosshair = crosshair;

      const bandWidth = 1200;
      const bandHeight = 120;
      const bandMargin = { top: 18, right: 22, bottom: 18, left: 70 };
      const bandInnerWidth = bandWidth - bandMargin.left - bandMargin.right;
      const bandRailY = 36;
      const bandRailHeight = 44;
      const bandStepWidth = bandInnerWidth / span;
      holdingBand.appendChild(
        createSvgNode("rect", {
          x: bandMargin.left,
          y: bandRailY,
          width: bandInnerWidth,
          height: bandRailHeight,
          rx: 14,
          fill: "#F2ECE1",
          stroke: "#D6CEC1",
          "stroke-width": 1,
        })
      );
      visiblePeriods.forEach((period) => {
        const rawStart = dateIndexMap.get(period.start_date);
        const rawEnd = dateIndexMap.get(period.end_date);
        if (rawStart === undefined || rawEnd === undefined) {
          return;
        }
        const startIndex = Math.max(rawStart, state.start);
        const endIndex = Math.min(rawEnd, state.end);
        const x = bandMargin.left + ((startIndex - state.start) / span) * bandInnerWidth;
        const widthPx = Math.max((((endIndex - startIndex) + 1) / (span + 1)) * bandInnerWidth, bandStepWidth * 0.85, 3);
        const color = symbolColors[period.symbol] || "#B7ADA1";
        const rect = createSvgNode("rect", {
          x: x,
          y: bandRailY + 5,
          width: widthPx,
          height: bandRailHeight - 10,
          rx: 10,
          fill: color,
          class: getPhaseClassName("holding-band-item", period.symbol),
        });
        holdingBand.appendChild(rect);
        bindTooltipEvents(rect, () => buildHoldingTooltip(period));
        if (widthPx >= 54) {
          const label = createSvgNode("text", {
            x: x + widthPx / 2,
            y: bandRailY + bandRailHeight / 2 + 4,
            "text-anchor": "middle",
            fill: "#FFFDF8",
            "font-size": 12,
            "font-weight": 600,
            class: getPhaseClassName("holding-band-label", period.symbol),
          });
          label.textContent = period.name || period.symbol || "空仓";
          holdingBand.appendChild(label);
          bindTooltipEvents(label, () => buildHoldingTooltip(period));
        }
      });
      const bandTickCount = Math.min(7, Math.max(state.end - state.start + 1, 2));
      for (let step = 0; step < bandTickCount; step += 1) {
        const ratio = bandTickCount === 1 ? 0 : step / (bandTickCount - 1);
        const index = Math.round(state.start + ratio * (state.end - state.start));
        const x = bandMargin.left + ((index - state.start) / span) * bandInnerWidth;
        const label = createSvgNode("text", {
          x: x,
          y: bandHeight - 6,
          "text-anchor": "middle",
          fill: "#6E665C",
          "font-size": 11,
        });
        label.textContent = dates[index];
        holdingBand.appendChild(label);
      }
      updateLegendState();
    }

    startSlider.addEventListener("input", () => {
      setWindow(Number(startSlider.value), state.end);
    });
    endSlider.addEventListener("input", () => {
      setWindow(state.start, Number(endSlider.value));
    });
    toggleLog.addEventListener("change", () => {
      state.logScale = toggleLog.checked;
      render();
    });
    document.querySelectorAll("button[data-window]").forEach((button) => {
      button.addEventListener("click", () => applyPreset(button.dataset.window));
    });
    svg.addEventListener("mousemove", handleChartMouseMove);
    svg.addEventListener("mouseleave", handleChartMouseLeave);
    svg.addEventListener("wheel", handleChartWheel, { passive: false });
    svg.addEventListener("mousedown", handleChartMouseDown);
    window.addEventListener("mousemove", handleWindowMouseMove);
    window.addEventListener("mouseup", handleWindowMouseUp);
    buildLegend();
    syncControls();
    render();
  </script>
</body>
</html>
"""

    return (
        html.replace("__TITLE__", title)
        .replace("__START__", str(meta.get("start_date") or ""))
        .replace("__END__", str(meta.get("end_date") or ""))
        .replace("__NOTES__", notes_html)
        .replace("__PAYLOAD_JSON__", payload_json)
    )


def write_interactive_rotation_preview(
    payload: dict[str, Any],
    output_path: Path | str = DEFAULT_OUTPUT_PATH,
) -> Path:
    resolved_output_path = Path(output_path)
    resolved_output_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_output_path.write_text(
        render_interactive_rotation_html(payload),
        encoding="utf-8",
    )
    return resolved_output_path


def main() -> int:
    payload = load_interactive_rotation_payload()
    output_path = write_interactive_rotation_preview(payload)
    print(f"[INFO] ETF轮动交互预览已生成: {output_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
