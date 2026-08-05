"""etf_rotation_20d 核心逻辑单元测试（无网络）。"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

import etf_rotation_20d as strat


UNIVERSE = ["A", "B"]
FALLBACK = "C"
LOOKBACK = 2


def _frame(prices: dict[str, list[float]], dates: list[str] | None = None) -> pd.DataFrame:
    n = len(next(iter(prices.values())))
    dates = dates or [f"2026-01-{i:02d}" for i in range(1, n + 1)]
    series = {code: {dates[i]: v for i, v in enumerate(vals)} for code, vals in prices.items()}
    return strat.build_aligned_frame(series)


# ----------------------------- 对齐与前填充 ------------------------------- #
def test_build_aligned_frame_unions_dates_and_forward_fills():
    frame = _frame({"A": [1.0, 2.0, 3.0], "B": [1.0, 1.0, 1.0]}, ["d1", "d2", "d3"])
    assert list(frame.index) == ["d1", "d2", "d3"]
    assert frame.loc["d3", "A"] == 3.0


def test_build_aligned_frame_forward_fills_missing_dates():
    # A 缺 d2，应前填充为 d1 的值
    frame = strat.build_aligned_frame(
        {"A": {"d1": 1.0, "d3": 3.0}, "B": {"d1": 1.0, "d2": 2.0, "d3": 3.0}}
    )
    assert frame.loc["d2", "A"] == 1.0  # 前填充
    assert frame.loc["d3", "A"] == 3.0


# ----------------------------- 20 日涨幅 ---------------------------------- #
def test_compute_returns_at_uses_lookback_base():
    frame = _frame({"A": [1.0, 1.0, 1.0, 2.0]})  # lookback=2 -> base=idx0
    ret = strat.compute_returns_at(frame, 3, ["A"], LOOKBACK)
    assert ret["A"] == pytest.approx(2.0 / 1.0 - 1.0)


def test_compute_returns_at_insufficient_history_returns_empty():
    frame = _frame({"A": [1.0, 1.0, 1.0]})
    assert strat.compute_returns_at(frame, 1, ["A"], LOOKBACK) == {}


def test_compute_returns_at_ignores_non_universe_codes():
    frame = _frame({"A": [1.0, 1.0, 1.0, 2.0], "B": [1.0, 1.0, 1.0, 5.0]})
    ret = strat.compute_returns_at(frame, 3, ["A"], LOOKBACK)
    assert "A" in ret and "B" not in ret


# ----------------------------- 选股 --------------------------------------- #
def test_select_holding_picks_max_positive():
    assert strat.select_holding({"A": 0.05, "B": 0.10}, FALLBACK) == "B"


def test_select_holding_fallback_when_all_nonpositive():
    assert strat.select_holding({"A": -0.01, "B": 0.0}, FALLBACK) == FALLBACK


def test_select_holding_fallback_when_empty():
    assert strat.select_holding({}, FALLBACK) == FALLBACK


# ----------------------------- 日收益 ------------------------------------- #
def test_daily_return_at():
    frame = _frame({"A": [1.0, 1.0, 1.0, 2.0]})
    assert strat.daily_return_at(frame, "A", 3) == pytest.approx(1.0)
    assert strat.daily_return_at(frame, "A", 0) == 0.0


def test_daily_return_at_missing_code_returns_zero():
    frame = _frame({"A": [1.0, 2.0]})
    assert strat.daily_return_at(frame, "Z", 1) == 0.0


# ----------------------------- 回放：无未来函数 --------------------------- #
def test_replay_holding_decided_by_prior_day_signal():
    """当日持仓由前一日信号决定；改当日价不影响当日持仓，只影响当日净值。"""
    base = _frame({"A": [1, 1, 1, 2, 3], "B": [1, 1, 1, 1, 1], "C": [1, 1, 1, 1, 1]})
    alt = _frame({"A": [1, 1, 1, 2, 10], "B": [1, 1, 1, 1, 1], "C": [1, 1, 1, 1, 1]})

    entries_base, nav_base, _ = strat.replay_forward(
        base, base, UNIVERSE, FALLBACK, LOOKBACK, LOOKBACK, 1.0
    )
    entries_alt, nav_alt, _ = strat.replay_forward(
        alt, alt, UNIVERSE, FALLBACK, LOOKBACK, LOOKBACK, 1.0
    )

    # d4（最后一日）持仓由 d3 信号决定，两场景相同
    assert entries_base[-1]["holding"] == entries_alt[-1]["holding"] == "A"
    # 但 d4 净值不同（当日价不同）
    assert entries_base[-1]["nav"] != entries_alt[-1]["nav"]


def test_replay_nav_compounding_and_fallback_selection():
    frame = _frame({"A": [1, 1, 1, 2, 3], "B": [1, 1, 1, 1, 1], "C": [1, 1, 1, 1, 1]})
    entries, nav, next_holding = strat.replay_forward(
        frame, frame, UNIVERSE, FALLBACK, LOOKBACK, LOOKBACK, 1.0
    )
    # d2 信号全 <=0 -> d3 持有空仓 C
    assert entries[0]["date"] == "2026-01-04"
    assert entries[0]["holding"] == "C"
    assert entries[0]["nav"] == pytest.approx(1.0)
    # d3 信号 A>0 -> d4 持有 A，收益 3/2-1=0.5 -> 净值 1.5
    assert entries[1]["holding"] == "A"
    assert entries[1]["daily_return"] == pytest.approx(0.5)
    assert entries[1]["nav"] == pytest.approx(1.5)
    assert nav == pytest.approx(1.5)
    # d4 信号 A=3/1-1=2>0 -> 次日持仓 A
    assert next_holding == "A"


def test_backfill_starts_after_lookback_and_raises_when_insufficient():
    frame = _frame({"A": [1, 1, 1, 2, 3], "B": [1, 1, 1, 1, 1], "C": [1, 1, 1, 1, 1]})
    entries, _, _ = strat.backfill(frame, frame, UNIVERSE, FALLBACK, LOOKBACK, 1.0)
    # 历史从 lookback+1（索引3，即 2026-01-04）开始
    assert entries[0]["date"] == "2026-01-04"

    short = _frame({"A": [1, 1], "B": [1, 1], "C": [1, 1]})
    with pytest.raises(RuntimeError):
        strat.backfill(short, short, UNIVERSE, FALLBACK, LOOKBACK, 1.0)


# ----------------------------- 回撤统计 ----------------------------------- #
def test_compute_drawdown_stats_basic():
    history = [{"nav": 1.05}, {"nav": 0.95}, {"nav": 1.02}]
    stats = strat.compute_drawdown_stats(history, initial_nav=1.0)
    # peak 1.05, trough 0.95 -> max_dd = 0.95/1.05 - 1
    assert stats["max_drawdown"] == pytest.approx(0.95 / 1.05 - 1.0)
    # current 1.02 vs all-time peak 1.05
    assert stats["current_drawdown"] == pytest.approx(1.02 / 1.05 - 1.0)
    # total return 1.02/1.0 - 1
    assert stats["total_return"] == pytest.approx(0.02)


def test_compute_drawdown_stats_empty_history():
    stats = strat.compute_drawdown_stats([], initial_nav=1.0)
    assert stats == {"total_return": 0.0, "max_drawdown": 0.0, "current_drawdown": 0.0}


# ----------------------------- 状态持久化 --------------------------------- #
def test_state_save_load_roundtrip(tmp_path: Path):
    state = {
        "strategy": "etf_rotation_20d",
        "last_run_date": "2026-01-04",
        "portfolio_nav": 1.5,
        "next_holding": "A",
        "holdings_history": [{"date": "2026-01-04", "holding": "A", "nav": 1.5}],
    }
    path = tmp_path / "state.json"
    strat.save_state(str(path), state)
    loaded = strat.load_state(str(path))
    assert loaded == state


def test_load_state_missing_returns_none(tmp_path: Path):
    assert strat.load_state(str(tmp_path / "nope.json")) is None


# ----------------------------- 配置 --------------------------------------- #
def test_load_strategy_config_reads_universe():
    config = strat.load_strategy_config("etf_rotation_20d_config.yaml")
    codes = [t["code"] for t in config["universe"]]
    assert codes == ["512040", "159967", "513090", "159934", "159941", "513880", "164824"]
    assert config["fallback_holding"]["code"] == "511880"
    assert config["strategy"]["lookback_days"] == 20


def test_code_name_map_includes_fallback():
    config = strat.load_strategy_config("etf_rotation_20d_config.yaml")
    names = strat.code_name_map(config)
    assert names["511880"] == "银华日利"
    assert names["159941"] == "纳指ETF广发"
