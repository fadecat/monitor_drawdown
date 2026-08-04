"""集思录 20 日涨幅 ETF 轮动策略。

数据源：集思录 ETF/QDII detail_hists 接口（收盘价 + 单位净值）。
选股：20 日涨幅（收盘价）> 0 中取最大者为次日持仓；全 <= 0 时空仓持有 511880。
净值：组合净值起始 1.0，T 日净值用 T-1 收盘已决定的持仓更新（无未来函数）。
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import requests
import yaml

import jisilu_login as jl


BEIJING_TZ = timezone(timedelta(hours=8))
DEFAULT_CONFIG_PATH = "etf_rotation_20d_config.yaml"
DEFAULT_STATE_PATH = "data_state/etf_rotation_20d_state.json"
JISILU_DETAIL_HISTS_URL = "https://www.jisilu.cn/data/{category}/detail_hists/"
HISTORY_ROWS = 50
EASTMONEY_LOOKBACK_CALENDAR_DAYS = 90

DETAIL_HEADERS = {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Origin": "https://www.jisilu.cn",
    "Referer": "https://www.jisilu.cn/data/etf/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
    ),
    "X-Requested-With": "XMLHttpRequest",
}

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


# ----------------------------- 通用工具 ----------------------------------- #
def now_in_beijing() -> datetime:
    return datetime.now(BEIJING_TZ)


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


def load_strategy_config(config_path: str = DEFAULT_CONFIG_PATH) -> Dict[str, Any]:
    with open(config_path, "r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}
    if not data.get("universe"):
        raise ValueError("配置缺少 universe")
    if not data.get("fallback_holding"):
        raise ValueError("配置缺少 fallback_holding")
    data.setdefault("strategy", {})
    data["strategy"].setdefault("lookback_days", 20)
    data["strategy"].setdefault("initial_nav", 1.0)
    data.setdefault("state_path", DEFAULT_STATE_PATH)
    return data


def load_jisilu_credentials() -> Tuple[str, str]:
    import local_env

    local_values = local_env.load_local_env(".env.local")
    username = local_env.get_env_value("JISILU_USERNAME", local_values) or os.getenv("JISILU_USERNAME", "")
    password = local_env.get_env_value("JISILU_PASSWORD", local_values) or os.getenv("JISILU_PASSWORD", "")
    return username.strip(), password.strip()


def code_name_map(config: Dict[str, Any]) -> Dict[str, str]:
    names = {t["code"]: t["name"] for t in config["universe"]}
    fb = config["fallback_holding"]
    names[fb["code"]] = fb["name"]
    return names


# ----------------------------- 数据层（网络） ------------------------------ #
def fetch_detail_history(
    category: str, code: str, cookie: str, session: requests.Session
) -> List[Dict[str, Any]]:
    """POST /data/{etf|qdii}/detail_hists/，返回 {date, price, nav} 升序列表。"""
    url = JISILU_DETAIL_HISTS_URL.format(category=category)
    data = {"fund_id": code, "rp": str(HISTORY_ROWS)}
    if category == "qdii":
        data["is_search"] = "1"
    resp = session.post(url, headers=DETAIL_HEADERS, data=data, timeout=15)
    resp.raise_for_status()
    rows = resp.json().get("rows", [])
    out: List[Dict[str, Any]] = []
    for row in rows:
        cell = row.get("cell", {}) if isinstance(row, dict) else {}
        if category == "etf":
            date = str(cell.get("hist_dt", "")).strip()
            price = parse_float(cell.get("trade_price"))
            nav = parse_float(cell.get("fund_nav"))
        else:
            date = str(cell.get("price_dt", "")).strip()
            price = parse_float(cell.get("price"))
            nav = parse_float(cell.get("net_value"))
        if date and price is not None:
            out.append({"date": date, "price": price, "nav": nav})
    deduped = {r["date"]: r for r in out}
    return [deduped[d] for d in sorted(deduped)]


def fetch_etf_list_realtime(
    cookie: str, session: requests.Session
) -> Dict[str, Dict[str, Any]]:
    payload = jl.fetch_etf_list(cookie, session=session)
    result: Dict[str, Dict[str, Any]] = {}
    for row in payload.get("rows", []):
        cell = row.get("cell", {}) if isinstance(row, dict) else {}
        fid = str(cell.get("fund_id", "")).strip()
        if not fid:
            continue
        result[fid] = {
            "price": parse_float(cell.get("price")),
            "last_dt": str(cell.get("last_dt", "")).strip(),
            "last_time": str(cell.get("last_time", "")).strip(),
        }
    return result


def fetch_eastmoney_series(
    code: str, calendar_days: int = EASTMONEY_LOOKBACK_CALENDAR_DAYS
) -> Dict[str, float]:
    """通过 monitor_drawdown.fetch_etf_data（akshare/eastmoney）取收盘价序列。"""
    try:
        import monitor_drawdown as md
    except Exception as exc:  # pragma: no cover
        logger.warning("无法加载 monitor_drawdown: %s", exc)
        return {}
    end = now_in_beijing().date()
    start = end - timedelta(days=calendar_days)
    try:
        df = md.fetch_etf_data(code, start.strftime("%Y%m%d"), end.strftime("%Y%m%d"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("eastmoney 获取 %s 失败: %s", code, exc)
        return {}
    mapping: Dict[str, float] = {}
    for _, row in df.iterrows():
        d = pd.Timestamp(row["date"]).strftime("%Y-%m-%d")
        value = parse_float(row["close"])
        if value is not None:
            mapping[d] = value
    return mapping


def load_universe_prices(
    config: Dict[str, Any], cookie: str, session: requests.Session
) -> Tuple[pd.DataFrame, pd.DataFrame, Optional[str], Dict[str, Dict[str, Any]]]:
    universe = config["universe"]
    fallback_code = config["fallback_holding"]["code"]
    price_series: Dict[str, Dict[str, float]] = {}
    nav_series: Dict[str, Dict[str, float]] = {}

    for target in universe:
        code = target["code"]
        category = target["jisilu_category"]
        hist = fetch_detail_history(category, code, cookie, session)
        price_series[code] = {r["date"]: r["price"] for r in hist}
        nav_series[code] = {r["date"]: r["nav"] for r in hist if r["nav"] is not None}
        logger.info("集思录 %s/%s 历史行数 %d", category, code, len(hist))

    # 511880 全量历史来自 eastmoney（集思录无此标的）
    price_series[fallback_code] = fetch_eastmoney_series(fallback_code)

    all_dates = set()
    for mapping in price_series.values():
        all_dates.update(mapping.keys())
    latest_date = max(all_dates) if all_dates else None

    realtime = fetch_etf_list_realtime(cookie, session)

    # ETF detail_hists 通常滞后一日，用 etf_list 实时价补当日收盘价
    if latest_date:
        for target in universe:
            code = target["code"]
            if target["jisilu_category"] != "etf":
                continue
            if latest_date in price_series.get(code, {}):
                continue
            rt = realtime.get(code)
            if rt and rt.get("last_dt") == latest_date and rt.get("price") is not None:
                price_series.setdefault(code, {})[latest_date] = rt["price"]
                logger.info("etf_list 补价 %s @ %s = %s", code, latest_date, rt["price"])
            else:
                em = fetch_eastmoney_series(code)
                if latest_date in em:
                    price_series.setdefault(code, {})[latest_date] = em[latest_date]
                    logger.info("eastmoney 补价 %s @ %s = %s", code, latest_date, em[latest_date])
                else:
                    logger.warning("%s 缺当日收盘价，将前填充", code)

    price_frame = build_aligned_frame(price_series)
    nav_frame = build_aligned_frame(nav_series)
    if not price_frame.empty and not nav_frame.empty:
        nav_frame = nav_frame.reindex(price_frame.index).ffill()
    return price_frame, nav_frame, latest_date, realtime


# ----------------------------- 策略层（纯函数） ---------------------------- #
def build_aligned_frame(series_by_code: Dict[str, Dict[str, float]]) -> pd.DataFrame:
    series_list: List[pd.Series] = []
    for code, mapping in series_by_code.items():
        if not mapping:
            continue
        s = pd.Series(mapping, name=code, dtype=float)
        s = s[~s.index.duplicated(keep="last")]
        series_list.append(s)
    if not series_list:
        return pd.DataFrame()
    frame = pd.concat(series_list, axis=1).sort_index()
    frame = frame[~frame.index.duplicated(keep="first")]
    return frame.ffill()


def compute_returns_at(
    frame: pd.DataFrame, idx: int, universe_codes: List[str], lookback: int
) -> Dict[str, float]:
    base_idx = idx - lookback
    if base_idx < 0 or idx >= len(frame):
        return {}
    returns: Dict[str, float] = {}
    for code in universe_codes:
        if code not in frame.columns:
            continue
        base = frame.iloc[base_idx][code]
        cur = frame.iloc[idx][code]
        if pd.notna(base) and pd.notna(cur) and float(base) > 0:
            returns[code] = float(cur) / float(base) - 1.0
    return returns


def daily_return_at(frame: pd.DataFrame, code: str, idx: int) -> float:
    if code not in frame.columns or idx <= 0:
        return 0.0
    prev = frame.iloc[idx - 1][code]
    cur = frame.iloc[idx][code]
    if pd.notna(prev) and pd.notna(cur) and float(prev) > 0:
        return float(cur) / float(prev) - 1.0
    return 0.0


def select_holding(returns: Dict[str, float], fallback_code: str) -> str:
    positive = {c: r for c, r in returns.items() if r > 0}
    if not positive:
        return fallback_code
    return max(positive, key=positive.get)


def replay_forward(
    frame: pd.DataFrame,
    nav_frame: pd.DataFrame,
    universe_codes: List[str],
    fallback_code: str,
    lookback: int,
    start_idx: int,
    start_nav: float,
) -> Tuple[List[Dict[str, Any]], float, str]:
    """从 start_idx 之后逐日推进。无未来函数：start_idx 的信号决定 start_idx+1 的持仓。"""
    entries: List[Dict[str, Any]] = []
    nav = start_nav
    prev_signal = compute_returns_at(frame, start_idx, universe_codes, lookback)
    for j in range(start_idx + 1, len(frame)):
        holding = select_holding(prev_signal, fallback_code)
        prev_nav = nav
        ret = daily_return_at(frame, holding, j)
        nav = prev_nav * (1.0 + ret)
        signals = compute_returns_at(frame, j, universe_codes, lookback)
        unit_navs: Dict[str, Optional[float]] = {}
        if nav_frame is not None and j < len(nav_frame):
            row = nav_frame.iloc[j]
            for code in universe_codes:
                if code in nav_frame.columns:
                    val = row[code]
                    unit_navs[code] = None if pd.isna(val) else round(float(val), 4)
        entries.append(
            {
                "date": str(frame.index[j]),
                "holding": holding,
                "nav": round(nav, 6),
                "prev_nav": round(prev_nav, 6),
                "daily_return": round(ret, 6),
                "signals": {c: round(r, 6) for c, r in signals.items()},
                "unit_navs": unit_navs,
            }
        )
        prev_signal = signals
    next_holding = select_holding(prev_signal, fallback_code)
    return entries, nav, next_holding


def backfill(
    frame: pd.DataFrame,
    nav_frame: pd.DataFrame,
    universe_codes: List[str],
    fallback_code: str,
    lookback: int,
    initial_nav: float,
) -> Tuple[List[Dict[str, Any]], float, str]:
    start_idx = lookback
    if len(frame) <= start_idx + 1:
        raise RuntimeError(
            f"历史数据不足：需要 > {start_idx + 1} 个交易日，实际 {len(frame)}"
        )
    return replay_forward(
        frame, nav_frame, universe_codes, fallback_code, lookback, start_idx, initial_nav
    )


# ----------------------------- 状态持久化 --------------------------------- #
def load_state(state_path: str) -> Optional[Dict[str, Any]]:
    path = Path(state_path)
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else None


def save_state(state_path: str, state: Dict[str, Any]) -> None:
    path = Path(state_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def fresh_state(
    config: Dict[str, Any],
    latest_date: str,
    entries: List[Dict[str, Any]],
    nav: float,
    next_holding: str,
) -> Dict[str, Any]:
    return {
        "strategy": "etf_rotation_20d",
        "last_run_date": latest_date,
        "portfolio_nav": round(nav, 6),
        "next_holding": next_holding,
        "initial_nav": config["strategy"]["initial_nav"],
        "lookback_days": config["strategy"]["lookback_days"],
        "updated_at": now_in_beijing().strftime("%Y-%m-%d %H:%M:%S"),
        "holdings_history": entries,
    }


# ----------------------------- 编排 --------------------------------------- #
def run_strategy(
    config_path: str = DEFAULT_CONFIG_PATH,
    state_path: Optional[str] = None,
    cookie: Optional[str] = None,
    session: Optional[requests.Session] = None,
) -> Optional[Dict[str, Any]]:
    config = load_strategy_config(config_path)
    state_path = state_path or config["state_path"]
    universe_codes = [t["code"] for t in config["universe"]]
    fallback_code = config["fallback_holding"]["code"]
    lookback = config["strategy"]["lookback_days"]
    initial_nav = config["strategy"]["initial_nav"]

    own_session = False
    if cookie is None or session is None:
        username, password = load_jisilu_credentials()
        if not username or not password:
            raise RuntimeError("缺少 JISILU_USERNAME/JISILU_PASSWORD")
        cookie = jl.login_jisilu(username, password)
        if not cookie:
            raise RuntimeError("集思录登录失败")
        session = requests.Session()
        jl.apply_cookie_string(session, cookie)
        own_session = True

    try:
        price_frame, nav_frame, latest_date, _ = load_universe_prices(config, cookie, session)
    finally:
        if own_session:
            session.close()

    if latest_date is None or price_frame.empty:
        logger.warning("未获取到任何价格数据，退出")
        return None

    state = load_state(state_path)

    if state is None or not state.get("holdings_history"):
        entries, nav, next_holding = backfill(
            price_frame, nav_frame, universe_codes, fallback_code, lookback, initial_nav
        )
        state = fresh_state(config, latest_date, entries, nav, next_holding)
        logger.info("回填完成：%d 个交易日，组合净值 %.4f，次日持仓 %s", len(entries), nav, next_holding)
    else:
        last_date = state["last_run_date"]
        if latest_date <= last_date:
            logger.info("无新交易日（最新 %s <= 上次 %s），跳过", latest_date, last_date)
            return state
        if last_date in price_frame.index:
            start_idx = int(price_frame.index.get_loc(last_date))
            entries, nav, next_holding = replay_forward(
                price_frame, nav_frame, universe_codes, fallback_code, lookback, start_idx, state["portfolio_nav"]
            )
            state["holdings_history"].extend(entries)
            state["last_run_date"] = latest_date
            state["portfolio_nav"] = round(nav, 6)
            state["next_holding"] = next_holding
            state["updated_at"] = now_in_beijing().strftime("%Y-%m-%d %H:%M:%S")
            logger.info("新增 %d 个交易日，组合净值 %.4f，次日持仓 %s", len(entries), nav, next_holding)
        else:
            logger.warning("上次运行日期 %s 不在数据窗口内，重新回填", last_date)
            entries, nav, next_holding = backfill(
                price_frame, nav_frame, universe_codes, fallback_code, lookback, initial_nav
            )
            state = fresh_state(config, latest_date, entries, nav, next_holding)

    save_state(state_path, state)
    return state


def build_report(state: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    names = code_name_map(config)
    history = state.get("holdings_history", [])
    latest = history[-1] if history else {}
    fallback_code = config["fallback_holding"]["code"]
    signals = latest.get("signals", {})
    ranking = sorted(
        ({"code": c, "name": names.get(c, c), "return_20d": r} for c, r in signals.items()),
        key=lambda x: x["return_20d"],
        reverse=True,
    )
    return {
        "as_of_date": latest.get("date"),
        "current_holding": latest.get("holding"),
        "current_holding_name": names.get(latest.get("holding", ""), ""),
        "current_nav": latest.get("nav"),
        "next_holding": state.get("next_holding"),
        "next_holding_name": names.get(state.get("next_holding", ""), ""),
        "ranking": ranking,
        "fallback_code": fallback_code,
        "fallback_name": names.get(fallback_code, ""),
        "history": history,
        "portfolio_nav": state.get("portfolio_nav"),
    }


def main() -> int:
    config = load_strategy_config()
    state = run_strategy()
    if state is None:
        return 1
    report = build_report(state, config)
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
