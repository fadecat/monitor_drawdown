import os
import time
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional, Tuple

import akshare as ak
import pandas as pd
import requests
import yaml

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None

try:
    from tickflow import TickFlow
except ImportError:  # pragma: no cover
    TickFlow = None


DEFAULT_TICKFLOW_FREE_BASE_URL = "https://free-api.tickflow.org"
DEFAULT_TICKFLOW_DAILY_COUNT = 500


BEIJING_TZ = timezone(timedelta(hours=8))

def now_in_beijing() -> datetime:
    return datetime.now(BEIJING_TZ)


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

    date_col_candidates = ["日期", "date", "trade_date", "交易日期", "净值日期"]
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


def dedupe_keep_order(items: List[str]) -> List[str]:
    seen = set()
    deduped: List[str] = []
    for item in items:
        if item and item not in seen:
            deduped.append(item)
            seen.add(item)
    return deduped


def build_tickflow_etf_symbols(code: str) -> List[str]:
    raw = code.strip().lower()
    digits = extract_index_digits(raw)
    has_sz_hint = raw.startswith("sz") or raw.endswith(".sz")
    has_sh_hint = raw.startswith("sh") or raw.endswith(".sh")

    candidates: List[str] = []

    if raw.endswith(".sz") and len(digits) == 6:
        candidates.append(f"{digits}.SZ")
    if raw.endswith(".sh") and len(digits) == 6:
        candidates.append(f"{digits}.SH")

    if len(digits) == 6:
        if has_sz_hint:
            candidates.extend([f"{digits}.SZ", f"{digits}.SH"])
        elif has_sh_hint:
            candidates.extend([f"{digits}.SH", f"{digits}.SZ"])
        else:
            primary_exchange = "SH" if digits[0] in {"5", "6", "9"} else "SZ"
            secondary_exchange = "SZ" if primary_exchange == "SH" else "SH"
            candidates.extend([f"{digits}.{primary_exchange}", f"{digits}.{secondary_exchange}"])

    return dedupe_keep_order(candidates)


def build_tickflow_index_symbols(code: str) -> List[str]:
    raw = code.strip().lower()
    digits = extract_index_digits(raw)
    has_sz_hint = raw.startswith("sz") or raw.endswith(".sz")
    has_sh_hint = raw.startswith("sh") or raw.endswith(".sh")

    candidates: List[str] = []

    if raw.endswith(".sz") and len(digits) == 6:
        candidates.append(f"{digits}.SZ")
    if raw.endswith(".sh") and len(digits) == 6:
        candidates.append(f"{digits}.SH")

    if len(digits) == 6:
        if has_sz_hint:
            candidates.extend([f"{digits}.SZ", f"{digits}.SH"])
        elif has_sh_hint:
            candidates.extend([f"{digits}.SH", f"{digits}.SZ"])
        elif digits.startswith(("39", "98")):
            candidates.extend([f"{digits}.SZ", f"{digits}.SH"])
        else:
            candidates.extend([f"{digits}.SH", f"{digits}.SZ"])

    return dedupe_keep_order(candidates)


def normalize_index_symbol_for_em(code: str) -> str:
    code = code.strip().lower()
    if code.startswith(("csi", "sh", "sz")):
        return code
    if len(code) == 6 and code.isdigit():
        return f"csi{code}"
    return code


def extract_index_digits(code: str) -> str:
    raw = code.strip().lower()
    digits = "".join(ch for ch in raw if ch.isdigit())
    return digits[-6:] if len(digits) >= 6 else digits


def build_em_index_symbols(code: str) -> List[str]:
    raw = code.strip().lower()
    digits = extract_index_digits(raw)

    has_sz_hint = raw.startswith("sz") or raw.endswith(".sz")
    has_sh_hint = raw.startswith("sh") or raw.endswith(".sh")
    has_csi_hint = raw.startswith("csi")

    candidates: List[str] = []

    # 显式带交易所后缀时优先转换为 EM 支持格式，如 980081.sz -> sz980081
    if raw.endswith(".sz") and len(digits) == 6:
        candidates.append(f"sz{digits}")
    if raw.endswith(".sh") and len(digits) == 6:
        candidates.append(f"sh{digits}")

    if raw and "." not in raw:
        candidates.append(raw)

    if len(digits) == 6:
        if has_sz_hint:
            candidates.extend([f"sz{digits}", digits, f"sh{digits}", f"csi{digits}"])
        elif has_sh_hint:
            candidates.extend([f"sh{digits}", digits, f"sz{digits}", f"csi{digits}"])
        elif has_csi_hint:
            candidates.extend([f"csi{digits}", digits, f"sz{digits}", f"sh{digits}"])
        else:
            # 无前缀时根据常见规则给优先级
            if digits.startswith(("39", "98")):
                candidates.extend([f"sz{digits}", f"csi{digits}", f"sh{digits}", digits])
            elif digits.startswith(("93",)):
                candidates.extend([f"csi{digits}", f"sz{digits}", f"sh{digits}", digits])
            elif digits.startswith(("00", "88", "99")):
                candidates.extend([f"sh{digits}", f"csi{digits}", f"sz{digits}", digits])
            else:
                candidates.extend([f"csi{digits}", f"sz{digits}", f"sh{digits}", digits])

    # 去重并保持顺序
    return dedupe_keep_order(candidates)


def build_numeric_index_symbols(code: str) -> List[str]:
    raw = code.strip()
    digits = extract_index_digits(raw)
    candidates = [digits, raw]
    return dedupe_keep_order([item.strip() for item in candidates])


def parse_float(value: object) -> Optional[float]:
    if value is None:
        return None

    text = str(value).strip().replace(",", "")
    if not text or text == "-":
        return None

    try:
        return float(text)
    except ValueError:
        return None


def parse_optional_date(value: object) -> Optional[pd.Timestamp]:
    if value is None:
        return None

    text = str(value).strip()
    if not text or text == "-":
        return None

    parsed = pd.to_datetime(text, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.normalize()


def build_tickflow_client() -> Optional["TickFlow"]:
    if TickFlow is None:
        return None

    timeout = float(os.getenv("TICKFLOW_TIMEOUT", "15"))
    api_key = os.getenv("TICKFLOW_API_KEY")

    if api_key:
        return TickFlow(
            api_key=api_key,
            base_url=os.getenv("TICKFLOW_BASE_URL"),
            timeout=timeout,
        )

    return TickFlow(
        api_key=None,
        base_url=os.getenv("TICKFLOW_FREE_BASE_URL", DEFAULT_TICKFLOW_FREE_BASE_URL),
        timeout=timeout,
    )


def clip_dataframe_by_date(df: pd.DataFrame, start_date: str, end_date: str) -> pd.DataFrame:
    if df.empty:
        return df

    start_ts = pd.to_datetime(start_date, format="%Y%m%d")
    end_ts = pd.to_datetime(end_date, format="%Y%m%d")
    return df[(df["date"] >= start_ts) & (df["date"] <= end_ts)].copy()


def fetch_tickflow_klines(symbols: List[str], start_date: str, end_date: str) -> pd.DataFrame:
    client = build_tickflow_client()
    if client is None:
        raise RuntimeError("tickflow 未安装")

    errors: List[str] = []
    try:
        for symbol in symbols:
            try:
                raw = run_with_retry(
                    "tickflow.klines.get",
                    lambda symbol=symbol: client.klines.get(
                        symbol,
                        period="1d",
                        count=DEFAULT_TICKFLOW_DAILY_COUNT,
                        adjust="none",
                        as_dataframe=True,
                    ),
                )
                normalized = clip_dataframe_by_date(normalize_dataframe(raw), start_date, end_date)
                if not normalized.empty:
                    return normalized
                errors.append(f"tickflow.klines.get({symbol}): empty result")
                print(f"[WARN] TickFlow 返回空数据，尝试下一个符号: {symbol}")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"tickflow.klines.get({symbol}): {exc}")
                print(f"[WARN] TickFlow 数据源失败，尝试下一个符号: {symbol} -> {exc}")
    finally:
        client.close()

    raise RuntimeError("; ".join(errors) if errors else "TickFlow 未返回有效数据")


def is_retryable_error(exc: Exception) -> bool:
    if isinstance(exc, requests.exceptions.RequestException):
        return True
    if httpx is not None and isinstance(exc, httpx.HTTPError):
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

    tickflow_symbols = build_tickflow_etf_symbols(code)
    if tickflow_symbols:
        try:
            return fetch_tickflow_klines(tickflow_symbols, start_date, end_date)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"tickflow({tickflow_symbols}): {exc}")
            print(f"[WARN] ETF TickFlow 数据源失败，准备尝试 AkShare: {exc}")

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
                print(f"[WARN] ETF 主数据源失败，准备尝试备源: fund_etf_hist_em({symbol}) -> {exc}")

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
    errors: List[str] = []

    tickflow_symbols = build_tickflow_index_symbols(code)
    if tickflow_symbols:
        try:
            return fetch_tickflow_klines(tickflow_symbols, start_date, end_date)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"tickflow({tickflow_symbols}): {exc}")
            print(f"[WARN] 指数 TickFlow 数据源失败，准备尝试 AkShare: {exc}")

    # 主接口: 东方财富指数日线（对 csi930955 实测更稳定）
    if hasattr(ak, "stock_zh_index_daily_em"):
        for symbol_em in build_em_index_symbols(code):
            try:
                raw = run_with_retry(
                    "stock_zh_index_daily_em",
                    lambda: ak.stock_zh_index_daily_em(symbol=symbol_em, start_date=start_date, end_date=end_date),
                )
                normalized = normalize_dataframe(raw)
                if not normalized.empty:
                    return normalized
                errors.append(f"stock_zh_index_daily_em({symbol_em}): empty result")
                print(f"[WARN] 指数主数据源返回空数据，尝试下一个符号: {symbol_em}")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"stock_zh_index_daily_em({symbol_em}): {exc}")
                print(f"[WARN] 指数主数据源失败，尝试下一个符号: {symbol_em} -> {exc}")

    # 备源1: 东方财富另一接口
    if hasattr(ak, "index_zh_a_hist"):
        for symbol_hist in build_numeric_index_symbols(code):
            try:
                raw = run_with_retry(
                    "index_zh_a_hist",
                    lambda: ak.index_zh_a_hist(
                        symbol=symbol_hist, period="daily", start_date=start_date, end_date=end_date
                    ),
                )
                normalized = normalize_dataframe(raw)
                if not normalized.empty:
                    return normalized
                errors.append(f"index_zh_a_hist({symbol_hist}): empty result")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"index_zh_a_hist({symbol_hist}): {exc}")
                print(f"[WARN] 指数备源1失败，准备尝试备源2: index_zh_a_hist({symbol_hist}) -> {exc}")

    # 备源2: 中证官网指数历史
    if hasattr(ak, "stock_zh_index_hist_csindex"):
        for symbol_csindex in build_numeric_index_symbols(code):
            try:
                raw = run_with_retry(
                    "stock_zh_index_hist_csindex",
                    lambda: ak.stock_zh_index_hist_csindex(
                        symbol=symbol_csindex, start_date=start_date, end_date=end_date
                    ),
                )
                normalized = normalize_dataframe(raw)
                if not normalized.empty:
                    return normalized
                errors.append(f"stock_zh_index_hist_csindex({symbol_csindex}): empty result")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"stock_zh_index_hist_csindex({symbol_csindex}): {exc}")

    error_message = "; ".join(errors) if errors else "未找到可用指数接口"
    raise RuntimeError(f"指数数据获取失败: {error_message}")


def fetch_jisilu_etf_rows(username: str, password: str) -> List[Dict]:
    from jisilu_login import fetch_etf_list, login_jisilu

    cookie = login_jisilu(username, password)
    if not cookie:
        raise RuntimeError("集思录登录失败，无法获取 ETF 列表")

    payload = fetch_etf_list(cookie)
    rows = payload.get("rows", [])
    if not isinstance(rows, list):
        raise RuntimeError("集思录 ETF 列表格式异常")
    return rows


def find_jisilu_etf_by_fund_id(rows: List[Dict], fund_code: str) -> Optional[Dict]:
    digits = extract_index_digits(fund_code)
    if not digits:
        return None

    for row in rows:
        cell = row.get("cell", {})
        if not isinstance(cell, dict):
            continue
        if str(cell.get("fund_id", "")).strip() == digits:
            return cell
    return None


def find_jisilu_index_etf_candidates(rows: List[Dict], index_code: str) -> List[Dict]:
    digits = extract_index_digits(index_code)
    if not digits:
        return []

    candidates: List[Dict] = []
    for row in rows:
        cell = row.get("cell", {})
        if not isinstance(cell, dict):
            continue
        if str(cell.get("index_id", "")).strip() == digits:
            candidates.append(cell)
    return candidates


def select_best_jisilu_index_etf(candidates: List[Dict]) -> Optional[Dict]:
    if not candidates:
        return None

    def sort_key(cell: Dict) -> Tuple[int, float, float]:
        has_price = 1 if parse_float(cell.get("price")) is not None else 0
        volume = parse_float(cell.get("volume")) or -1.0
        amount = parse_float(cell.get("amount")) or -1.0
        return has_price, volume, amount

    return max(candidates, key=sort_key)


def build_etf_realtime_patch(df: pd.DataFrame, etf_cell: Dict, current_time: Optional[datetime] = None) -> Optional[Dict]:
    if df.empty:
        return None

    sorted_df = df.sort_values("date").reset_index(drop=True)
    last_row = sorted_df.iloc[-1]
    last_date = pd.to_datetime(last_row["date"]).normalize()
    patch_date = pd.Timestamp((current_time or now_in_beijing()).date())

    if patch_date <= last_date:
        return None

    etf_price = parse_float(etf_cell.get("price"))
    if etf_price is None or etf_price <= 0:
        return None

    return {
        "date": patch_date,
        "close": etf_price,
        "fund_id": str(etf_cell.get("fund_id", "")).strip(),
        "fund_nm": str(etf_cell.get("fund_nm", "")).strip(),
        "index_nm": str(etf_cell.get("index_nm", "")).strip(),
        "last_time": str(etf_cell.get("last_time", "")).strip(),
        "pre_close": parse_float(etf_cell.get("pre_close")),
        "increase_rt": parse_float(etf_cell.get("increase_rt")),
    }


def build_index_realtime_patch(df: pd.DataFrame, etf_cell: Dict, current_time: Optional[datetime] = None) -> Optional[Dict]:
    if df.empty:
        return None

    sorted_df = df.sort_values("date").reset_index(drop=True)
    last_row = sorted_df.iloc[-1]
    last_date = pd.to_datetime(last_row["date"]).normalize()

    patch_date = parse_optional_date(etf_cell.get("idx_price_dt"))
    if patch_date is None:
        patch_date = pd.Timestamp((current_time or now_in_beijing()).date())

    if patch_date <= last_date:
        return None

    etf_price = parse_float(etf_cell.get("price"))
    etf_pre_close = parse_float(etf_cell.get("pre_close"))
    index_last_close = parse_float(last_row["close"])
    if etf_price is None or etf_pre_close is None or index_last_close is None:
        return None
    if etf_pre_close <= 0 or index_last_close <= 0:
        return None

    etf_return = etf_price / etf_pre_close - 1
    patched_close = index_last_close * (1 + etf_return)
    return {
        "date": patch_date,
        "close": patched_close,
        "fund_id": str(etf_cell.get("fund_id", "")).strip(),
        "fund_nm": str(etf_cell.get("fund_nm", "")).strip(),
        "index_id": str(etf_cell.get("index_id", "")).strip(),
        "index_nm": str(etf_cell.get("index_nm", "")).strip(),
        "etf_price": etf_price,
        "etf_pre_close": etf_pre_close,
        "etf_return": etf_return,
        "last_time": str(etf_cell.get("last_time", "")).strip(),
    }


def apply_index_realtime_patch(df: pd.DataFrame, patch: Dict) -> pd.DataFrame:
    patched_df = df.copy()
    patched_df["date"] = pd.to_datetime(patched_df["date"], errors="coerce")

    patch_date = pd.to_datetime(patch["date"]).normalize()
    mask = patched_df["date"].dt.normalize() == patch_date
    if mask.any():
        patched_df.loc[mask, "close"] = patch["close"]
    else:
        patched_df = pd.concat(
            [patched_df, pd.DataFrame([{"date": patch_date, "close": patch["close"]}])],
            ignore_index=True,
        )

    return patched_df.sort_values("date").reset_index(drop=True)


def patch_etf_dataframe_with_jisilu(
    df: pd.DataFrame,
    fund_code: str,
    rows: List[Dict],
    current_time: Optional[datetime] = None,
) -> Tuple[pd.DataFrame, Optional[Dict]]:
    cell = find_jisilu_etf_by_fund_id(rows, fund_code)
    if cell is None:
        return df, None

    patch = build_etf_realtime_patch(df, cell, current_time=current_time)
    if patch is None:
        return df, None

    return apply_index_realtime_patch(df, patch), patch


def patch_index_dataframe_with_jisilu(
    df: pd.DataFrame,
    index_code: str,
    rows: List[Dict],
    current_time: Optional[datetime] = None,
) -> Tuple[pd.DataFrame, Optional[Dict]]:
    candidates = find_jisilu_index_etf_candidates(rows, index_code)
    selected = select_best_jisilu_index_etf(candidates)
    if selected is None:
        return df, None

    patch = build_index_realtime_patch(df, selected, current_time=current_time)
    if patch is None:
        return df, None

    return apply_index_realtime_patch(df, patch), patch


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


def format_number(value: float, decimals: int = 4) -> str:
    text = f"{value:.{decimals}f}".rstrip("0").rstrip(".")
    return text if text else "0"


def format_percent(value: float, decimals: int = 2) -> str:
    text = f"{value:.{decimals}f}".rstrip("0").rstrip(".")
    return text if text else "0"


def build_webhook_markdown_content(triggered_items: List[Dict], current_time: Optional[datetime] = None) -> str:
    now_str = (current_time or now_in_beijing()).strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "**📉 核心标的监控告警**",
        f"> 触发时间: <font color=\"comment\">{now_str}</font>",
        "",
    ]

    for item in triggered_items:
        name = item["name"]
        code = item["code"]
        drawdown_pct = item["drawdown"] * 100
        current_price = format_number(item["current_price"], decimals=4)
        peak_price = format_number(item["peak_price"], decimals=4)
        peak_date = item["peak_date"]

        if abs(drawdown_pct) < 1e-8:
            lines.extend(
                [
                    f"🚀 **{name} ({code})**",
                    "> 突破状态: <font color=\"info\">**创近期新高！**</font>",
                    f"> 当前价格: **{current_price}**",
                    "",
                ]
            )
        else:
            drawdown_text = format_percent(drawdown_pct, decimals=2)
            lines.extend(
                [
                    f"🔻 **{name} ({code})**",
                    f"> 当前回撤: <font color=\"warning\">**-{drawdown_text}%**</font>",
                    f"> 当前价格: **{current_price}**",
                    f"> 历史高点: {peak_price} ({peak_date})",
                    "",
                ]
            )

    return "\n".join(lines).strip()


def build_webhook_payload(triggered_items: List[Dict], current_time: Optional[datetime] = None) -> Dict:
    return {
        "msgtype": "markdown",
        "markdown": {"content": build_webhook_markdown_content(triggered_items, current_time=current_time)},
    }


def send_webhook(webhook_url: str, triggered_items: List[Dict]) -> None:
    payload = build_webhook_payload(triggered_items)
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

    current_time = now_in_beijing()
    end = current_time.date()
    start = end - timedelta(days=365)
    start_str = start.strftime("%Y%m%d")
    end_str = end.strftime("%Y%m%d")
    print(f"[INFO] 当前北京时间: {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"[INFO] 拉取数据区间: {start_str} - {end_str}")

    triggered: List[Dict] = []
    has_patch_targets = any(str(target.get("type", "")).strip().lower() in {"etf", "index"} for target in targets)
    jisilu_rows: Optional[List[Dict]] = None

    if has_patch_targets:
        jisilu_username = os.getenv("JISILU_USERNAME", "").strip()
        jisilu_password = os.getenv("JISILU_PASSWORD", "").strip()
        if jisilu_username and jisilu_password:
            try:
                jisilu_rows = fetch_jisilu_etf_rows(jisilu_username, jisilu_password)
                print(f"[INFO] 已加载集思录 ETF 列表，共 {len(jisilu_rows)} 条。")
            except Exception as exc:  # noqa: BLE001
                print(f"[WARN] 集思录 ETF 列表加载失败，指数将不补当日价格: {exc}")
        else:
            print("[WARN] 未配置 JISILU_USERNAME/JISILU_PASSWORD，指数将不补当日价格。")

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
                if jisilu_rows:
                    df, patch = patch_etf_dataframe_with_jisilu(
                        df,
                        code,
                        jisilu_rows,
                        current_time=current_time,
                    )
                    if patch:
                        print(
                            f"[INFO] 已用集思录补齐当日 ETF: {name} ({code}) -> "
                            f"{patch['fund_nm']}({patch['fund_id']})，"
                            f"现价 {patch['close']:.4f}，"
                            f"补齐日期 {pd.to_datetime(patch['date']).strftime('%Y-%m-%d')}"
                        )
            else:
                df = fetch_index_data(code, start_str, end_str)
                if jisilu_rows:
                    df, patch = patch_index_dataframe_with_jisilu(
                        df,
                        code,
                        jisilu_rows,
                        current_time=current_time,
                    )
                    if patch:
                        print(
                            f"[INFO] 已用集思录 ETF 补齐当日指数: {name} ({code}) -> "
                            f"{patch['fund_nm']}({patch['fund_id']})，"
                            f"ETF 涨跌 {patch['etf_return']:.2%}，"
                            f"补齐日期 {pd.to_datetime(patch['date']).strftime('%Y-%m-%d')}"
                        )

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
