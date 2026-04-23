# Valuation Percentile Chart Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the email's embedded equity-bond chart with a static valuation percentile chart that follows `VALUATION_PERCENTILE_CHART_SPEC.md`.

**Architecture:** Add a new chart module that reuses existing valuation fetch helpers from `monitor_drawdown.py`, renders a single 1400x780 PE percentile chart with matplotlib, and returns a PNG path keyed by `index_code`. Keep the old prototype untouched, update only the import/call sites that generate email charts, and preserve the existing email HTML embedding flow.

**Tech Stack:** Python 3.10, matplotlib, pandas, pytest

---

### Task 1: Add the failing chart-generation test

**Files:**
- Create: `tests/test_valuation_percentile_chart.py`
- Test: `tests/test_valuation_percentile_chart.py`

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path

import pandas as pd

import prototype_valuation_percentile_chart as chart


def test_generate_valuation_percentile_chart_outputs_png_with_missing_pb_and_dividend(monkeypatch, tmp_path: Path):
    def fake_fetch_index_pe_history(index_code: str, url: str = "") -> pd.DataFrame:
        dates = pd.date_range("2024-01-01", periods=30, freq="W")
        values = [10 + idx * 0.2 for idx in range(len(dates))]
        return pd.DataFrame({"date": dates, "pe": values})

    monkeypatch.setattr(chart.md, "fetch_index_pe_history", fake_fetch_index_pe_history)

    target = {
        "name": "测试指数",
        "code": "000300",
        "index_code": "000300",
        "index_name": "测试指数",
        "index_valuation_date": "2026-04-23",
        "index_valuation_metrics": {
            "PE(TTM)": {"current": 15.8, "percentiles": {"5Y": 18.5}},
        },
    }

    output = chart.generate_valuation_percentile_chart(target, tmp_path)

    assert output is not None
    assert output.exists()
    assert output.stat().st_size > 5 * 1024
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_valuation_percentile_chart.py -v`
Expected: FAIL because `prototype_valuation_percentile_chart` does not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
from pathlib import Path
from typing import Dict, Optional


def generate_valuation_percentile_chart(target: Dict, output_dir: Path) -> Optional[Path]:
    raise NotImplementedError
```

- [ ] **Step 4: Run test to verify it still fails for the right reason**

Run: `pytest tests/test_valuation_percentile_chart.py -v`
Expected: FAIL with `NotImplementedError`, proving the test exercises the new entrypoint.

- [ ] **Step 5: Commit**

```bash
git add tests/test_valuation_percentile_chart.py prototype_valuation_percentile_chart.py
git commit -m "test: add valuation percentile chart scaffold"
```

### Task 2: Implement the valuation percentile chart renderer

**Files:**
- Create: `prototype_valuation_percentile_chart.py`
- Test: `tests/test_valuation_percentile_chart.py`

- [ ] **Step 1: Extend the test for the desired behavior**

```python
def test_classify_level_by_percentile_uses_spec_thresholds():
    assert chart.classify_level_by_percentile(19.9) == ("估值极低", "#2f9e4f")
    assert chart.classify_level_by_percentile(20.0) == ("估值偏低", "#6fbf73")
    assert chart.classify_level_by_percentile(40.0) == ("估值合理", "#9aa0a6")
    assert chart.classify_level_by_percentile(60.0) == ("估值偏高", "#e89b3b")
    assert chart.classify_level_by_percentile(80.0) == ("估值极高", "#d94f3a")
```

- [ ] **Step 2: Run targeted tests to verify red**

Run: `pytest tests/test_valuation_percentile_chart.py -v`
Expected: FAIL because `classify_level_by_percentile` is missing.

- [ ] **Step 3: Implement the minimal chart module**

```python
def classify_level_by_percentile(pct: float) -> tuple[str, str]:
    if pct < 20:
        return "估值极低", "#2f9e4f"
    if pct < 40:
        return "估值偏低", "#6fbf73"
    if pct < 60:
        return "估值合理", "#9aa0a6"
    if pct < 80:
        return "估值偏高", "#e89b3b"
    return "估值极高", "#d94f3a"
```

- [ ] **Step 4: Finish the renderer and verify green**

Run: `pytest tests/test_valuation_percentile_chart.py -v`
Expected: PASS with PNG output assertion succeeding.

- [ ] **Step 5: Commit**

```bash
git add prototype_valuation_percentile_chart.py tests/test_valuation_percentile_chart.py
git commit -m "feat: add valuation percentile email chart"
```

### Task 3: Switch email chart generation to the new module

**Files:**
- Modify: `monitor_drawdown.py`
- Modify: `preview_email_with_charts.py`
- Test: `tests/test_valuation_percentile_chart.py`

- [ ] **Step 1: Add an integration-focused failing test**

```python
def test_generate_valuation_percentile_chart_uses_existing_metric_payload(monkeypatch, tmp_path: Path):
    calls = []

    def fake_fetch_target_index_metrics(target):
        calls.append(target["index_code"])
        return {
            "index_code": target["index_code"],
            "index_name": target["name"],
            "index_valuation_date": "2026-04-23",
            "index_valuation_metrics": {"PE(TTM)": {"current": 15.8, "percentiles": {"5Y": 18.5}}},
        }

    monkeypatch.setattr(chart.md, "fetch_target_index_metrics", fake_fetch_target_index_metrics)
```

- [ ] **Step 2: Run targeted tests to verify red**

Run: `pytest tests/test_valuation_percentile_chart.py -v`
Expected: FAIL if the generator does not yet fall back through the existing metric helpers.

- [ ] **Step 3: Update import and call sites**

```python
from prototype_valuation_percentile_chart import generate_valuation_percentile_chart

png_path = generate_valuation_percentile_chart(target, chart_output_dir)
```

- [ ] **Step 4: Re-run tests**

Run: `pytest tests/test_valuation_percentile_chart.py tests/test_monitor_drawdown.py -v`
Expected: PASS, with no regression in the existing monitor tests.

- [ ] **Step 5: Commit**

```bash
git add monitor_drawdown.py preview_email_with_charts.py tests/test_valuation_percentile_chart.py
git commit -m "refactor: switch email preview to valuation percentile chart"
```

### Task 4: Update docs and verify end-to-end preview

**Files:**
- Modify: `README.md`
- Modify: `VALUATION_PERCENTILE_CHART_SPEC.md`

- [ ] **Step 1: Add the README note**

```markdown
邮件中的估值图已由股债性价比图切换为估值分位走势图。
当前图面展示 PE 走势主图，以及 PB、PB百分位、股息率三项指标。
旧的 `prototype_equity_bond_chart.py` 仍保留，便于回滚或对照。
```

- [ ] **Step 2: Run the full automated test suite**

Run: `python -m pytest -q`
Expected: PASS with zero failing tests.

- [ ] **Step 3: Run the local preview script**

Run: `python preview_email_with_charts.py`
Expected: Exit 0 and generate `email_preview_with_charts.html` plus the new chart PNGs.

- [ ] **Step 4: Update spec progress with verification evidence**

```markdown
- 2026-04-23 HH:MM Codex：已完成测试、预览与 6 张估值分位图目检，本节记录命令与结果。
```

- [ ] **Step 5: Commit**

```bash
git add README.md VALUATION_PERCENTILE_CHART_SPEC.md docs/superpowers/plans/2026-04-23-valuation-percentile-chart.md
git commit -m "docs: record valuation percentile chart rollout"
```
