"""cb_three_low 核心逻辑单元测试（无网络）。"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest
import requests

import cb_three_low as strat


CONFIG_PATH = "cb_three_low_config.yaml"


def _row(bond_id, dblow, premium_rt, curr_iss_amt, price, **cell_extra):
    """构造一只干净的 cb_list row（默认通过所有过滤）。"""
    cell = {
        "bond_id": bond_id,
        "bond_nm": f"转债{bond_id}",
        "price": price,
        "dblow": dblow,
        "premium_rt": premium_rt,
        "curr_iss_amt": curr_iss_amt,
        "rating_cd": "AA",
        "year_left": 3,
        "pb": 2.0,
        "sprice": 10.0,
        "convert_value": 100.0,
        "convert_amt_ratio": 5,
        "list_dt": "2020-01-01",
        "stock_nm": "正股",
        "icons": {},
    }
    cell.update(cell_extra)
    return {"cell": cell}


# ── 代码归一化 ────────────────────────────────────────────────────────────────
def test_normalize_bond_code():
    assert strat.normalize_bond_code("113001") == "113001.SH"
    assert strat.normalize_bond_code("128001") == "128001.SZ"
    assert strat.normalize_bond_code("113001.SH") == "113001.SH"
    assert strat.normalize_bond_code(None) == ""


def test_build_bond_code_match_set_accepts_both_forms():
    s = strat.build_bond_code_match_set(["113001", "128001.SZ"])
    # 6 位输入 -> 同时含裸码与后缀码
    assert "113001" in s and "113001.SH" in s
    # 后缀输入 -> 含后缀码（匹配时由对端补裸码）
    assert "128001.SZ" in s


# ── 过滤 ──────────────────────────────────────────────────────────────────────
def _config():
    return strat.load_strategy_config(CONFIG_PATH)


def test_filter_cb_excludes_st():
    cfg = _config()
    rows = [_row("113001", 100, 5, 2, 100, stock_nm="*ST正股")]
    assert strat.filter_cb(rows, cfg, {}) == []


def test_filter_cb_excludes_redeem_icon():
    cfg = _config()
    rows = [_row("113001", 100, 5, 2, 100, icons={"R": "已公告强赎"})]
    assert strat.filter_cb(rows, cfg, {}) == []


def test_filter_cb_excludes_pb_below_one():
    cfg = _config()
    rows = [_row("113001", 100, 5, 2, 100, pb=0.8)]
    assert strat.filter_cb(rows, cfg, {}) == []


def test_filter_cb_excludes_high_convert_value():
    cfg = _config()
    rows = [_row("113001", 100, 5, 2, 100, convert_value=130)]
    assert strat.filter_cb(rows, cfg, {}) == []


def test_filter_cb_excludes_manual_exclude_list():
    cfg = _config()
    rows = [_row("118027", 100, 5, 2, 100)]  # 宏图转债 在排除清单
    assert strat.filter_cb(rows, cfg, {}) == []


def test_filter_cb_keeps_clean_bond():
    cfg = _config()
    rows = [_row("113001", 100, 5, 2, 100)]
    kept = strat.filter_cb(rows, cfg, {})
    assert len(kept) == 1


def test_filter_cb_excludes_near_redeem_trigger():
    cfg = _config()
    rows = [_row("113001", 100, 5, 2, 100)]
    # redeem_safe_days=2，剩余 1 天 -> 排除
    remain = {"113001": 1}
    assert strat.filter_cb(rows, cfg, remain) == []
    # 剩余 5 天（>2）-> 保留
    assert len(strat.filter_cb(rows, cfg, {"113001": 5})) == 1


def test_filter_cb_excludes_unlisted_min_days():
    cfg = _config()  # min_listing_days=3
    rows = [_row("113001", 100, 5, 2, 100, list_dt=strat.now_in_beijing().strftime("%Y-%m-%d"))]
    assert strat.filter_cb(rows, cfg, {}) == []


# ── 三低打分 ──────────────────────────────────────────────────────────────────
def test_three_low_ranking_by_total_score():
    factors = [
        {"field": "dblow", "ascending": True, "weight": 1.0},
        {"field": "premium_rt", "ascending": True, "weight": 1.0},
        {"field": "curr_iss_amt", "ascending": True, "weight": 1.0},
    ]
    rows = [
        _row("A", 100, 10, 5, 100),  # 双低最低
        _row("B", 120, 5, 1, 100),   # 溢价/规模最低
        _row("C", 110, 7, 3, 100),
    ]
    ranked = strat.three_low_strategy(rows, factors, top_n=3)
    # B 总分最高（溢价、规模均第1），其次 C，最后 A
    assert [strat.bond_code(r) for r in ranked] == ["B", "C", "A"]


def test_three_low_tiebreak_by_dblow_ascending():
    factors = [
        {"field": "dblow", "ascending": True, "weight": 1.0},
        {"field": "premium_rt", "ascending": True, "weight": 1.0},
    ]
    # 两只总分相同（各拿一个第1），双低低者排前
    rows = [_row("P", 100, 10, 2, 100), _row("Q", 110, 5, 2, 100)]
    ranked = strat.three_low_strategy(rows, factors, top_n=2)
    assert [strat.bond_code(r) for r in ranked] == ["P", "Q"]


def test_three_low_respects_top_n():
    factors = [{"field": "dblow", "ascending": True, "weight": 1.0}]
    rows = [_row(str(i), 100 + i, 5, 2, 100) for i in range(5)]
    ranked = strat.three_low_strategy(rows, factors, top_n=2)
    assert len(ranked) == 2
    assert strat.bond_code(ranked[0]) == "0"  # 双低最低


# ── 容差持仓 ──────────────────────────────────────────────────────────────────
def _pool(codes):
    """构造 keep_pool（已带 rank）。"""
    return [{"cell": {"bond_id": c, "bond_nm": f"转债{c}", "price": 100.0}, "rank": i + 1, "total_score": 0}
            for i, c in enumerate(codes)]


def test_holdings_first_run_takes_top_target():
    pool = _pool(["A", "B", "C", "D", "E"])
    closes = {c: 100.0 for c in "ABCDE"}
    holdings = strat.holdings_from_keep_pool(pool, target_count=3, today_close_map=closes)
    assert [h["code"] for h in holdings] == ["A", "B", "C"]


def test_holdings_tolerance_retains_existing_in_pool():
    # 已持有 D（rank4，在 keep_pool 内但非 top3），容差保留，不买 rank3 的 C
    pool = _pool(["A", "B", "C", "D", "E"])
    closes = {c: 100.0 for c in "ABCDE"}
    prev = [{"code": "D", "name": "转债D", "price": 100.0, "rank": 4}]
    holdings = strat.holdings_from_keep_pool(pool, target_count=3, today_close_map=closes, prev_holdings=prev)
    assert "D" in [h["code"] for h in holdings]
    assert [h["code"] for h in holdings] == ["A", "B", "D"]  # C 被挤掉


def test_holdings_drops_bond_outside_pool():
    # 已持有 Z 不在今日 keep_pool -> 卖出，补 rank3
    pool = _pool(["A", "B", "C", "D", "E"])
    closes = {c: 100.0 for c in "ABCDE"}
    prev = [{"code": "Z", "name": "转债Z", "price": 100.0, "rank": 1}]
    holdings = strat.holdings_from_keep_pool(pool, target_count=3, today_close_map=closes, prev_holdings=prev)
    assert [h["code"] for h in holdings] == ["A", "B", "C"]


# ── 组合收益 ──────────────────────────────────────────────────────────────────
def test_compute_portfolio_return_equal_weight_mean():
    prev = [
        {"code": "A", "price": 100.0},
        {"code": "B", "price": 100.0},
    ]
    closes = {"A": 102.0, "B": 101.0}  # +2%, +1% -> 均值 +1.5%
    ret, missing = strat.compute_portfolio_return(prev, closes)
    assert ret == pytest.approx(0.015)
    assert missing == []


def test_compute_portfolio_return_missing_price_zero_return():
    prev = [{"code": "A", "price": 100.0}, {"code": "B", "price": 100.0}]
    closes = {"A": 110.0}  # B 缺价 -> 0 收益兜底
    ret, missing = strat.compute_portfolio_return(prev, closes)
    assert ret == pytest.approx(0.05)  # (0.10 + 0.0) / 2
    assert missing == ["B"]


def test_compute_portfolio_return_empty_prev():
    assert strat.compute_portfolio_return([], {}) == (0.0, [])


# ── 回撤统计 ──────────────────────────────────────────────────────────────────
def test_compute_drawdown_stats_basic():
    history = [{"nav": 1.05}, {"nav": 0.95}, {"nav": 1.02}]
    stats = strat.compute_drawdown_stats(history, initial_nav=1.0)
    assert stats["max_drawdown"] == pytest.approx(0.95 / 1.05 - 1.0)
    assert stats["current_drawdown"] == pytest.approx(1.02 / 1.05 - 1.0)
    assert stats["total_return"] == pytest.approx(0.02)


def test_compute_drawdown_stats_empty():
    stats = strat.compute_drawdown_stats([], initial_nav=1.0)
    assert stats == {"total_return": 0.0, "max_drawdown": 0.0, "current_drawdown": 0.0}


# ── 最大回撤区间 ──────────────────────────────────────────────────────────────
def test_find_max_drawdown_window_basic():
    history = [
        {"date": "2026-01-05", "nav": 1.05},  # 前高
        {"date": "2026-01-06", "nav": 1.02},
        {"date": "2026-01-07", "nav": 0.98},  # 最深
        {"date": "2026-01-08", "nav": 1.01},
    ]
    window = strat.find_max_drawdown_window(history, initial_nav=1.0)
    assert window is not None
    assert window["peak_date"] == "2026-01-05"
    assert window["trough_date"] == "2026-01-07"
    assert window["max_drawdown"] == pytest.approx(0.98 / 1.05 - 1.0)


def test_find_max_drawdown_window_peak_at_start():
    # 起点即最高点：peak_date 为 None
    history = [{"date": "2026-01-05", "nav": 0.97}, {"date": "2026-01-06", "nav": 0.99}]
    window = strat.find_max_drawdown_window(history, initial_nav=1.0)
    assert window is not None
    assert window["peak_date"] is None
    assert window["trough_date"] == "2026-01-05"


def test_find_max_drawdown_window_none_when_monotonic_up():
    history = [{"date": "2026-01-05", "nav": 1.01}, {"date": "2026-01-06", "nav": 1.02}]
    assert strat.find_max_drawdown_window(history, initial_nav=1.0) is None
    assert strat.find_max_drawdown_window([], initial_nav=1.0) is None


# ── 基准对齐 ──────────────────────────────────────────────────────────────────
def test_align_benchmark_normalizes_from_first_common_date():
    history = [
        {"date": "2026-01-05", "nav": 1.00},
        {"date": "2026-01-06", "nav": 1.02},
        {"date": "2026-01-07", "nav": 1.01},
    ]
    bench = [
        {"date": "2026-01-02", "value": 2000.0},  # 策略尚未开始，忽略
        {"date": "2026-01-05", "value": 2100.0},
        {"date": "2026-01-06", "value": 2121.0},  # +1%
        {"date": "2026-01-07", "value": 2089.5},  # -0.5%
    ]
    aligned = strat.align_benchmark(history, bench)
    assert [a["date"] for a in aligned] == ["2026-01-05", "2026-01-06", "2026-01-07"]
    assert aligned[0]["strategy_return"] == pytest.approx(0.0)
    assert aligned[0]["benchmark_return"] == pytest.approx(0.0)
    assert aligned[1]["strategy_return"] == pytest.approx(0.02)
    assert aligned[1]["benchmark_return"] == pytest.approx(0.01)
    assert aligned[2]["benchmark_return"] == pytest.approx(-0.005)


def test_align_benchmark_skips_dates_missing_on_either_side():
    history = [
        {"date": "2026-01-05", "nav": 1.00},
        {"date": "2026-01-06", "nav": 1.02},  # 基准缺这天
        {"date": "2026-01-07", "nav": 1.01},
    ]
    bench = [{"date": "2026-01-05", "value": 100.0}, {"date": "2026-01-07", "value": 102.0}]
    aligned = strat.align_benchmark(history, bench)
    assert [a["date"] for a in aligned] == ["2026-01-05", "2026-01-07"]
    assert aligned[1]["benchmark_return"] == pytest.approx(0.02)


def test_compute_benchmark_comparison():
    history = [{"date": "2026-01-05", "nav": 1.00}, {"date": "2026-01-06", "nav": 1.03}]
    bench = [{"date": "2026-01-05", "value": 100.0}, {"date": "2026-01-06", "value": 101.0}]
    comp = strat.compute_benchmark_comparison(history, bench)
    assert comp["benchmark_return"] == pytest.approx(0.01)
    assert comp["excess_return"] == pytest.approx(0.02)
    # 无共同日期 -> None
    empty = strat.compute_benchmark_comparison(history, [{"date": "2025-01-01", "value": 1.0}])
    assert empty == {"benchmark_return": None, "excess_return": None}


# ── 图表冒烟 ──────────────────────────────────────────────────────────────────
def test_generate_nav_chart_with_benchmark_and_drawdown(tmp_path: Path):
    import cb_three_low_email_chart as chart_mod

    history = [
        {"date": f"2026-01-{d:02d}", "nav": nav}
        for d, nav in [(5, 1.00), (6, 1.03), (7, 0.97), (8, 1.01), (9, 1.04)]
    ]
    bench = [
        {"date": f"2026-01-{d:02d}", "value": v}
        for d, v in [(5, 100.0), (6, 101.0), (7, 99.0), (8, 100.5), (9, 101.5)]
    ]
    aligned = strat.align_benchmark(history, bench)
    drawdown = strat.find_max_drawdown_window(history, initial_nav=1.0)
    out = chart_mod.generate_nav_chart(
        history, tmp_path / "chart.png", benchmark=aligned, drawdown=drawdown
    )
    assert out.exists() and out.stat().st_size > 1000


def test_generate_nav_chart_strategy_only_still_works(tmp_path: Path):
    import cb_three_low_email_chart as chart_mod

    history = [{"date": "2026-01-05", "nav": 1.0}, {"date": "2026-01-06", "nav": 1.01}]
    out = chart_mod.generate_nav_chart(history, tmp_path / "chart2.png")
    assert out.exists() and out.stat().st_size > 1000


# ── 状态持久化 ────────────────────────────────────────────────────────────────
def test_state_save_load_roundtrip(tmp_path: Path):
    state = {
        "strategy": "cb_three_low",
        "last_run_date": "2026-01-04",
        "portfolio_nav": 1.5,
        "last_snapshot_signature": "abc",
        "holdings_history": [{"date": "2026-01-04", "nav": 1.5, "holdings": []}],
    }
    path = tmp_path / "state.json"
    strat.save_state(str(path), state)
    assert strat.load_state(str(path)) == state


def test_load_state_missing_returns_none(tmp_path: Path):
    assert strat.load_state(str(tmp_path / "nope.json")) is None


# ── 配置 ──────────────────────────────────────────────────────────────────────
def test_load_strategy_config_reads_params():
    cfg = strat.load_strategy_config(CONFIG_PATH)
    s = cfg["strategy"]
    assert s["target_count"] == 10
    assert s["hold_tolerance"] == 5
    assert len(s["factors"]) == 3
    assert [f["field"] for f in s["factors"]] == ["dblow", "premium_rt", "curr_iss_amt"]
    assert len(s["excluded_bond_codes"]) == 7
    assert cfg["state_path"] == "data_state/cb_three_low_state.json"


# ── 快照签名 ──────────────────────────────────────────────────────────────────
def test_snapshot_signature_stable_for_same_data():
    pool = _pool(["A", "B", "C"])
    assert strat.compute_snapshot_signature(pool) == strat.compute_snapshot_signature(pool)


def test_snapshot_signature_changes_with_price():
    pool1 = [{"cell": {"bond_id": "A", "price": 100.0}, "rank": 1, "total_score": 0}]
    pool2 = [{"cell": {"bond_id": "A", "price": 101.0}, "rank": 1, "total_score": 0}]
    assert strat.compute_snapshot_signature(pool1) != strat.compute_snapshot_signature(pool2)


# ── run_strategy：首次 + 二次 + 节假日跳过（mock 网络）──────────────────────
def _patch_fetch(monkeypatch, rows, redeem_rows=None):
    monkeypatch.setattr(strat, "fetch_cb_list", lambda session: list(rows))
    monkeypatch.setattr(strat, "fetch_redeem_list", lambda session: list(redeem_rows or []))


def _patch_today(monkeypatch, date_str):
    """固定“今天”，用于模拟跨交易日的多次运行。"""
    fake = dt.datetime.fromisoformat(date_str + "T15:30:00")
    monkeypatch.setattr(strat, "now_in_beijing", lambda: fake)


def test_run_strategy_first_run_seeds_top_holdings(monkeypatch, tmp_path: Path):
    rows = [_row(str(i), 100 + i, 5 + i, 2, 100.0) for i in range(12)]
    _patch_fetch(monkeypatch, rows)
    state_path = tmp_path / "state.json"
    state = strat.run_strategy(CONFIG_PATH, str(state_path), cookie="x", session=requests.Session())
    assert state is not None
    assert len(state["holdings_history"]) == 1
    assert len(state["holdings_history"][0]["holdings"]) == 10  # target_count
    assert state["portfolio_nav"] == pytest.approx(1.0)
    assert state["holdings_history"][0]["daily_return"] == 0.0


def test_run_strategy_second_run_updates_nav(monkeypatch, tmp_path: Path):
    # 首日：12 只，价格 100
    rows0 = [_row(str(i), 100 + i, 5 + i, 2, 100.0) for i in range(12)]
    state_path = tmp_path / "state.json"
    _patch_fetch(monkeypatch, rows0)
    _patch_today(monkeypatch, "2026-01-05")
    strat.run_strategy(CONFIG_PATH, str(state_path), cookie="x", session=requests.Session())

    # 次日：价格全部 +1%，签名变化 -> 推进
    rows1 = [_row(str(i), 100 + i, 5 + i, 2, 101.0) for i in range(12)]
    _patch_fetch(monkeypatch, rows1)
    _patch_today(monkeypatch, "2026-01-06")
    state = strat.run_strategy(CONFIG_PATH, str(state_path), cookie="x", session=requests.Session())
    assert len(state["holdings_history"]) == 2
    last = state["holdings_history"][-1]
    assert last["date"] == "2026-01-06"
    # 持仓 10 只各 +1% -> 日收益 1%
    assert last["daily_return"] == pytest.approx(0.01)
    assert last["nav"] == pytest.approx(1.01)


def test_run_strategy_same_day_rerun_overwrites(monkeypatch, tmp_path: Path):
    """盘中手动触发（盘中价）后，收盘定时跑必须用收盘价覆盖当日记录，而不是追加。"""
    state_path = tmp_path / "state.json"
    rows0 = [_row(str(i), 100 + i, 5 + i, 2, 100.0) for i in range(12)]
    _patch_fetch(monkeypatch, rows0)
    _patch_today(monkeypatch, "2026-01-05")
    strat.run_strategy(CONFIG_PATH, str(state_path), cookie="x", session=requests.Session())

    rows1 = [_row(str(i), 100 + i, 5 + i, 2, 101.0) for i in range(12)]
    _patch_fetch(monkeypatch, rows1)
    _patch_today(monkeypatch, "2026-01-06")
    strat.run_strategy(CONFIG_PATH, str(state_path), cookie="x", session=requests.Session())

    # 同日再跑（价格从 +1% 变成 +2%）-> 覆盖当日记录，历史长度不变
    rows2 = [_row(str(i), 100 + i, 5 + i, 2, 102.0) for i in range(12)]
    _patch_fetch(monkeypatch, rows2)
    state = strat.run_strategy(CONFIG_PATH, str(state_path), cookie="x", session=requests.Session())
    assert len(state["holdings_history"]) == 2
    last = state["holdings_history"][-1]
    assert last["date"] == "2026-01-06"
    assert last["daily_return"] == pytest.approx(0.02)
    assert last["nav"] == pytest.approx(1.02)


def test_run_strategy_same_day_rerun_on_first_day_reseeds(monkeypatch, tmp_path: Path):
    """首日盘中触发、收盘再跑：当日种子记录被覆盖重建，净值保持 initial_nav。"""
    state_path = tmp_path / "state.json"
    rows0 = [_row(str(i), 100 + i, 5 + i, 2, 100.0) for i in range(12)]
    _patch_fetch(monkeypatch, rows0)
    _patch_today(monkeypatch, "2026-01-05")
    strat.run_strategy(CONFIG_PATH, str(state_path), cookie="x", session=requests.Session())

    rows1 = [_row(str(i), 100 + i, 5 + i, 2, 101.0) for i in range(12)]
    _patch_fetch(monkeypatch, rows1)
    state = strat.run_strategy(CONFIG_PATH, str(state_path), cookie="x", session=requests.Session())
    assert len(state["holdings_history"]) == 1
    entry = state["holdings_history"][0]
    assert entry["date"] == "2026-01-05"
    assert entry["nav"] == pytest.approx(1.0)
    assert entry["daily_return"] == 0.0
    assert entry["holdings"][0]["price"] == pytest.approx(101.0)


def test_history_updated_detection():
    from send_cb_three_low_email import history_updated

    # 首次运行
    assert history_updated(None, {"holdings_history": [{}], "last_snapshot_signature": "a"}) is True
    # 签名一致（节假日/重复触发）-> 不更新
    assert history_updated(
        {"holdings_history": [{}], "last_snapshot_signature": "a"},
        {"holdings_history": [{}], "last_snapshot_signature": "a"},
    ) is False
    # 新交易日（历史变长）
    assert history_updated(
        {"holdings_history": [{}], "last_snapshot_signature": "a"},
        {"holdings_history": [{}, {}], "last_snapshot_signature": "a"},
    ) is True
    # 同日覆盖重算（长度不变，签名变化）
    assert history_updated(
        {"holdings_history": [{}], "last_snapshot_signature": "a"},
        {"holdings_history": [{}], "last_snapshot_signature": "b"},
    ) is True


def test_run_strategy_skips_when_signature_unchanged(monkeypatch, tmp_path: Path):
    rows = [_row(str(i), 100 + i, 5 + i, 2, 100.0) for i in range(12)]
    state_path = tmp_path / "state.json"
    _patch_fetch(monkeypatch, rows)
    strat.run_strategy(CONFIG_PATH, str(state_path), cookie="x", session=requests.Session())
    # 同样的数据再跑一次 -> 签名一致 -> 跳过
    state = strat.run_strategy(CONFIG_PATH, str(state_path), cookie="x", session=requests.Session())
    assert len(state["holdings_history"]) == 1


def test_build_report_shape(monkeypatch, tmp_path: Path):
    rows = [_row(str(i), 100 + i, 5 + i, 2, 100.0) for i in range(12)]
    _patch_fetch(monkeypatch, rows)
    state_path = tmp_path / "state.json"
    state = strat.run_strategy(CONFIG_PATH, str(state_path), cookie="x", session=requests.Session())
    cfg = strat.load_strategy_config(CONFIG_PATH)
    report = strat.build_report(state, cfg)
    assert report["as_of_date"] is not None
    assert len(report["holdings"]) == 10
    assert report["current_nav"] == pytest.approx(1.0)
    assert report["target_count"] == 10
    # ranking = keep_pool（target+tol=15，但只有 12 只）
    assert len(report["ranking"]) == 12
    assert report["ranking"][0]["selected"] is True
