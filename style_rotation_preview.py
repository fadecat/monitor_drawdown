from __future__ import annotations

from typing import Any

import analyze_etf_com_cn_period_returns as etf_analysis
import pandas as pd
import monitor_drawdown as md


FIXED_LEFT_SYMBOL = "399376"
FIXED_LEFT_NAME = "国证小盘成长"
FIXED_RIGHT_SYMBOL = "399373"
FIXED_RIGHT_NAME = "国证大盘价值"
DEFAULT_RETURN_WINDOW_DAYS = 250
DEFAULT_DISPLAY_WINDOW_DAYS = 252 * 5
STYLE_ROTATION_TICKFLOW_DAILY_COUNT = 5000

FIXED_ETF_LEFT_SYMBOL = "159259"
FIXED_ETF_LEFT_NAME = "成长ETF易方达"
FIXED_ETF_RIGHT_SYMBOL = "159263"
FIXED_ETF_RIGHT_NAME = "价值ETF易方达"
DEFAULT_ETF_RETURN_WINDOW_DAYS = 40
DEFAULT_ETF_DISPLAY_WINDOW_DAYS = 180


def normalize_price_frame(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(
            {
                "date": pd.Series(dtype="datetime64[ns]"),
                "close": pd.Series(dtype="float64"),
            }
        )

    frame = df.copy()
    frame.columns = [str(column).strip().lower() for column in frame.columns]

    date_column = "date" if "date" in frame.columns else "trade_date"
    if "close" not in frame.columns or date_column not in frame.columns:
        raise ValueError("price frame must contain date and close columns")

    frame = frame[[date_column, "close"]].copy()
    frame.columns = ["date", "close"]
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    frame = frame.dropna(subset=["date", "close"])
    frame = frame.sort_values("date").drop_duplicates(subset=["date"], keep="last").reset_index(drop=True)
    return frame


def calculate_style_rotation_preview(
    *,
    left_df: pd.DataFrame,
    right_df: pd.DataFrame,
    return_window_days: int = 250,
    display_window_days: int = 252,
) -> dict[str, Any]:
    if return_window_days <= 0:
        raise ValueError("return_window_days must be greater than 0")

    left = normalize_price_frame(left_df)
    right = normalize_price_frame(right_df)

    merged = pd.merge(left, right, on="date", how="inner", suffixes=("_left", "_right"))
    merged = merged.sort_values("date").reset_index(drop=True)
    if merged.empty:
        raise ValueError("对齐后的价格数据为空")

    merged["left_return"] = merged["close_left"].pct_change(return_window_days) * 100
    merged["right_return"] = merged["close_right"].pct_change(return_window_days) * 100
    merged["spread"] = merged["left_return"] - merged["right_return"]
    merged = merged.dropna(subset=["left_return", "right_return", "spread"])
    if merged.empty:
        raise ValueError("有效收益率差值为空")

    if display_window_days > 0:
        merged = merged.tail(display_window_days)

    merged = merged.reset_index(drop=True)

    return {
        "dates": merged["date"].dt.strftime("%Y-%m-%d").tolist(),
        "left_return": merged["left_return"].round(2).tolist(),
        "right_return": merged["right_return"].round(2).tolist(),
        "spread": merged["spread"].round(2).tolist(),
    }


def build_style_rotation_preview_payload(
    *,
    left_df: pd.DataFrame,
    right_df: pd.DataFrame,
    left_symbol: str = FIXED_LEFT_SYMBOL,
    left_name: str = FIXED_LEFT_NAME,
    right_symbol: str = FIXED_RIGHT_SYMBOL,
    right_name: str = FIXED_RIGHT_NAME,
    return_window_days: int = DEFAULT_RETURN_WINDOW_DAYS,
    display_window_days: int = DEFAULT_DISPLAY_WINDOW_DAYS,
) -> dict[str, Any]:
    preview = calculate_style_rotation_preview(
        left_df=left_df,
        right_df=right_df,
        return_window_days=return_window_days,
        display_window_days=display_window_days,
    )
    return {
        "meta": {
            "left_symbol": left_symbol,
            "left_name": left_name,
            "right_symbol": right_symbol,
            "right_name": right_name,
            "return_window_days": return_window_days,
            "display_window_days": display_window_days,
        },
        "series": preview,
    }


def fetch_index_history(symbol: str) -> pd.DataFrame:
    end_date = pd.Timestamp.today().normalize()
    start_date = end_date - pd.Timedelta(days=365 * 10)
    start_str = start_date.strftime("%Y%m%d")
    end_str = end_date.strftime("%Y%m%d")

    frame = md.fetch_index_data(
        symbol,
        start_str,
        end_str,
        tickflow_daily_count=STYLE_ROTATION_TICKFLOW_DAILY_COUNT,
    )
    normalized = normalize_price_frame(frame)
    if normalized.empty:
        raise RuntimeError(f"指数历史数据规范化后为空: {symbol}")
    return normalized


def fetch_etf_history(symbol: str) -> pd.DataFrame:
    rows = etf_analysis.load_nav_rows(symbol)
    frame = pd.DataFrame(
        {
            "date": [row.get("trdDt") for row in rows],
            "close": [row.get("adjUnitNav") for row in rows],
        }
    )
    normalized = normalize_price_frame(frame)
    if normalized.empty:
        raise RuntimeError(f"ETF 历史数据规范化后为空: {symbol}")
    return normalized


def collect_style_rotation_preview_payload(
    *,
    return_window_days: int = DEFAULT_RETURN_WINDOW_DAYS,
    display_window_days: int = DEFAULT_DISPLAY_WINDOW_DAYS,
) -> dict[str, Any]:
    left_df = fetch_index_history(FIXED_LEFT_SYMBOL)
    right_df = fetch_index_history(FIXED_RIGHT_SYMBOL)
    return build_style_rotation_preview_payload(
        left_df=left_df,
        right_df=right_df,
        left_symbol=FIXED_LEFT_SYMBOL,
        left_name=FIXED_LEFT_NAME,
        right_symbol=FIXED_RIGHT_SYMBOL,
        right_name=FIXED_RIGHT_NAME,
        return_window_days=return_window_days,
        display_window_days=display_window_days,
    )


def collect_etf_style_rotation_preview_payload(
    *,
    return_window_days: int = DEFAULT_ETF_RETURN_WINDOW_DAYS,
    display_window_days: int = DEFAULT_ETF_DISPLAY_WINDOW_DAYS,
) -> dict[str, Any]:
    left_df = fetch_etf_history(FIXED_ETF_LEFT_SYMBOL)
    right_df = fetch_etf_history(FIXED_ETF_RIGHT_SYMBOL)
    return build_style_rotation_preview_payload(
        left_df=left_df,
        right_df=right_df,
        left_symbol=FIXED_ETF_LEFT_SYMBOL,
        left_name=FIXED_ETF_LEFT_NAME,
        right_symbol=FIXED_ETF_RIGHT_SYMBOL,
        right_name=FIXED_ETF_RIGHT_NAME,
        return_window_days=return_window_days,
        display_window_days=display_window_days,
    )
