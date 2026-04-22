"""测试: 从 etf.com (cdn.efunds.com.cn) 获取指数历史股息率, 并计算当前股息率的历史百分位.

运行:
    python test_dividend_yield_history.py
    python test_dividend_yield_history.py 930955 000300
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import List

import pandas as pd
import requests

URL_TEMPLATE = "https://cdn.efunds.com.cn/etf-net/index_dividend_ratio_{code}.json"

DEFAULT_CODES = ["930955", "000300", "399303", "931722", "930709", "931233","399326"]

CACHE_DIR = Path(__file__).resolve().parent / "datacache"


def cache_path(code: str) -> Path:
    return CACHE_DIR / f"dividend_yield_{code}.json"


def load_rows(code: str) -> list:
    path = cache_path(code)
    if path.exists():
        print(f"[cache] {code}: 命中 {path.name}")
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    url = URL_TEMPLATE.format(code=code)
    print(f"[fetch] {code}: {url}")
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    rows = resp.json()
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"{code}: 接口返回为空或非列表")

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False)
    print(f"[cache] {code}: 已写入 {path.name} ({len(rows)} 条)")
    return rows


def fetch_history(code: str) -> pd.DataFrame:
    rows = load_rows(code)
    df = pd.DataFrame(rows)
    df["trdDt"] = pd.to_datetime(df["trdDt"], errors="coerce")
    df["dividendYield"] = pd.to_numeric(df["dividendYield"], errors="coerce")
    df = df.dropna(subset=["trdDt", "dividendYield"]).sort_values("trdDt").reset_index(drop=True)
    return df


def percentile_of(series: pd.Series, value: float) -> float:
    """当前值在历史序列中的百分位 (0-100). 越高 = 股息率越高 = 越便宜."""
    if series.empty:
        return float("nan")
    return float((series <= value).mean() * 100)


def summarize(code: str, df: pd.DataFrame) -> None:
    latest = df.iloc[-1]
    current = float(latest["dividendYield"])
    current_date = latest["trdDt"].strftime("%Y-%m-%d")
    start_date = df["trdDt"].iloc[0].strftime("%Y-%m-%d")
    years = (df["trdDt"].iloc[-1] - df["trdDt"].iloc[0]).days / 365.25

    series = df["dividendYield"]
    pct_full = percentile_of(series, current)

    print(f"\n===== {code} =====")
    print(f"数据范围: {start_date} ~ {current_date}  ({len(df)} 条, {years:.1f} 年)")
    print(f"当前股息率: {current:.4f}%")
    print(f"历史  min / mean / median / max: "
          f"{series.min():.4f}% / {series.mean():.4f}% / {series.median():.4f}% / {series.max():.4f}%")
    print(f"全历史百分位: {pct_full:.2f}%  (越高越便宜)")

    # 不同回溯窗口的百分位
    for label, years_back in [("1Y", 1), ("3Y", 3), ("5Y", 5), ("10Y", 10)]:
        cutoff = df["trdDt"].iloc[-1] - pd.DateOffset(years=years_back)
        window = df.loc[df["trdDt"] >= cutoff, "dividendYield"]
        if window.empty or len(window) < 30:
            print(f"  {label}: 数据不足 ({len(window)} 条)")
            continue
        pct = percentile_of(window, current)
        print(f"  {label}: 百分位 {pct:5.2f}%  | 区间 {window.min():.4f}% ~ {window.max():.4f}%")


def main(codes: List[str]) -> int:
    exit_code = 0
    for code in codes:
        try:
            df = fetch_history(code)
            summarize(code, df)
        except Exception as exc:  # noqa: BLE001
            print(f"\n===== {code} =====")
            print(f"失败: {exc!r}")
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    codes = sys.argv[1:] or DEFAULT_CODES
    sys.exit(main(codes))
