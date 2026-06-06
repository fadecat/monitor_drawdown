from __future__ import annotations

from typing import Any

import analyze_etf_com_cn_period_returns as etf_analysis
import monitor_drawdown as md


def normalize_series_frame(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped_by_date: dict[str, dict[str, Any]] = {}
    for row in records:
        date_text = str(row.get("date") or "").strip()
        close_value = row.get("close")
        if not date_text or close_value in {None, ""}:
            continue
        try:
            numeric_close = float(close_value)
        except (TypeError, ValueError):
            continue
        deduped_by_date[date_text] = {"date": date_text, "close": numeric_close}
    return [deduped_by_date[key] for key in sorted(deduped_by_date)]


def load_etf_series(code: str) -> list[dict[str, Any]]:
    rows = etf_analysis.load_nav_rows(code)
    return normalize_series_frame(
        [
            {"date": str(row.get("trdDt") or "").strip(), "close": row.get("adjUnitNav")}
            for row in rows
            if isinstance(row, dict)
        ]
    )


def load_index_series(code: str) -> list[dict[str, Any]]:
    source_url = md.build_index_eod_price_url(code)
    rows = md.fetch_json_response("index_eod_price", source_url)
    frame = md.parse_index_eod_price_rows(rows)
    if frame.empty:
        return []
    return normalize_series_frame(
        [
            {
                "date": record["date"].strftime("%Y-%m-%d"),
                "close": record["close"],
            }
            for record in frame.to_dict(orient="records")
        ]
    )


def fetch_selected_series(selected_primary: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    kind = str(selected_primary["kind"])
    code = str(selected_primary["code"])
    if kind == "etf":
        series = load_etf_series(code)
    elif kind == "index":
        series = load_index_series(code)
    else:
        raise ValueError(f"unsupported kind: {kind}")

    if not series:
        raise RuntimeError(f"empty ETF rotation series for {kind}:{code}")

    summary = {
        "status": "ok",
        "selected_kind": kind,
        "selected_code": code,
        "rows": len(series),
        "date_start": series[0]["date"],
        "date_end": series[-1]["date"],
        "latest_close": series[-1]["close"],
    }
    return series, summary


def resolve_target(target: dict[str, Any]) -> dict[str, Any]:
    label = str(target.get("label") or "").strip()
    return {
        "label": label,
        "status": "unresolved",
        "selected_primary": None,
    }
