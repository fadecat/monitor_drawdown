# ETF Rotation V4 Generalization Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a read-only validation layer that checks V2 / V3 / V4-A / V4-B stability across time segments without changing strategy rules.

**Architecture:** Add one standalone analyzer that reads existing `daily_positions.csv` files, computes normalized segment metrics, writes CSV/Markdown artifacts, and documents that this is temporal robustness testing rather than a true blind holdout. Keep the analyzer independent from strategy and backtest code.

**Tech Stack:** Python standard library, CSV artifacts, pytest.

---

### Task 1: Add Segment Metric Tests

**Files:**
- Create: `tests/test_analyze_etf_rotation_generalization.py`

- [ ] Write tests for segment normalization, max drawdown, defense-day counts, and summary generation.
- [ ] Run: `python -m pytest tests/test_analyze_etf_rotation_generalization.py -q`
- [ ] Expected first result: fails because `analyze_etf_rotation_generalization` does not exist.

### Task 2: Implement Read-Only Analyzer

**Files:**
- Create: `analyze_etf_rotation_generalization.py`

- [ ] Implement CSV loading.
- [ ] Implement `build_segment_summary(rows, start_date, end_date, defensive_symbol)`.
- [ ] Implement `run()` that compares:
  - V2: `.test_artifacts/etf_rotation_v2_backtest/daily_positions.csv`
  - V3: `.test_artifacts/etf_rotation_v3_backtest/daily_positions.csv`
  - V4-A: `.test_artifacts/etf_rotation_v4_backtest/daily_positions.csv`
  - V4-B: `.test_artifacts/etf_rotation_v4_backtest_v4b/daily_positions.csv`
- [ ] Use fixed segments:
  - `2014-01-01` to `2018-12-31`
  - `2019-01-01` to `2022-12-31`
  - `2023-01-01` to `2026-06-05`
  - `2025-01-01` to `2026-06-05`
- [ ] Write:
  - `.test_artifacts/etf_rotation_generalization/segment_summary.csv`
  - `.test_artifacts/etf_rotation_generalization/generalization_summary.md`

### Task 3: Add Chinese Review Document

**Files:**
- Create: `docs/etf_rotation_v4_generalization_validation.md`

- [ ] Explain that this is not a strict blind test because V4 has already been inspected on 2025 data.
- [ ] Summarize whether V4-B stability is enough to justify V4.1 research.
- [ ] State the next rule: no parameter tuning before future-data observation or broader asset-pool validation.

### Task 4: Verify

**Files:**
- Existing tests and generated artifacts.

- [ ] Run: `python -m pytest tests/test_analyze_etf_rotation_generalization.py tests/test_etf_rotation_v4_strategy.py tests/test_run_etf_rotation_v4_strategy.py tests/test_backtest_etf_rotation_v4_strategy.py -q`
- [ ] Run: `python analyze_etf_rotation_generalization.py`
- [ ] Confirm generated CSV and Markdown exist.

