from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Callable

import requests
import yaml


ETF_CODES = ["159934", "159941", "159259", "159263", "511130", "511380"]
SAMPLE_DIR = Path(".test_artifacts/etf_com_cn_api")
OUTPUT_DIR = SAMPLE_DIR / "period_return_analysis"
ONE_MONTH_OUTPUT_DIR = SAMPLE_DIR / "one_month_analysis"
SIMPLE_LIST_URL = "https://www.etf.com.cn/api/etf-api-service/etf-funds/simpleList"
NAV_URL_TEMPLATE = "https://cdn.efunds.com.cn/etf-net/etf_fund_nav_{code}.json"
REQUEST_TIMEOUT = 15

PERIOD_LABELS = {
    "1m": "近1月",
    "3m": "近3月",
    "6m": "近6月",
    "1y": "近1年",
    "ytd": "年初至今",
    "3y": "近3年",
    "5y": "近5年",
    "10y": "近10年",
    "since_inception": "成立以来",
}


def shift_months(value: date, months: int) -> date:
    year = value.year
    month = value.month - months
    while month <= 0:
        year -= 1
        month += 12

    if month == 2:
        leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
        max_day = 29 if leap else 28
    elif month in {4, 6, 9, 11}:
        max_day = 30
    else:
        max_day = 31

    return date(year, month, min(value.day, max_day))


def shift_years(value: date, years: int) -> date:
    year = value.year - years
    month = value.month
    day = value.day
    if month == 2 and day == 29:
        leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
        day = 29 if leap else 28
    return date(year, month, day)


def load_period_return_email_codes(config_path: Path) -> list[str]:
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    codes = payload.get("codes") or []
    if not isinstance(codes, list):
        raise ValueError("period_return_email_config.yaml 中 codes 必须是列表")

    normalized: list[str] = []
    seen: set[str] = set()
    for item in codes:
        code = str(item).strip()
        if not code or code in seen:
            continue
        normalized.append(code)
        seen.add(code)
    return normalized


def load_nav_rows(code: str, sample_dir: Path = SAMPLE_DIR) -> list[dict[str, Any]]:
    path = sample_dir / f"etf_fund_nav_{code}.json"
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
    else:
        sample_dir.mkdir(parents=True, exist_ok=True)
        with requests.Session() as session:
            response = session.get(
                NAV_URL_TEMPLATE.format(code=code),
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    if not isinstance(payload, list):
        raise ValueError(f"unexpected NAV payload type for {code}: {type(payload).__name__}")
    rows = [item for item in payload if isinstance(item, dict)]
    if not rows:
        raise ValueError(f"empty NAV rows for {code}")
    return rows


def select_base_record(rows: list[dict[str, Any]], target_date: date) -> dict[str, Any] | None:
    chosen = None
    for row in rows:
        row_date = date.fromisoformat(str(row["trdDt"]))
        if row_date <= target_date:
            chosen = row
        else:
            break
    return chosen


def compute_period_return(rows: list[dict[str, Any]], label: str, target_date: date) -> dict[str, Any]:
    base_row = select_base_record(rows, target_date)
    if base_row is None:
        return {
            "label": label,
            "available": False,
            "base_date": None,
            "return_pct": None,
        }

    latest_row = rows[-1]
    latest_nav = float(latest_row["adjUnitNav"])
    base_nav = float(base_row["adjUnitNav"])
    return_pct = round((latest_nav / base_nav - 1) * 100, 2)
    return {
        "label": label,
        "available": True,
        "base_date": str(base_row["trdDt"]),
        "return_pct": return_pct,
    }


def compute_ytd_return(rows: list[dict[str, Any]]) -> dict[str, Any]:
    latest_date = date.fromisoformat(str(rows[-1]["trdDt"]))
    first_of_year = date(latest_date.year, 1, 1)
    first_row_in_year = next(
        (row for row in rows if date.fromisoformat(str(row["trdDt"])).year == latest_date.year),
        None,
    )
    if first_row_in_year is None:
        return {
            "label": "ytd",
            "available": False,
            "base_date": None,
            "return_pct": None,
        }

    base_row = select_base_record(rows, first_of_year) or first_row_in_year
    latest_nav = float(rows[-1]["adjUnitNav"])
    base_nav = float(base_row["adjUnitNav"])
    return {
        "label": "ytd",
        "available": True,
        "base_date": str(base_row["trdDt"]),
        "return_pct": round((latest_nav / base_nav - 1) * 100, 2),
    }


def compute_since_inception_return(rows: list[dict[str, Any]]) -> dict[str, Any]:
    base_row = rows[0]
    latest_row = rows[-1]
    latest_nav = float(latest_row["adjUnitNav"])
    base_nav = float(base_row["adjUnitNav"])
    return {
        "label": "since_inception",
        "available": True,
        "base_date": str(base_row["trdDt"]),
        "return_pct": round((latest_nav / base_nav - 1) * 100, 2),
    }


def build_one_month_curve(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest_date = date.fromisoformat(str(rows[-1]["trdDt"]))
    start_date = shift_months(latest_date, 1)
    base_row = select_base_record(rows, start_date)
    if base_row is None:
        return []

    base_date = date.fromisoformat(str(base_row["trdDt"]))
    base_nav = float(base_row["adjUnitNav"])
    curve: list[dict[str, Any]] = []
    for row in rows:
        row_date = date.fromisoformat(str(row["trdDt"]))
        if row_date < base_date:
            continue
        return_pct = round((float(row["adjUnitNav"]) / base_nav - 1) * 100, 2)
        curve.append(
            {
                "date": str(row["trdDt"]),
                "return_pct": return_pct,
            }
        )
    return curve


def compute_period_returns(code: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    latest_date = date.fromisoformat(str(rows[-1]["trdDt"]))
    target_builders: dict[str, Callable[[date], date]] = {
        "1m": lambda current: shift_months(current, 1),
        "3m": lambda current: shift_months(current, 3),
        "6m": lambda current: shift_months(current, 6),
        "1y": lambda current: shift_years(current, 1),
        "3y": lambda current: shift_years(current, 3),
        "5y": lambda current: shift_years(current, 5),
        "10y": lambda current: shift_years(current, 10),
    }

    period_returns = {
        label: compute_period_return(rows, label, builder(latest_date))
        for label, builder in target_builders.items()
    }
    period_returns["ytd"] = compute_ytd_return(rows)
    period_returns["since_inception"] = compute_since_inception_return(rows)

    ordered_period_returns = {
        key: period_returns[key]
        for key in ["1m", "3m", "6m", "1y", "ytd", "3y", "5y", "10y", "since_inception"]
    }
    return {
        "code": code,
        "latest_date": str(rows[-1]["trdDt"]),
        "period_returns": ordered_period_returns,
    }


def format_period_value(period: dict[str, Any]) -> str:
    if not period["available"]:
        return "--"
    return f"{period['return_pct']:.2f}%"


def fetch_fund_names(codes: list[str]) -> dict[str, str]:
    with requests.Session() as session:
        response = session.post(
            SIMPLE_LIST_URL,
            json={"fundCodes": codes},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()

    items = payload.get("data") or []
    names: dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        code = str(item.get("fundCode") or item.get("trdCode") or "").strip()
        name = str(item.get("extdSecuSht") or item.get("fundName") or "").strip()
        if code and name:
            names[code] = name
    return names


def build_table_rows(analyses: list[dict[str, Any]], names: dict[str, str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for analysis in analyses:
        code = analysis["code"]
        period_returns = analysis["period_returns"]
        rows.append(
            {
                "name": names.get(code, ""),
                "code": code,
                "return_1m": format_period_value(period_returns["1m"]),
                "return_3m": format_period_value(period_returns["3m"]),
                "return_6m": format_period_value(period_returns["6m"]),
                "return_1y": format_period_value(period_returns["1y"]),
                "return_ytd": format_period_value(period_returns["ytd"]),
                "return_3y": format_period_value(period_returns["3y"]),
                "return_5y": format_period_value(period_returns["5y"]),
                "return_10y": format_period_value(period_returns["10y"]),
                "return_since_inception": format_period_value(period_returns["since_inception"]),
            }
        )
    return rows


def render_report(analyses: list[dict[str, Any]], output_dir: Path = OUTPUT_DIR) -> str:
    lines = ["# ETF.com.cn 区间收益验证", ""]
    ordered_labels = ["1m", "3m", "6m", "1y", "ytd", "3y", "5y", "10y", "since_inception"]

    for analysis in analyses:
        lines.append(f"## {analysis['code']}")
        lines.append(f"- Latest Date: `{analysis['latest_date']}`")
        for label in ordered_labels:
            period = analysis["period_returns"][label]
            lines.append(f"- {PERIOD_LABELS[label]}: `{format_period_value(period)}`")
        lines.append("")

    report = "\n".join(lines).rstrip() + "\n"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "report.md").write_text(report, encoding="utf-8")
    return report


def write_analysis_payloads(analyses: list[dict[str, Any]], output_dir: Path = OUTPUT_DIR) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for analysis in analyses:
        path = output_dir / f"{analysis['code']}_period_returns.json"
        path.write_text(
            json.dumps(analysis, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def write_table_json(rows: list[dict[str, str]], output_dir: Path = OUTPUT_DIR) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "table.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_one_month_curve_json(
    code: str,
    curve: list[dict[str, Any]],
    output_dir: Path = ONE_MONTH_OUTPUT_DIR,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / f"{code}_one_month_curve.json").write_text(
        json.dumps(curve, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> int:
    analyses = [compute_period_returns(code, load_nav_rows(code)) for code in ETF_CODES]
    names = fetch_fund_names(ETF_CODES)
    rows = build_table_rows(analyses, names)
    write_analysis_payloads(analyses)
    write_table_json(rows)
    for code in ETF_CODES:
        write_one_month_curve_json(code, build_one_month_curve(load_nav_rows(code)))
    report = render_report(analyses)
    print(report, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
