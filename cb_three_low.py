"""可转债三低轮动 模拟盘策略。

数据源：集思录 cb_list_new（全市场转债快照）+ redeem_list（强赎名单）。
选股：三低策略（双低值 + 溢价率 + 剩余规模 综合评分），取前 target_count+hold_tolerance 为 keep_pool。
持仓：target_count 只等权，日频再平衡；已持有且仍在 keep_pool 内的保留（容差降换手）。
净值：组合净值起始 1.0，T 日净值 = prev_nav × (1 + mean(各持仓 T-1收盘->T收盘 涨幅))，无未来函数。
仅向前记录：不回填历史（三低因子是每日快照，集思录不存历史）。

选债逻辑移植自 v2_cb_rotation/src/services/jisilu_service.py；净值跟踪对标 etf_rotation_20d。
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
import yaml

import jisilu_login as jl


BEIJING_TZ = timezone(timedelta(hours=8))
DEFAULT_CONFIG_PATH = "cb_three_low_config.yaml"
DEFAULT_STATE_PATH = "data_state/cb_three_low_state.json"

CB_LIST_URL = "https://www.jisilu.cn/data/cbnew/cb_list_new/"
CB_REDEEM_LIST_URL = "https://www.jisilu.cn/data/cbnew/redeem_list/"
CB_PAGE_SIZE = 1000
CB_ALLOWED_RATINGS = ["AAA", "AA+", "AA", "AA-", "A+", "A", "A-"]
CB_ALLOWED_MARKETS = ["shmb", "shkc", "szmb", "szcy"]
CB_FORM_DATA = {
    "fprice": "", "tprice": "", "curr_iss_amt": "", "convert_amt_ratio": "",
    "premium_rt": "", "fyear_left": "", "tyear_left": "",
    "rating_cd[]": CB_ALLOWED_RATINGS,
    "is_search": "Y",
    "market_cd[]": CB_ALLOWED_MARKETS,
    "show_blocked": "N", "min_price_only": "N", "btype": "",
    "listed": "Y", "qflag": "N", "sw_cd": "", "bond_ids": "",
    "rp": str(CB_PAGE_SIZE),
}
CB_HEADERS = {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Referer": "https://www.jisilu.cn/data/cbnew/",
    "Origin": "https://www.jisilu.cn",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
    ),
    "X-Requested-With": "XMLHttpRequest",
}

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


# ── 通用工具 ──────────────────────────────────────────────────────────────────
def now_in_beijing() -> datetime:
    return datetime.now(BEIJING_TZ)


def to_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def load_strategy_config(config_path: str = DEFAULT_CONFIG_PATH) -> Dict[str, Any]:
    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if "strategy" not in data:
        raise ValueError("配置缺少 strategy")
    s = data["strategy"]
    s.setdefault("target_count", 10)
    s.setdefault("hold_tolerance", 5)
    s.setdefault("initial_nav", 1.0)
    s.setdefault("factors", [])
    s.setdefault("exclusion_rules", [])
    s.setdefault("excluded_redeem_icons", ["R", "O", "B"])
    s.setdefault("redeem_safe_days", 2)
    s.setdefault("min_listing_days", 0)
    s.setdefault("excluded_bond_codes", [])
    data.setdefault("state_path", DEFAULT_STATE_PATH)
    return data


def load_jisilu_credentials() -> Tuple[str, str]:
    import local_env

    local_values = local_env.load_local_env(".env.local")
    username = local_env.get_env_value("JISILU_USERNAME", local_values) or os.getenv("JISILU_USERNAME", "")
    password = local_env.get_env_value("JISILU_PASSWORD", local_values) or os.getenv("JISILU_PASSWORD", "")
    return username.strip(), password.strip()


def normalize_bond_code(code: Optional[str]) -> str:
    """6 位代码归一化为 .SH/.SZ 后缀形式（11 开头沪市，12 开头深市）。"""
    if code is None:
        return ""
    n = str(code).strip().upper()
    if not n:
        return ""
    if n.endswith(".SH") or n.endswith(".SZ"):
        return n
    if len(n) == 6 and n.isdigit():
        if n.startswith("11"):
            return f"{n}.SH"
        if n.startswith("12"):
            return f"{n}.SZ"
    return n


def build_bond_code_match_set(codes: List[Any]) -> set:
    """构建匹配集，同时接受 6 位与带后缀两种写法。"""
    match_set: set = set()
    for item in codes or []:
        code = item.get("code") if isinstance(item, dict) else item
        raw = str(code).strip().upper()
        if not raw:
            continue
        match_set.add(raw)
        normalized = normalize_bond_code(raw)
        if normalized:
            match_set.add(normalized)
    return match_set


# ── 数据层 ────────────────────────────────────────────────────────────────────
def fetch_cb_list(session: requests.Session) -> List[Dict[str, Any]]:
    """POST cb_list_new，返回 rows。≤30 条视为未登录/会话失效，抛错。"""
    params = {"___jsl": f"LST___t={int(time.time() * 1000)}"}
    resp = session.post(CB_LIST_URL, headers=CB_HEADERS, params=params, data=CB_FORM_DATA, timeout=15)
    resp.raise_for_status()
    rows = resp.json().get("rows", [])
    if len(rows) <= 30:
        raise ValueError(f"转债列表仅返回 {len(rows)} 条（≤30），可能未登录或会话已失效")
    logger.info("cb_list 返回 %d 条", len(rows))
    return rows


def fetch_redeem_list(session: requests.Session) -> List[Dict[str, Any]]:
    params = {"___jsl": f"LST___t={int(time.time() * 1000)}"}
    resp = session.post(
        CB_REDEEM_LIST_URL, headers=CB_HEADERS, params=params, data={"rp": 50, "page": 1}, timeout=15
    )
    resp.raise_for_status()
    rows = resp.json().get("rows", [])
    logger.info("redeem_list 返回 %d 条", len(rows))
    return rows


def load_snapshot(
    config: Dict[str, Any], cookie: str, session: requests.Session
) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, Any]], str]:
    """返回 (all_bonds_rows, redeem_map, as_of_date)。redeem_map: bond_id -> cell。"""
    all_bonds = fetch_cb_list(session)
    redeem_rows = fetch_redeem_list(session)
    redeem_map: Dict[str, Dict[str, Any]] = {}
    for r in redeem_rows:
        if not isinstance(r, dict):
            continue
        cell = r.get("cell", {}) or {}
        bid = cell.get("bond_id")
        if bid:
            redeem_map[bid] = cell
    as_of_date = now_in_beijing().strftime("%Y-%m-%d")
    return all_bonds, redeem_map, as_of_date


# ── 过滤 + 选债（移植自 v2 jisilu_service.py）─────────────────────────────────
def _cell_of(row: Any) -> Dict[str, Any]:
    if isinstance(row, dict):
        c = row.get("cell")
        if isinstance(c, dict):
            return c
        return row
    return {}


def get_cell_float(row: Any, field: str) -> Optional[float]:
    value = _cell_of(row).get(field)
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def check_exclusion_rules(cell: Dict[str, Any], rules: List[Dict[str, Any]]) -> List[str]:
    """数值阈值排除，返回命中原因。取不到值时不排除（宁可放行）。"""
    reasons: List[str] = []
    for rule in rules or []:
        if not rule.get("enabled", True):
            continue
        raw = cell.get(rule["field"])
        if raw is None or raw == "":
            continue
        try:
            val = float(raw)
        except (TypeError, ValueError):
            continue
        try:
            threshold = float(rule["threshold"])
        except (TypeError, ValueError):
            continue
        op = rule.get("op")
        if op == "lt" and val < threshold:
            reasons.append(rule.get("label", rule["field"]))
        elif op == "gt" and val > threshold:
            reasons.append(rule.get("label", rule["field"]))
    return reasons


def get_cb_filter_reasons(cell: Dict[str, Any], excluded_redeem_icons: List[str]) -> List[str]:
    reasons: List[str] = []
    icons = cell.get("icons", {}) or {}
    label_map = {"R": "已公告强赎", "O": "公告要强赎", "B": "已满足强赎条件", "G": "公告不强赎"}
    for icon in excluded_redeem_icons or []:
        if icon in icons:
            reasons.append(label_map.get(icon, icon))
    if "ST" in str(cell.get("stock_nm", "")).upper():
        reasons.append("正股含ST或*ST")
    return reasons


def _get_listed_days(list_dt_str: Any) -> Optional[int]:
    try:
        listed_date = datetime.strptime(str(list_dt_str), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None
    return (now_in_beijing().date() - listed_date).days


def filter_cb(
    rows: List[Dict[str, Any]], config: Dict[str, Any], remain_days_map: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """排除 ST、强赎风险、数值阈值不达标、临近强赎触发、上市未满期的转债。"""
    s = config["strategy"]
    excluded_icons = s.get("excluded_redeem_icons", [])
    rules = s.get("exclusion_rules", [])
    safe_days = int(s.get("redeem_safe_days", 2))
    min_days = max(0, int(s.get("min_listing_days", 0) or 0))
    excluded_code_set = build_bond_code_match_set(s.get("excluded_bond_codes", []))
    result: List[Dict[str, Any]] = []
    for row in rows:
        c = _cell_of(row)
        reasons = get_cb_filter_reasons(c, excluded_icons)
        reasons += check_exclusion_rules(c, rules)
        bond_id = c.get("bond_id")
        if excluded_code_set:
            if build_bond_code_match_set([bond_id]) & excluded_code_set:
                reasons.append("命中全局排除代码")
        if safe_days >= 0:
            remain = remain_days_map.get(bond_id)
            try:
                remain_i = int(remain) if remain is not None else None
            except (TypeError, ValueError):
                remain_i = None
            if remain_i is not None and 0 <= remain_i <= safe_days:
                reasons.append(f"临近强赎触发(还需{remain_i}天)")
        if min_days > 0:
            listed_days = _get_listed_days(c.get("list_dt"))
            if listed_days is not None and listed_days < min_days:
                reasons.append(f"上市未满{min_days}天(仅{listed_days}天)")
        if reasons:
            continue
        result.append(row)
    return result


def assign_factor_scores(rows: List[Dict[str, Any]], field: str, ascending: bool, weight: float) -> None:
    """按 field 排名写入 {field}_score（值越小排名越靠前时 ascending=True）。"""
    valid = [(i, row, get_cell_float(row, field)) for i, row in enumerate(rows)
             if get_cell_float(row, field) is not None]
    valid.sort(key=lambda x: (x[2] if ascending else -x[2], x[0]))
    total = len(valid)
    score_key = f"{field}_score"
    for rank, (_, row, _) in enumerate(valid, 1):
        row[score_key] = (total - rank + 1) * weight
    scored_ids = {id(row) for _, row, _ in valid}
    for row in rows:
        if id(row) not in scored_ids:
            row[score_key] = 0


def three_low_strategy(rows: List[Dict[str, Any]], factors: List[Dict[str, Any]], top_n: int) -> List[Dict[str, Any]]:
    """各因子打分求和，降序排列，同分按双低值升序，返回前 top_n。"""
    ranked = list(rows)
    active = [f for f in factors if f.get("enabled", True)]
    for f in active:
        assign_factor_scores(ranked, field=f["field"], ascending=f.get("ascending", True), weight=f.get("weight", 1.0))
    for row in ranked:
        row["total_score"] = sum(row.get(f"{f['field']}_score", 0) for f in active)
    ranked.sort(key=lambda r: (-r["total_score"], to_float(_cell_of(r).get("dblow"), float("inf"))))
    return ranked[:top_n]


def select_keep_pool(
    rows: List[Dict[str, Any]], config: Dict[str, Any], remain_days_map: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """过滤 -> 打分 -> 返回 keep_pool（target+tol），每行带 total_score 与 rank（1=第一）。"""
    s = config["strategy"]
    target = int(s["target_count"])
    tol = max(0, int(s.get("hold_tolerance", 0)))
    pool_size = target + tol
    filtered = filter_cb(rows, config, remain_days_map)
    logger.info("过滤后剩 %d 条（共 %d）", len(filtered), len(rows))
    keep_pool = three_low_strategy(filtered, s.get("factors", []), pool_size)
    for i, row in enumerate(keep_pool, 1):
        row["rank"] = i
    return keep_pool


# ── 净值/持仓（新）────────────────────────────────────────────────────────────
def bond_code(row: Any) -> str:
    return str(_cell_of(row).get("bond_id", "")).strip()


def bond_field(row: Any, field: str, default: Any = None) -> Any:
    return _cell_of(row).get(field, default)


def holdings_from_keep_pool(
    keep_pool: List[Dict[str, Any]],
    target_count: int,
    today_close_map: Dict[str, Optional[float]],
    prev_holdings: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """apply_tolerance：已持有且仍在 keep_pool 内的保留，空缺按 rank 补到 target_count。

    返回 [{code, name, price, rank}, ...]（按 keep_pool rank 排序），price 为今日收盘价。
    """
    pool_codes = {bond_code(r): r for r in keep_pool}
    retained: List[str] = []
    for h in (prev_holdings or []):
        if h["code"] in pool_codes:
            retained.append(h["code"])
    new_codes: List[str] = []
    for r in keep_pool:
        code = bond_code(r)
        if code in retained:
            continue
        new_codes.append(code)
        if len(retained) + len(new_codes) >= target_count:
            break
    selected = (retained + new_codes)[:target_count]
    selected_set = set(selected)
    out: List[Dict[str, Any]] = []
    for r in keep_pool:
        code = bond_code(r)
        if code not in selected_set:
            continue
        out.append({
            "code": code,
            "name": str(bond_field(r, "bond_nm", code)),
            "price": today_close_map.get(code),
            "rank": r.get("rank"),
        })
    return out


def compute_portfolio_return(
    prev_holdings: List[Dict[str, Any]], today_close_map: Dict[str, Optional[float]]
) -> Tuple[float, List[str]]:
    """等权日收益 = mean(today_close/prev_price - 1)。缺今日价按 0 收益兜底。

    返回 (portfolio_return, missing_codes)。
    """
    if not prev_holdings:
        return 0.0, []
    rets: List[float] = []
    missing: List[str] = []
    for h in prev_holdings:
        prev_price = to_float(h.get("price"))
        today_price = to_float(today_close_map.get(h["code"]))
        if prev_price is None or prev_price <= 0 or today_price is None:
            rets.append(0.0)
            if today_price is None:
                missing.append(h["code"])
            continue
        rets.append(today_price / prev_price - 1.0)
    return sum(rets) / len(rets), missing


def compute_snapshot_signature(keep_pool: List[Dict[str, Any]]) -> str:
    """用 keep_pool 的 (code, price) 生成签名，检测是否有新交易日。

    cb_list 快照无日期：节假日数据不变 -> 签名一致 -> 跳过；交易日价格变动 -> 签名不同 -> 推进。
    """
    parts = [f"{bond_code(r)}:{bond_field(r, 'price')}" for r in keep_pool]
    return hashlib.md5("|".join(parts).encode("utf-8")).hexdigest()


def selection_snapshot(
    keep_pool: List[Dict[str, Any]], config: Dict[str, Any], holdings: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """keep_pool 排名快照，用于邮件排名表；标记选中的 target_count 只。"""
    held_codes = {h["code"] for h in holdings}
    factors = [f for f in config["strategy"].get("factors", []) if f.get("enabled", True)]
    out: List[Dict[str, Any]] = []
    for r in keep_pool:
        code = bond_code(r)
        item: Dict[str, Any] = {
            "code": code,
            "name": str(bond_field(r, "bond_nm", code)),
            "price": to_float(bond_field(r, "price")),
            "rank": r.get("rank"),
            "total_score": round(to_float(r.get("total_score"), 0.0) or 0.0, 2),
            "selected": code in held_codes,
        }
        for f in factors:
            item[f["field"]] = to_float(bond_field(r, f["field"]))
        out.append(item)
    return out


# ── 状态持久化 ────────────────────────────────────────────────────────────────
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
    as_of_date: str,
    entries: List[Dict[str, Any]],
    nav: float,
    signature: str,
) -> Dict[str, Any]:
    s = config["strategy"]
    return {
        "strategy": "cb_three_low",
        "last_run_date": as_of_date,
        "portfolio_nav": round(nav, 6),
        "initial_nav": float(s["initial_nav"]),
        "target_count": int(s["target_count"]),
        "hold_tolerance": int(s.get("hold_tolerance", 0)),
        "last_snapshot_signature": signature,
        "updated_at": now_in_beijing().strftime("%Y-%m-%d %H:%M:%S"),
        "holdings_history": entries,
    }


# ── 编排 ──────────────────────────────────────────────────────────────────────
def run_strategy(
    config_path: str = DEFAULT_CONFIG_PATH,
    state_path: Optional[str] = None,
    cookie: Optional[str] = None,
    session: Optional[requests.Session] = None,
) -> Optional[Dict[str, Any]]:
    config = load_strategy_config(config_path)
    state_path = state_path or config["state_path"]
    s = config["strategy"]
    target = int(s["target_count"])
    initial_nav = float(s["initial_nav"])

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
        all_bonds, redeem_map, as_of_date = load_snapshot(config, cookie, session)
        remain_days_map = {bid: c.get("redeem_remain_days") for bid, c in redeem_map.items()}
        keep_pool = select_keep_pool(all_bonds, config, remain_days_map)
    finally:
        if own_session:
            session.close()

    if not keep_pool:
        logger.warning("keep_pool 为空，退出")
        return None

    today_close_map = {bond_code(r): to_float(bond_field(r, "price")) for r in all_bonds}
    signature = compute_snapshot_signature(keep_pool)

    state = load_state(state_path)
    if state is not None and state.get("last_snapshot_signature") == signature:
        logger.info("无新交易日（快照签名与上次一致），跳过")
        return state

    if state is not None and state.get("holdings_history"):
        history = state["holdings_history"]
        if history[-1].get("date") == as_of_date:
            # 同日重跑（如盘中手动触发后，收盘定时再跑）：丢弃当日记录，
            # 基于前一交易日用最新（收盘）快照重算，保证每个交易日只有一条记录。
            logger.info("当日（%s）已有记录，用最新快照覆盖重算", as_of_date)
            history.pop()

    if state is None or not state.get("holdings_history"):
        # 首次运行（或当日记录被覆盖后无更早历史）：无 prev，种子持仓 = top target_count，净值 = initial_nav
        holdings = holdings_from_keep_pool(keep_pool, target, today_close_map, prev_holdings=None)
        nav = initial_nav
        entry = {
            "date": as_of_date,
            "holdings": holdings,
            "nav": round(nav, 6),
            "prev_nav": round(nav, 6),
            "daily_return": 0.0,
            "selection": selection_snapshot(keep_pool, config, holdings),
        }
        state = fresh_state(config, as_of_date, [entry], nav, signature)
        logger.info("首次运行：持仓 %d 只，净值 %.4f", len(holdings), nav)
    else:
        prev_entry = state["holdings_history"][-1]
        prev_holdings = prev_entry["holdings"]
        daily_return, missing = compute_portfolio_return(prev_holdings, today_close_map)
        if missing:
            logger.warning("持仓缺今日收盘价（按 0 收益兜底）：%s", ", ".join(missing))
        prev_nav = float(prev_entry["nav"])
        nav = prev_nav * (1.0 + daily_return)
        holdings = holdings_from_keep_pool(keep_pool, target, today_close_map, prev_holdings=prev_holdings)
        entry = {
            "date": as_of_date,
            "holdings": holdings,
            "nav": round(nav, 6),
            "prev_nav": round(prev_nav, 6),
            "daily_return": round(daily_return, 6),
            "selection": selection_snapshot(keep_pool, config, holdings),
        }
        state["holdings_history"].append(entry)
        state["last_run_date"] = as_of_date
        state["portfolio_nav"] = round(nav, 6)
        state["last_snapshot_signature"] = signature
        state["updated_at"] = now_in_beijing().strftime("%Y-%m-%d %H:%M:%S")
        logger.info("新增交易日 %s：净值 %.4f，日收益 %.4f%%，持仓 %d 只", as_of_date, nav, daily_return * 100, len(holdings))

    save_state(state_path, state)
    return state


# ── 报告 ──────────────────────────────────────────────────────────────────────
def compute_drawdown_stats(history: List[Dict[str, Any]], initial_nav: float) -> Dict[str, float]:
    """从持仓历史计算累计收益、最大回撤、当前回撤（基于组合净值序列）。"""
    navs = [float(initial_nav)] + [float(e["nav"]) for e in history if e.get("nav") is not None]
    if not navs:
        return {"total_return": 0.0, "max_drawdown": 0.0, "current_drawdown": 0.0}
    peak = navs[0]
    max_dd = 0.0
    for value in navs:
        if value > peak:
            peak = value
        if peak > 0:
            dd = value / peak - 1.0
            if dd < max_dd:
                max_dd = dd
    current = navs[-1]
    peak_all = max(navs)
    total_return = current / float(initial_nav) - 1.0 if initial_nav else 0.0
    current_dd = current / peak_all - 1.0 if peak_all > 0 else 0.0
    return {"total_return": total_return, "max_drawdown": max_dd, "current_drawdown": current_dd}


def find_max_drawdown_window(
    history: List[Dict[str, Any]], initial_nav: float
) -> Optional[Dict[str, Any]]:
    """返回最大回撤区间：peak_date（前高日）、trough_date（最深日）、max_drawdown。

    起点（initial_nav）参与计算：若最高点恰为起点，peak_date 为 None。
    无回撤（净值单调创新高或为空）时返回 None。
    """
    navs = [float(initial_nav)] + [float(e["nav"]) for e in history if e.get("nav") is not None]
    dates = [None] + [str(e.get("date", "")) for e in history if e.get("nav") is not None]
    if len(navs) < 2:
        return None
    peak = navs[0]
    peak_date = dates[0]
    max_dd = 0.0
    dd_peak_date: Optional[str] = None
    dd_trough_date: Optional[str] = None
    for value, date in zip(navs, dates):
        if value > peak:
            peak = value
            peak_date = date
        if peak > 0:
            dd = value / peak - 1.0
            if dd < max_dd:
                max_dd = dd
                dd_peak_date = peak_date
                dd_trough_date = date
    if dd_trough_date is None:
        return None
    return {
        "peak_date": dd_peak_date,
        "trough_date": dd_trough_date,
        "max_drawdown": max_dd,
    }


def align_benchmark(
    history: List[Dict[str, Any]], benchmark_series: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """按日期对齐策略净值与基准（集思录等权指数），从首个共同日期起各自归一。

    benchmark_series: [{"date": "YYYY-MM-DD", "value": 指数值}, ...]
    返回 [{"date", "strategy_return", "benchmark_return"}]，首个共同日期两者均为 0。
    """
    bench_map = {}
    for record in benchmark_series or []:
        date = str(record.get("date", ""))[:10]
        value = record.get("value")
        if date and value not in (None, ""):
            try:
                bench_map[date] = float(value)
            except (TypeError, ValueError):
                continue
    aligned: List[Dict[str, Any]] = []
    base_nav: Optional[float] = None
    base_bench: Optional[float] = None
    for entry in history:
        date = str(entry.get("date", ""))[:10]
        nav = entry.get("nav")
        bench = bench_map.get(date)
        if nav is None or bench is None:
            continue
        nav = float(nav)
        if base_nav is None:
            base_nav, base_bench = nav, bench
        aligned.append(
            {
                "date": date,
                "strategy_return": nav / base_nav - 1.0 if base_nav else 0.0,
                "benchmark_return": bench / base_bench - 1.0 if base_bench else 0.0,
            }
        )
    return aligned


def compute_benchmark_comparison(
    history: List[Dict[str, Any]], benchmark_series: List[Dict[str, Any]]
) -> Dict[str, Optional[float]]:
    """基于对齐序列给出基准同期收益与超额收益（相对首个共同日期）。"""
    aligned = align_benchmark(history, benchmark_series)
    if not aligned:
        return {"benchmark_return": None, "excess_return": None}
    last = aligned[-1]
    return {
        "benchmark_return": last["benchmark_return"],
        "excess_return": last["strategy_return"] - last["benchmark_return"],
    }


def build_report(state: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    s = config["strategy"]
    target = int(s["target_count"])
    history = state.get("holdings_history", [])
    latest = history[-1] if history else {}
    holdings = latest.get("holdings", [])
    selection = latest.get("selection", [])
    stats = compute_drawdown_stats(history, float(s["initial_nav"]))
    return {
        "as_of_date": latest.get("date"),
        "holdings": holdings,
        "current_nav": latest.get("nav"),
        "portfolio_nav": state.get("portfolio_nav"),
        "total_return": stats["total_return"],
        "max_drawdown": stats["max_drawdown"],
        "current_drawdown": stats["current_drawdown"],
        "ranking": selection,
        "target_count": target,
        "history": history,
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
