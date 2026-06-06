from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any


DEFAULT_OUTPUT_ROOT = Path(".test_artifacts/etf_rotation_generalization")
DEFENSIVE_SYMBOL = "511880"
VERSION_POSITION_PATHS = {
    "V2": Path(".test_artifacts/etf_rotation_v2_backtest/daily_positions.csv"),
    "V3": Path(".test_artifacts/etf_rotation_v3_backtest/daily_positions.csv"),
    "V4-A": Path(".test_artifacts/etf_rotation_v4_backtest/daily_positions.csv"),
    "V4-B": Path(".test_artifacts/etf_rotation_v4_backtest_v4b/daily_positions.csv"),
}
SEGMENTS = [
    ("2014-2018", "2014-01-01", "2018-12-31"),
    ("2019-2022", "2019-01-01", "2022-12-31"),
    ("2023-2026", "2023-01-01", "2026-06-05"),
    ("2025-2026", "2025-01-01", "2026-06-05"),
]


def _clean_float(value: float, digits: int = 12) -> float:
    if not math.isfinite(value):
        return 0.0
    return round(float(value), digits)


def load_csv_rows(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _calculate_max_drawdown(nav_values: list[float]) -> float:
    peak = None
    max_drawdown = 0.0
    for nav in nav_values:
        if not math.isfinite(nav):
            continue
        if peak is None or nav > peak:
            peak = nav
            continue
        if peak <= 0:
            continue
        drawdown = nav / peak - 1.0
        if drawdown < max_drawdown:
            max_drawdown = drawdown
    return max_drawdown


def build_segment_summary(
    version: str,
    rows: list[dict[str, Any]],
    start_date: str,
    end_date: str,
    defensive_symbol: str = DEFENSIVE_SYMBOL,
    segment_name: str | None = None,
) -> dict[str, Any]:
    segment_rows = [
        row
        for row in rows
        if start_date <= str(row.get("date") or "") <= end_date
    ]
    if not segment_rows:
        return {
            "version": version,
            "segment": segment_name or f"{start_date}_{end_date}",
            "start_date": start_date,
            "end_date": end_date,
            "trading_days": 0,
            "defensive_days": 0,
            "risk_days": 0,
            "segment_final_nav": 1.0,
            "segment_total_return": 0.0,
            "segment_annualized_return": 0.0,
            "segment_max_drawdown": 0.0,
        }

    raw_nav_values = [float(row.get("strategy_nav") or 0.0) for row in segment_rows]
    first_nav = raw_nav_values[0]
    normalized_nav_values = [
        nav / first_nav if first_nav > 0 and math.isfinite(nav) else 1.0
        for nav in raw_nav_values
    ]
    final_nav = normalized_nav_values[-1]
    trading_days = len(segment_rows)
    annualized_return = final_nav ** (252 / trading_days) - 1.0 if trading_days and final_nav > 0 else 0.0
    defensive_days = sum(
        1
        for row in segment_rows
        if str(row.get("holding_symbol") or "").strip() == defensive_symbol
    )

    return {
        "version": version,
        "segment": segment_name or f"{start_date}_{end_date}",
        "start_date": str(segment_rows[0].get("date") or start_date),
        "end_date": str(segment_rows[-1].get("date") or end_date),
        "trading_days": trading_days,
        "defensive_days": defensive_days,
        "risk_days": trading_days - defensive_days,
        "segment_final_nav": _clean_float(final_nav),
        "segment_total_return": _clean_float(final_nav - 1.0),
        "segment_annualized_return": _clean_float(annualized_return),
        "segment_max_drawdown": _clean_float(_calculate_max_drawdown(normalized_nav_values)),
    }


def build_all_segment_summaries(
    version_position_paths: dict[str, Path] = VERSION_POSITION_PATHS,
    segments: list[tuple[str, str, str]] = SEGMENTS,
) -> list[dict[str, Any]]:
    rows_by_version = {
        version: load_csv_rows(path)
        for version, path in version_position_paths.items()
    }
    summaries: list[dict[str, Any]] = []
    for version, rows in rows_by_version.items():
        for segment_name, start_date, end_date in segments:
            summaries.append(
                build_segment_summary(
                    version=version,
                    rows=rows,
                    start_date=start_date,
                    end_date=end_date,
                    defensive_symbol=DEFENSIVE_SYMBOL,
                    segment_name=segment_name,
                )
            )
    return summaries


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_markdown_summary(rows: list[dict[str, Any]]) -> str:
    lines = [
        "# ETF Rotation 泛化验证",
        "",
        "说明：这是一份时间分段稳健性验证，不是严格盲测。V4 已经看过 2025 年数据，因此 2025-2026 只能作为压力复核段。",
        "",
        "| 版本 | 区间 | 交易日 | 防守天数 | 最终净值 | 年化收益 | 最大回撤 |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            "| {version} | {segment} | {trading_days} | {defensive_days} | "
            "{nav:.4f} | {annual:.2%} | {drawdown:.2%} |".format(
                version=row["version"],
                segment=row["segment"],
                trading_days=int(row["trading_days"]),
                defensive_days=int(row["defensive_days"]),
                nav=float(row["segment_final_nav"]),
                annual=float(row["segment_annualized_return"]),
                drawdown=float(row["segment_max_drawdown"]),
            )
        )
    lines.extend(
        [
            "",
            "## 初步判断",
            "",
            "- V4-B 只能进入稳健性观察，不能直接替代 V2。",
            "- 任何 V4.1 都必须先冻结规则，再做分段验证，不能围绕单一总净值调参。",
            "- 真正的盲测只能来自未来新增数据或完全独立资产池。",
            "",
        ]
    )
    return "\n".join(lines)


def run(output_root: Path | str = DEFAULT_OUTPUT_ROOT) -> dict[str, Any]:
    resolved_output_root = Path(output_root)
    summaries = build_all_segment_summaries()
    write_csv(resolved_output_root / "segment_summary.csv", summaries)
    markdown = build_markdown_summary(summaries)
    (resolved_output_root / "generalization_summary.md").write_text(markdown, encoding="utf-8")
    return {
        "segment_summaries": summaries,
        "summary_markdown": markdown,
    }


if __name__ == "__main__":
    run()

