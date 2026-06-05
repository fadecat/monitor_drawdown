# ETF Rotation V2 Stage 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an isolated V2 ETF rotation strategy that uses 25-day weighted trend scoring, 10-day confirmation, Top1 selection, and defensive fallback without modifying V1 behavior.

**Architecture:** Keep V1 intact and add a parallel V2 stack with its own config, strategy module, runner, backtest script, and tests. Reuse the existing ETF.com.cn series loading path from `inspect_etf_trend_sources.py`, but define new V2-specific metrics, execution timing rules, and output files.

**Tech Stack:** Python 3.10, pytest, PyYAML, existing local data loaders and JSON/CSV outputs.

---

### Task 1: Freeze Stage 1 Rules In Documentation

**Files:**
- Modify: `docs/etf_rotation_v2_stage1_decisions.md`

- [ ] **Step 1: Add explicit execution accounting rules**

Document these points in the decisions file:

```text
- signal_date means T-day close, used only for ranking and filtering
- position_date means the next global trading date in the union calendar
- daily_positions.csv uses position_date as date and keeps signal_date as a separate field
- a position chosen on signal_date earns return from signal_date close to position_date close
- this is a research accounting convention, not a strict tradable open-price model
```

- [ ] **Step 2: Add V2 output contract**

Document the required V2 outputs:

```text
Runner:
- candidate_metrics.json
- ranked_candidates.json
- portfolio_decision.json
- summary.md

Backtest:
- daily_candidate_metrics.csv
- daily_rankings.csv
- daily_positions.csv
- trades.csv
- holding_periods.csv
- yearly_returns.csv
- symbol_contributions.csv
- backtest_summary.md
```

- [ ] **Step 3: List mandatory metric fields**

Document that at minimum V2 outputs must expose:

```text
score_25
annualized_return_25
r_squared_25
return_10d
selection_reason
```

### Task 2: Add V2 Strategy Tests First

**Files:**
- Create: `tests/test_etf_rotation_v2_strategy.py`

- [ ] **Step 1: Write failing metric tests**

Add tests for:

```python
def test_calculate_weighted_trend_metrics_returns_positive_score_for_clean_uptrend():
    ...

def test_calculate_weighted_trend_metrics_clamps_negative_r_squared_to_zero():
    ...

def test_build_rotation_candidate_v2_requires_positive_score_25_and_return_10d():
    ...
```

- [ ] **Step 2: Run only the new V2 strategy tests**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; python -m pytest tests/test_etf_rotation_v2_strategy.py -q
```

Expected: fail because `etf_rotation_v2_strategy.py` does not exist yet.

- [ ] **Step 3: Implement minimal V2 strategy module**

Create `etf_rotation_v2_strategy.py` with:

```python
calculate_lookback_return(...)
calculate_weighted_trend_metrics(...)
build_rotation_candidate(...)
rank_candidates(...)
select_portfolio(...)
```

- [ ] **Step 4: Re-run the V2 strategy tests**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; python -m pytest tests/test_etf_rotation_v2_strategy.py -q
```

Expected: pass.

### Task 3: Add V2 Runner Tests First

**Files:**
- Create: `tests/test_run_etf_rotation_v2_strategy.py`
- Create: `etf_rotation_v2_config.yaml`
- Create: `run_etf_rotation_v2_strategy.py`

- [ ] **Step 1: Write failing runner tests**

Add tests for:

```python
def test_load_rotation_v2_config_reads_separate_risk_and_defensive_targets():
    ...

def test_run_rotation_v2_strategy_writes_candidate_metrics_rankings_and_decision():
    ...
```

- [ ] **Step 2: Run only the new V2 runner tests**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; python -m pytest tests/test_run_etf_rotation_v2_strategy.py -q
```

Expected: fail because V2 config and runner are missing.

- [ ] **Step 3: Implement minimal V2 config and runner**

Create:

```text
etf_rotation_v2_config.yaml
run_etf_rotation_v2_strategy.py
```

The runner must:
- load `targets` and `defensive_targets`
- fetch/load series through `inspect_etf_trend_sources`
- compute V2 candidate metrics for risk assets only
- append fallback defensive decision when no risk asset qualifies
- write the required runner outputs

- [ ] **Step 4: Re-run the V2 runner tests**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; python -m pytest tests/test_run_etf_rotation_v2_strategy.py -q
```

Expected: pass.

### Task 4: Add V2 Backtest Tests First

**Files:**
- Create: `tests/test_backtest_etf_rotation_v2_strategy.py`
- Create: `backtest_etf_rotation_v2_strategy.py`

- [ ] **Step 1: Write failing backtest tests**

Add tests for:

```python
def test_replay_rotation_v2_uses_t_plus_1_position_dates_and_defensive_fallback():
    ...

def test_replay_rotation_v2_writes_daily_candidate_metrics_and_rankings():
    ...

def test_run_backtest_v2_writes_required_stage1_outputs():
    ...
```

- [ ] **Step 2: Run only the new V2 backtest tests**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; python -m pytest tests/test_backtest_etf_rotation_v2_strategy.py -q
```

Expected: fail because V2 backtest module does not exist yet.

- [ ] **Step 3: Implement minimal V2 backtest**

Create `backtest_etf_rotation_v2_strategy.py` with:
- replay loop on union trading dates
- `signal_date` to `position_date` accounting
- daily candidate metrics output
- daily rankings output
- daily positions, trades, holding periods, yearly returns, symbol contributions

- [ ] **Step 4: Re-run the V2 backtest tests**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; python -m pytest tests/test_backtest_etf_rotation_v2_strategy.py -q
```

Expected: pass.

### Task 5: Full V2 Verification

**Files:**
- Modify: `docs/etf_rotation_v2_stage1_decisions.md`
- Create/Modify: `etf_rotation_v2_strategy.py`
- Create/Modify: `run_etf_rotation_v2_strategy.py`
- Create/Modify: `backtest_etf_rotation_v2_strategy.py`
- Create/Modify: `etf_rotation_v2_config.yaml`
- Create/Modify: `tests/test_etf_rotation_v2_strategy.py`
- Create/Modify: `tests/test_run_etf_rotation_v2_strategy.py`
- Create/Modify: `tests/test_backtest_etf_rotation_v2_strategy.py`

- [ ] **Step 1: Run the focused V2 suite**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; python -m pytest tests/test_etf_rotation_v2_strategy.py tests/test_run_etf_rotation_v2_strategy.py tests/test_backtest_etf_rotation_v2_strategy.py -q
```

Expected: all pass.

- [ ] **Step 2: Run the existing baseline suite to ensure no V1 regression**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; python -m pytest tests/test_etf_rotation_strategy.py tests/test_run_etf_rotation_strategy.py tests/test_backtest_etf_rotation_strategy.py tests/test_preview_etf_rotation_interactive.py -q
```

Expected: all pass.

- [ ] **Step 3: Review git diff and summarize**

Run:

```powershell
git status --short
```

Expected: only V2-specific files and the V2 decision doc changed.
