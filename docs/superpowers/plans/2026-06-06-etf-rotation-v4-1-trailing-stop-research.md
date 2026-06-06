# ETF Rotation V4.1 持仓峰值回撤止损研究计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不修改 V2 入场逻辑的前提下，只增加一个持仓峰值回撤止损，验证它是否能降低回撤并保住趋势收益。

**Architecture:** 以 V2 作为主基线，复用现有回测框架和 T+1 执行节奏，只在持仓管理阶段新增一个 trailing stop 状态机。止损基于持仓期间每日收盘价的最高点计算，触发后次日切换到 `511880`，并在每次换仓时重置峰值。研究阶段只测 `5% / 8% / 10%` 三档，不做网格搜索。

**Tech Stack:** Python 标准库、现有回测 CSV 产物、pytest。

---

### Task 1: 写峰值止损的失败测试

**Files:**
- Create: `tests/test_etf_rotation_v4_1_trailing_stop.py`

- [ ] **Step 1: Write the failing test**

```python
import etf_rotation_v4_1_strategy as module


def test_trailing_peak_resets_on_each_new_position():
    state = module.build_trailing_stop_state(entry_price=100.0)
    state = module.update_trailing_stop_state(state, close_price=130.0)
    state = module.build_trailing_stop_state(entry_price=80.0)
    assert state["trailing_peak"] == 80.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_etf_rotation_v4_1_trailing_stop.py -q`
Expected: FAIL because `etf_rotation_v4_1_strategy` does not exist yet.

### Task 2: 实现最小可用的 V4.1 策略模块

**Files:**
- Create: `etf_rotation_v4_1_strategy.py`

- [ ] **Step 1: Write minimal implementation**

```python
from __future__ import annotations


def build_trailing_stop_state(entry_price: float) -> dict[str, float | bool]:
    return {
        "entry_price": float(entry_price),
        "trailing_peak": float(entry_price),
        "stop_triggered": False,
    }


def update_trailing_stop_state(
    state: dict[str, float | bool],
    close_price: float,
    stop_loss_pct: float = 0.08,
) -> dict[str, float | bool]:
    trailing_peak = max(float(state["trailing_peak"]), float(close_price))
    drawdown = float(close_price) / trailing_peak - 1.0 if trailing_peak > 0 else 0.0
    updated = dict(state)
    updated["trailing_peak"] = trailing_peak
    updated["stop_triggered"] = drawdown <= -float(stop_loss_pct)
    return updated
```

- [ ] **Step 2: Run test to verify it passes**

Run: `python -m pytest tests/test_etf_rotation_v4_1_trailing_stop.py -q`
Expected: PASS.

### Task 3: 把止损接入回测层

**Files:**
- Create: `backtest_etf_rotation_v4_1_strategy.py`
- Modify: `backtest_etf_rotation_v2_strategy.py` 参考现有 T+1 处理方式

- [ ] **Step 1: Write the failing integration test**

```python
def test_replay_rotation_v4_1_switches_to_defense_after_trailing_stop():
    series_by_label = {
        "A": _make_series(
            "A",
            [100.0, 110.0, 120.0, 130.0, 120.0, 116.0, 115.0, 114.0],
        ),
        "银华日利ETF": _make_series("银华日利ETF", [100.0, 100.01, 100.02, 100.03, 100.04, 100.05, 100.06, 100.07]),
    }
    metadata_by_label = {
        "A": {"label": "A", "code": "510001", "kind": "etf", "name": "AETF"},
        "银华日利ETF": {
            "label": "银华日利ETF",
            "code": "511880",
            "kind": "etf",
            "name": "银华日利ETF",
        },
    }
    result = module.replay_rotation_strategy_v4_1(
        series_by_label=series_by_label,
        metadata_by_label=metadata_by_label,
        strategy_config={
            "lookback_days": 25,
            "short_lookback_days": 10,
            "annualization_days": 250,
            "weight_start": 1.0,
            "weight_end": 2.0,
            "holdings_num": 1,
            "stop_loss_pct": 0.10,
        },
        risk_labels={"A"},
        defensive_labels={"银华日利ETF"},
    )
    assert result["daily_positions"][0]["holding_symbol"] == "510001"
    assert any(
        row["holding_symbol"] == "511880" and row["signal_date"] == "2026-04-006"
        for row in result["daily_positions"]
    )
    assert result["holding_periods"][0]["symbol"] == "510001"
    assert result["holding_periods"][1]["symbol"] == "511880"
    assert result["trailing_stop_events"][0]["reason"] == "trailing_stop_triggered"


def test_replay_rotation_v4_1_resets_trailing_peak_on_new_position():
    result = module.replay_rotation_strategy_v4_1(
        ...
    )
    first_risk_period = next(period for period in result["holding_periods"] if period["symbol"] == "510001")
    second_risk_period = next(
        period for period in result["holding_periods"] if period["symbol"] == "510001" and period["start_date"] != first_risk_period["start_date"]
    )
    assert first_risk_period["entry_price"] == 100.0
    assert first_risk_period["trailing_peak"] == 130.0
    assert second_risk_period["entry_price"] == second_risk_period["trailing_peak"]


def test_replay_rotation_v4_1_trigger_day_skips_same_day_rerank_and_forces_defense_next_day():
    result = module.replay_rotation_strategy_v4_1(
        ...
    )
    triggered_event = next(event for event in result["trailing_stop_events"] if event["reason"] == "trailing_stop_triggered")
    assert triggered_event["signal_date"] == "2026-04-006"
    assert triggered_event["action"] == "force_defensive_next_day"
    assert result["daily_positions"][1]["holding_symbol"] == "511880"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_backtest_etf_rotation_v4_1_strategy.py -q`
Expected: FAIL because `replay_rotation_strategy_v4_1` does not exist yet.

- [ ] **Step 3: Write the minimal integration**

```python
def replay_rotation_strategy_v4_1(...):
    ...
```

要求：

- 触发条件只看持仓期收盘价峰值回撤
- T 日收盘发现触发，T+1 切防守
- 当日止损触发后，**不**在同一信号日继续做新的排名替换，先强制进入防守状态
- 每次换仓后 `trailing_peak` 重置为新入场收盘价
- 不改 `score_25`
- 不改 Top1
- 不改短期确认层

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_backtest_etf_rotation_v4_1_strategy.py -q`
Expected: PASS.

### Task 4: 跑三档参数的真实数据验证

**Files:**
- Create: `run_etf_rotation_v4_1_strategy.py`
- Create: `.test_artifacts/etf_rotation_v4_1_backtest/stop_loss_0.05/*`
- Create: `.test_artifacts/etf_rotation_v4_1_backtest/stop_loss_0.08/*`
- Create: `.test_artifacts/etf_rotation_v4_1_backtest/stop_loss_0.10/*`

- [ ] **Step 1: 固定三档参数**

```python
stop_loss_pcts = [0.05, 0.08, 0.10]
```

- [ ] **Step 2: 跑真实数据回测**

Run:

```bash
python run_etf_rotation_v4_1_strategy.py --stop-loss-pct 0.05 --output-root .test_artifacts/etf_rotation_v4_1_backtest/stop_loss_0.05
python run_etf_rotation_v4_1_strategy.py --stop-loss-pct 0.08 --output-root .test_artifacts/etf_rotation_v4_1_backtest/stop_loss_0.08
python run_etf_rotation_v4_1_strategy.py --stop-loss-pct 0.10 --output-root .test_artifacts/etf_rotation_v4_1_backtest/stop_loss_0.10
```

Expected: each run writes its own backtest summary and CSV outputs.

- [ ] **Step 3: 对比 V2**

检查：

- 最大回撤是否下降
- 年化收益是否明显受损
- 防守天数是否大幅增加
- 2025-2026 是否只是样本内适配

### Task 5: 写中文研究结论

**Files:**
- Create: `docs/etf_rotation_v4_1_trailing_stop_research.md`

- [ ] **Step 1: 写明结论边界**

必须明确：

- 这不是入场优化
- 这不是过滤层迭代
- 这是持仓中退出机制验证

- [ ] **Step 2: 写明是否值得进入下一轮**

如果三档里没有一个同时满足“回撤改善 + 收益不明显恶化”，则冻结为失败假设，不继续加冷却期或最低持仓期。

要求输出下面这张对比表：

| 指标 | V2 | V4.1-5% | V4.1-8% | V4.1-10% |
|---|---:|---:|---:|---:|
| 年化收益 | | | | |
| 最大回撤 | | | | |
| 防守天数 | | | | |
| 止损触发次数 | | | | |
| 2025 年收益 | | | | |

### Task 6: 验证与收口

**Files:**
- Existing tests and generated artifacts.

- [ ] **Step 1: 跑全量相关测试**

Run:

```bash
python -m pytest tests/test_etf_rotation_v4_1_trailing_stop.py tests/test_backtest_etf_rotation_v4_1_strategy.py -q
```

- [ ] **Step 2: 检查输出文件**

确认：

- `backtest_summary.md`
- `daily_positions.csv`
- `trades.csv`
- `holding_periods.csv`
- `docs/etf_rotation_v4_1_trailing_stop_research.md`
