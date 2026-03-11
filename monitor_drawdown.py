import os
import time
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional

import akshare as ak
import pandas as pd
import requests
import yaml


def load_config(config_path: str) -> List[Dict]:
    with open(config_path, "r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}

    targets = data.get("targets", [])
    if not isinstance(targets, list):
        raise ValueError("config.yaml 中 targets 必须是列表")
    return targets


def normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["date", "close"])

    renamed = df.copy()
    renamed.columns = [str(col).strip().lower() for col in renamed.columns]

    date_col_candidates = ["日期", "date", "交易日期", "净值日期"]
    close_col_candidates = [
        "收盘",
        "收盘价",
        "close",
        "close_price",
        "closeprice",
        "单位净值",
        "累计净值",
    ]

    date_col = next((c for c in date_col_candidates if c in renamed.columns), None)
    close_col = next((c for c in close_col_candidates if c in renamed.columns), None)

    if date_col is None or close_col is None:
        raise ValueError(f"无法识别日期/收盘列，现有列: {list(renamed.columns)}")

    out = renamed[[date_col, close_col]].copy()
    out.columns = ["date", "close"]
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out["close"] = pd.to_numeric(out["close"], errors="coerce")
    out = out.dropna(subset=["date", "close"]).sort_values("date")
    return out


def add_exchange_prefix_if_needed(code: str) -> str:
    code = code.strip()
    lower = code.lower()
    if lower.startswith("sh") or lower.startswith("sz"):
        return code
    if len(code) == 6 and code.isdigit():
        return f"sh{code}" if code[0] in {"5", "6", "9"} else f"sz{code}"
    return code


def is_retryable_error(exc: Exception) -> bool:
    if isinstance(exc, requests.exceptions.RequestException):
        return True

    message = str(exc).lower()
    retry_keywords = [
        "timeout",
        "timed out",
        "connection",
        "connection aborted",
        "remote end closed",
        "max retries exceeded",
        "temporarily unavailable",
        "502",
        "503",
        "504",
    ]
    return any(keyword in message for keyword in retry_keywords)


def run_with_retry(name: str, fn: Callable[[], pd.DataFrame], retries: int = 3, base_sleep: float = 1.5) -> pd.DataFrame:
    last_error: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            return fn()
        except TypeError:
            # 参数不匹配属于接口差异，不重试
            raise
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt < retries and is_retryable_error(exc):
                wait = base_sleep * attempt
                print(f"[WARN] {name} 第 {attempt}/{retries} 次失败: {exc}，{wait:.1f}s 后重试")
                time.sleep(wait)
                continue
            raise

    if last_error:
        raise last_error
    raise RuntimeError(f"{name} 调用失败")


def fetch_etf_data(code: str, start_date: str, end_date: str) -> pd.DataFrame:
    errors: List[str] = []

    # 主接口: ETF 历史行情（优先级最高，返回标准 OHLC）
    if hasattr(ak, "fund_etf_hist_em"):
        for symbol in [code, add_exchange_prefix_if_needed(code)]:
            try:
                raw = run_with_retry(
                    "fund_etf_hist_em",
                    lambda: ak.fund_etf_hist_em(
                        symbol=symbol,
                        period="daily",
                        start_date=start_date,
                        end_date=end_date,
                        adjust="",
                    ),
                )
                normalized = normalize_dataframe(raw)
                if not normalized.empty:
                    return normalized
            except Exception as exc:  # noqa: BLE001
                errors.append(f"fund_etf_hist_em({symbol}): {exc}")

    # 降级接口: ETF 净值历史
    if hasattr(ak, "fund_etf_fund_info_em"):
        try:
            raw = run_with_retry(
                "fund_etf_fund_info_em",
                lambda: ak.fund_etf_fund_info_em(
                    fund=code,
                    start_date=start_date,
                    end_date=end_date,
                ),
            )
            normalized = normalize_dataframe(raw)
            if not normalized.empty:
                return normalized
        except Exception as exc:  # noqa: BLE001
            errors.append(f"fund_etf_fund_info_em({code}): {exc}")

    error_message = "; ".join(errors) if errors else "未找到可用 ETF 接口"
    raise RuntimeError(f"ETF 数据获取失败: {error_message}")


def fetch_index_data(code: str, start_date: str, end_date: str) -> pd.DataFrame:
    raw = run_with_retry(
        "index_zh_a_hist",
        lambda: ak.index_zh_a_hist(symbol=code, period="daily", start_date=start_date, end_date=end_date),
    )
    normalized = normalize_dataframe(raw)
    return normalized


def compute_drawdown(df: pd.DataFrame, lookback_days: int) -> Dict:
    if df.empty:
        raise ValueError("数据为空")

    window = df.tail(max(1, int(lookback_days)))
    if window.empty:
        raise ValueError("窗口内无有效数据")

    peak_idx = window["close"].idxmax()
    peak_row = window.loc[peak_idx]
    current_row = window.iloc[-1]

    peak_price = float(peak_row["close"])
    current_price = float(current_row["close"])
    if peak_price <= 0:
        raise ValueError(f"无效峰值价格: {peak_price}")

    drawdown = (peak_price - current_price) / peak_price
    return {
        "drawdown": drawdown,
        "current_price": current_price,
        "peak_price": peak_price,
        "peak_date": peak_row["date"].strftime("%Y-%m-%d"),
        "current_date": current_row["date"].strftime("%Y-%m-%d"),
        "window_size": len(window),
    }


def send_webhook(webhook_url: str, triggered_items: List[Dict]) -> None:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [f"监控触发时间: {now_str}", "触发标的:"]

    for item in triggered_items:
        lines.append(
            f"- {item['name']} ({item['code']}): "
            f"回撤 {item['drawdown'] * 100:.2f}%, "
            f"当前价 {item['current_price']:.4f}, "
            f"近期高点 {item['peak_price']:.4f} (日期 {item['peak_date']})"
        )

    payload = {"msgtype": "text", "text": {"content": "\n".join(lines)}}
    response = requests.post(webhook_url, json=payload, timeout=15)
    response.raise_for_status()
    print(f"[INFO] Webhook 发送成功，状态码: {response.status_code}")


def main() -> None:
    config_path = os.getenv("CONFIG_PATH", "./config.yaml")
    webhook_url = os.getenv("WEBHOOK_URL")

    if not webhook_url:
        raise RuntimeError("缺少环境变量 WEBHOOK_URL")

    print(f"[INFO] 使用配置文件: {config_path}")
    targets = load_config(config_path)
    if not targets:
        print("[WARN] 未配置任何监控标的，退出。")
        return

    end = datetime.now().date()
    start = end - timedelta(days=365)
    start_str = start.strftime("%Y%m%d")
    end_str = end.strftime("%Y%m%d")
    print(f"[INFO] 拉取数据区间: {start_str} - {end_str}")

    triggered: List[Dict] = []

    for target in targets:
        name = str(target.get("name", "")).strip()
        code = str(target.get("code", "")).strip()
        target_type = str(target.get("type", "")).strip().lower()
        threshold = float(target.get("threshold", 0.08))
        lookback_days = int(target.get("lookback_days", 120))

        if not name or not code or target_type not in {"etf", "index"}:
            print(f"[ERROR] 配置不完整或类型非法，已跳过: {target}")
            continue

        print(f"[INFO] 开始处理: {name} ({code}), type={target_type}, threshold={threshold:.2%}, lookback={lookback_days}")
        try:
            if target_type == "etf":
                df = fetch_etf_data(code, start_str, end_str)
            else:
                df = fetch_index_data(code, start_str, end_str)

            if df.empty:
                print(f"[WARN] {name} ({code}) 未获取到有效数据，跳过。")
                continue

            result = compute_drawdown(df, lookback_days)
            drawdown = result["drawdown"]
            print(
                f"[INFO] {name} ({code}) 数据 {len(df)} 条，窗口 {result['window_size']} 条，"
                f"最新日期 {result['current_date']}，回撤 {drawdown:.2%}"
            )

            if drawdown >= threshold:
                print(f"[ALERT] 触发阈值: {name} ({code}) 回撤 {drawdown:.2%} >= {threshold:.2%}")
                triggered.append(
                    {
                        "name": name,
                        "code": code,
                        "drawdown": drawdown,
                        "current_price": result["current_price"],
                        "peak_price": result["peak_price"],
                        "peak_date": result["peak_date"],
                    }
                )
            else:
                print(f"[INFO] 未触发: {name} ({code}) 回撤 {drawdown:.2%} < {threshold:.2%}")
        except Exception as exc:  # noqa: BLE001
            print(f"[ERROR] 处理 {name} ({code}) 失败: {exc}")
            continue

    if triggered:
        print(f"[INFO] 共 {len(triggered)} 个标的触发，准备发送通知。")
        try:
            send_webhook(webhook_url, triggered)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Webhook 发送失败: {exc}") from exc
    else:
        print("[INFO] 本次无标的触发阈值，不发送通知。")


if __name__ == "__main__":
    main()
