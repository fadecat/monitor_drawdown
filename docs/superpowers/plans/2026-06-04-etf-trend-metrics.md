# ETF Trend Metrics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone trend-analysis layer on top of real ETF.com.cn K-line data that computes `bias20`、`综合趋势`、`转变日`, writes reproducible artifacts, and leaves a manual benchmark-diff entrypoint for later screenshot validation.

**Architecture:** Keep ETF/search/K-line acquisition inside `inspect_etf_trend_sources.py`, and move all trend-metric math into a new pure-analysis module `etf_trend_analysis.py`. The entry script will call that module after K-line fetch succeeds, write per-series analysis files plus latest snapshots, optionally compare against a local manual benchmark file, and extend the existing markdown summary with trend fields.

**Tech Stack:** Python 3.10, pandas, pytest, existing ETF.com.cn helpers in `inspect_etf_trend_sources.py`, `monitor_drawdown.py`, and `analyze_etf_com_cn_period_returns.py`.

---

## Planned File Map

- Create: `etf_trend_analysis.py`
- Create: `tests/test_etf_trend_analysis.py`
- Modify: `inspect_etf_trend_sources.py`
- Modify: `tests/test_inspect_etf_trend_sources.py`

### Task 1: Add Trend Metric Calculation Skeleton

**Files:**
- Create: `tests/test_etf_trend_analysis.py`
- Create: `etf_trend_analysis.py`

- [ ] **Step 1: Write the failing tests for rolling metric calculation and warm-up behavior**

Add `tests/test_etf_trend_analysis.py` with these tests and helpers:

```python
import math

import etf_trend_analysis as module


def _make_records(closes):
    return [
        {"date": f"2026-01-{index + 1:02d}", "close": float(close)}
        for index, close in enumerate(closes)
    ]


def test_analyze_trend_series_computes_ma20_bias20_and_direction5():
    closes = list(range(100, 130))
    analysis = module.analyze_trend_series(_make_records(closes))

    latest = analysis["records"][-1]

    expected_ma20 = sum(closes[-20:]) / 20
    expected_bias20_raw = closes[-1] / expected_ma20 - 1

    bias20_raw_series = []
    for end_index in range(19, len(closes)):
        window = closes[end_index - 19 : end_index + 1]
        ma20 = sum(window) / 20
        bias20_raw_series.append(closes[end_index] / ma20 - 1)
    expected_bias20 = sum(bias20_raw_series[-5:]) / 5
    expected_direction5 = expected_bias20 - bias20_raw_series[-6]

    assert latest["ma20"] == expected_ma20
    assert latest["bias20_raw"] == expected_bias20_raw
    assert latest["bias20"] == expected_bias20
    assert latest["direction5"] == expected_direction5


def test_analyze_trend_series_keeps_trend_fields_empty_during_warm_up():
    analysis = module.analyze_trend_series(_make_records(range(100, 128)))

    latest = analysis["records"][-1]

    assert latest["ma20"] is not None
    assert latest["bias20_raw"] is not None
    assert latest["bias20"] is not None
    assert latest["direction5"] is None
    assert latest["trend_state"] is None
    assert latest["transition_confirmed"] is False
    assert latest["transition_date"] is None
```

- [ ] **Step 2: Run the new test file and verify it fails**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; python -m pytest tests/test_etf_trend_analysis.py -q
```

Expected:

- `ModuleNotFoundError: No module named 'etf_trend_analysis'`

- [ ] **Step 3: Write the minimal analysis module for normalization, rolling fields, and empty transition flags**

Create `etf_trend_analysis.py` with this initial implementation:

```python
from __future__ import annotations

from typing import Any

import pandas as pd


def _optional_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _normalize_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in records:
        date_text = str(row.get("date") or "").strip()
        close_value = row.get("close")
        if not date_text or close_value in {None, ""}:
            continue
        try:
            normalized.append({"date": date_text, "close": float(close_value)})
        except (TypeError, ValueError):
            continue
    return sorted(normalized, key=lambda item: item["date"])


def analyze_trend_series(records: list[dict[str, Any]]) -> dict[str, Any]:
    normalized = _normalize_records(records)
    if not normalized:
        return {
            "records": [],
            "latest_transition_date": None,
            "latest_valid_state": None,
            "latest_valid_date": None,
        }

    frame = pd.DataFrame(normalized)
    frame["ma20"] = frame["close"].rolling(20).mean()
    frame["bias20_raw"] = frame["close"] / frame["ma20"] - 1
    frame["bias20"] = frame["bias20_raw"].rolling(5).mean()
    frame["direction5"] = frame["bias20"] - frame["bias20"].shift(5)
    frame["trend_state"] = None
    frame["state_candidate_changed"] = False
    frame["transition_confirmed"] = False
    frame["transition_date"] = None

    output_records = []
    for row in frame.to_dict(orient="records"):
        output_records.append(
            {
                "date": str(row["date"]),
                "close": float(row["close"]),
                "ma20": _optional_float(row["ma20"]),
                "bias20_raw": _optional_float(row["bias20_raw"]),
                "bias20": _optional_float(row["bias20"]),
                "direction5": _optional_float(row["direction5"]),
                "trend_state": row["trend_state"],
                "state_candidate_changed": bool(row["state_candidate_changed"]),
                "transition_confirmed": bool(row["transition_confirmed"]),
                "transition_date": row["transition_date"],
            }
        )

    return {
        "records": output_records,
        "latest_transition_date": None,
        "latest_valid_state": None,
        "latest_valid_date": None,
    }


def build_latest_trend_snapshot(analysis: dict[str, Any]) -> dict[str, Any]:
    records = analysis.get("records") or []
    if not records:
        return {
            "latest_date": None,
            "close": None,
            "bias20_raw": None,
            "bias20": None,
            "direction5": None,
            "trend_state": None,
            "latest_transition_date": None,
        }

    latest = records[-1]
    return {
        "latest_date": latest["date"],
        "close": latest["close"],
        "bias20_raw": latest["bias20_raw"],
        "bias20": latest["bias20"],
        "direction5": latest["direction5"],
        "trend_state": latest["trend_state"],
        "latest_transition_date": analysis.get("latest_transition_date"),
    }
```

- [ ] **Step 4: Run the trend-analysis tests and verify they pass**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; python -m pytest tests/test_etf_trend_analysis.py -q
```

Expected:

- `2 passed`

- [ ] **Step 5: Commit the skeleton**

```powershell
git add etf_trend_analysis.py tests/test_etf_trend_analysis.py
git commit -m "feat: add trend metric calculation skeleton"
```

### Task 2: Add Trend State Classification and Transition Confirmation

**Files:**
- Modify: `tests/test_etf_trend_analysis.py`
- Modify: `etf_trend_analysis.py`

- [ ] **Step 1: Add failing tests for state classification, confirmed transition dates, and rejected one-day reversals**

Append these tests to `tests/test_etf_trend_analysis.py`:

```python
def test_classify_trend_state_maps_bias20_and_direction5_to_four_quadrants():
    assert module._classify_trend_state_value(0.01, 0.02) == "强势上行"
    assert module._classify_trend_state_value(0.01, 0.0) == "强势回落"
    assert module._classify_trend_state_value(-0.01, 0.02) == "弱势修复"
    assert module._classify_trend_state_value(-0.01, -0.02) == "弱势下行"
    assert module._classify_trend_state_value(None, 0.02) is None


def test_confirm_transitions_marks_first_new_state_after_two_day_confirmation():
    records = [
        {
            "date": "2026-06-01",
            "close": 1.0,
            "ma20": 1.0,
            "bias20_raw": -0.02,
            "bias20": -0.01,
            "direction5": -0.01,
            "trend_state": "弱势下行",
            "state_candidate_changed": False,
            "transition_confirmed": False,
            "transition_date": None,
        },
        {
            "date": "2026-06-02",
            "close": 1.0,
            "ma20": 1.0,
            "bias20_raw": -0.01,
            "bias20": -0.005,
            "direction5": 0.01,
            "trend_state": "弱势修复",
            "state_candidate_changed": False,
            "transition_confirmed": False,
            "transition_date": None,
        },
        {
            "date": "2026-06-03",
            "close": 1.0,
            "ma20": 1.0,
            "bias20_raw": -0.005,
            "bias20": -0.002,
            "direction5": 0.02,
            "trend_state": "弱势修复",
            "state_candidate_changed": False,
            "transition_confirmed": False,
            "transition_date": None,
        },
    ]

    confirmed = module._confirm_transitions(records)

    assert confirmed[1]["state_candidate_changed"] is True
    assert confirmed[1]["transition_confirmed"] is False
    assert confirmed[2]["transition_confirmed"] is True
    assert confirmed[2]["transition_date"] == "2026-06-02"


def test_confirm_transitions_drops_candidate_when_state_reverts_next_day():
    records = [
        {
            "date": "2026-06-01",
            "close": 1.0,
            "ma20": 1.0,
            "bias20_raw": -0.02,
            "bias20": -0.01,
            "direction5": -0.01,
            "trend_state": "弱势下行",
            "state_candidate_changed": False,
            "transition_confirmed": False,
            "transition_date": None,
        },
        {
            "date": "2026-06-02",
            "close": 1.0,
            "ma20": 1.0,
            "bias20_raw": -0.01,
            "bias20": -0.005,
            "direction5": 0.01,
            "trend_state": "弱势修复",
            "state_candidate_changed": False,
            "transition_confirmed": False,
            "transition_date": None,
        },
        {
            "date": "2026-06-03",
            "close": 1.0,
            "ma20": 1.0,
            "bias20_raw": -0.015,
            "bias20": -0.008,
            "direction5": -0.01,
            "trend_state": "弱势下行",
            "state_candidate_changed": False,
            "transition_confirmed": False,
            "transition_date": None,
        },
    ]

    confirmed = module._confirm_transitions(records)

    assert confirmed[1]["state_candidate_changed"] is True
    assert confirmed[2]["transition_confirmed"] is False
    assert confirmed[2]["transition_date"] is None
```

- [ ] **Step 2: Run the test file and verify it fails on missing helpers / empty transition logic**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; python -m pytest tests/test_etf_trend_analysis.py -q
```

Expected:

- failures mentioning `_classify_trend_state_value`
- or failures mentioning `transition_confirmed` / `transition_date`

- [ ] **Step 3: Implement state classification and transition confirmation in the analysis module**

Update `etf_trend_analysis.py` with these functions and integrate them into `analyze_trend_series`:

```python
def _classify_trend_state_value(bias20: float | None, direction5: float | None) -> str | None:
    if bias20 is None or direction5 is None:
        return None
    if bias20 > 0 and direction5 > 0:
        return "强势上行"
    if bias20 > 0 and direction5 <= 0:
        return "强势回落"
    if bias20 <= 0 and direction5 > 0:
        return "弱势修复"
    return "弱势下行"


def _confirm_transitions(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not records:
        return []

    output = [dict(record) for record in records]
    previous_state: str | None = None
    candidate_state: str | None = None
    candidate_date: str | None = None
    candidate_index: int | None = None

    for index, row in enumerate(output):
        state = row.get("trend_state")
        if state is None:
            continue
        if previous_state is None:
            previous_state = state
            continue
        if candidate_state is None:
            if state != previous_state:
                row["state_candidate_changed"] = True
                candidate_state = state
                candidate_date = row["date"]
                candidate_index = index
            continue
        if state == candidate_state:
            row["transition_confirmed"] = True
            row["transition_date"] = candidate_date
            previous_state = candidate_state
        candidate_state = None
        candidate_date = None
        candidate_index = None

    return output
```

Replace the tail of `analyze_trend_series` with:

```python
    output_records = []
    for row in frame.to_dict(orient="records"):
        bias20 = _optional_float(row["bias20"])
        direction5 = _optional_float(row["direction5"])
        output_records.append(
            {
                "date": str(row["date"]),
                "close": float(row["close"]),
                "ma20": _optional_float(row["ma20"]),
                "bias20_raw": _optional_float(row["bias20_raw"]),
                "bias20": bias20,
                "direction5": direction5,
                "trend_state": _classify_trend_state_value(bias20, direction5),
                "state_candidate_changed": False,
                "transition_confirmed": False,
                "transition_date": None,
            }
        )

    output_records = _confirm_transitions(output_records)
    latest_valid = next((row for row in reversed(output_records) if row["trend_state"] is not None), None)
    latest_transition = next(
        (row["transition_date"] for row in reversed(output_records) if row["transition_date"] is not None),
        None,
    )

    return {
        "records": output_records,
        "latest_transition_date": latest_transition,
        "latest_valid_state": None if latest_valid is None else latest_valid["trend_state"],
        "latest_valid_date": None if latest_valid is None else latest_valid["date"],
    }
```

- [ ] **Step 4: Run the focused trend-analysis tests and verify they all pass**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; python -m pytest tests/test_etf_trend_analysis.py -q
```

Expected:

- `5 passed`

- [ ] **Step 5: Commit the completed trend-analysis module**

```powershell
git add etf_trend_analysis.py tests/test_etf_trend_analysis.py
git commit -m "feat: add trend state and transition analysis"
```

### Task 3: Integrate Trend Analysis Into the ETF Inspection Script

**Files:**
- Modify: `inspect_etf_trend_sources.py`
- Modify: `tests/test_inspect_etf_trend_sources.py`

- [ ] **Step 1: Add failing script-level tests for trend summary fields and benchmark diff generation**

Append these tests to `tests/test_inspect_etf_trend_sources.py`:

```python
def test_build_summary_includes_trend_state_bias20_and_transition_date():
    resolved = [
        {
            "label": "煤炭ETF",
            "status": "ok",
            "selected_primary": {"kind": "etf", "code": "515220", "name": "煤炭ETF国泰"},
        }
    ]
    kline_results = [
        {
            "label": "煤炭ETF",
            "status": "ok",
            "selected_primary": {"kind": "etf", "code": "515220", "name": "煤炭ETF国泰"},
        }
    ]
    trend_results = [
        {
            "label": "煤炭ETF",
            "status": "ok",
            "latest_snapshot": {
                "bias20": 0.0256,
                "trend_state": "强势回落",
                "latest_transition_date": "2026-05-28",
            },
        }
    ]

    summary = module.build_summary(resolved, kline_results, trend_results)

    assert "trend=强势回落" in summary
    assert "bias20=0.0256" in summary
    assert "transition=2026-05-28" in summary


def test_build_trend_benchmark_diffs_compares_bias_state_and_transition():
    snapshots = [
        {
            "label": "煤炭ETF",
            "selected_primary": {"kind": "etf", "code": "515220", "name": "煤炭ETF国泰"},
            "latest_date": "2026-06-04",
            "close": 1.2345,
            "bias20_raw": 0.0312,
            "bias20": 0.0256,
            "direction5": -0.0041,
            "trend_state": "强势回落",
            "latest_transition_date": "2026-05-28",
        }
    ]
    benchmarks = [
        {
            "label": "煤炭ETF",
            "as_of_date": "2026-06-04",
            "expected_bias20": 0.0248,
            "expected_trend_state": "强势回落",
            "expected_transition_date": "2026-05-27",
        }
    ]

    diffs = module.build_trend_benchmark_diffs(snapshots, benchmarks)

    assert diffs == [
        {
            "label": "煤炭ETF",
            "as_of_date": "2026-06-04",
            "actual_bias20": 0.0256,
            "expected_bias20": 0.0248,
            "bias20_diff": 0.0008,
            "actual_trend_state": "强势回落",
            "expected_trend_state": "强势回落",
            "trend_state_match": True,
            "actual_transition_date": "2026-05-28",
            "expected_transition_date": "2026-05-27",
            "transition_date_match": False,
        }
    ]
```

- [ ] **Step 2: Run the script-level test file and verify it fails on the new function signatures**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; python -m pytest tests/test_inspect_etf_trend_sources.py -q
```

Expected:

- failure because `build_summary()` still takes 2 arguments
- or failure because `build_trend_benchmark_diffs()` does not exist

- [ ] **Step 3: Modify the inspection script to analyze saved series, write new artifacts, and compare optional benchmarks**

Apply these changes to `inspect_etf_trend_sources.py`:

```python
import etf_trend_analysis as trend_analysis


SERIES_ANALYSIS_DIR = OUTPUT_ROOT / "series_analysis"
MANUAL_TREND_BENCHMARKS_PATH = OUTPUT_ROOT / "manual_trend_benchmarks.json"
TREND_METRICS_SUMMARY_PATH = OUTPUT_ROOT / "trend_metrics_summary.json"
TREND_BENCHMARK_DIFF_PATH = OUTPUT_ROOT / "trend_benchmark_diff.json"


def ensure_output_dirs() -> None:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    SERIES_DIR.mkdir(parents=True, exist_ok=True)
    SERIES_ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def format_optional_float(value: Any) -> str:
    if value in {None, ""}:
        return "-"
    return f"{float(value):.4f}"


def materialize_trend_analysis(kline_result: dict[str, Any]) -> dict[str, Any]:
    selected_primary = kline_result.get("selected_primary")
    if kline_result.get("status") != "ok" or not selected_primary:
        return {
            "label": kline_result["label"],
            "status": kline_result["status"],
            "selected_primary": selected_primary,
            "latest_snapshot": None,
        }

    source_records = read_json(Path(str(kline_result["series_file"])))
    analysis = trend_analysis.analyze_trend_series(source_records)
    latest_snapshot = trend_analysis.build_latest_trend_snapshot(analysis)

    filename = f"{selected_primary['kind']}_{selected_primary['code']}.json"
    analysis_path = SERIES_ANALYSIS_DIR / filename
    write_json(analysis_path, analysis["records"])

    return {
        "label": kline_result["label"],
        "status": "ok",
        "selected_primary": selected_primary,
        "latest_snapshot": latest_snapshot,
        "analysis_file": str(analysis_path.as_posix()),
    }


def load_manual_trend_benchmarks(path: Path = MANUAL_TREND_BENCHMARKS_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = read_json(path)
    return payload if isinstance(payload, list) else []


def build_trend_benchmark_diffs(
    snapshots: list[dict[str, Any]], benchmarks: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    snapshot_by_label = {item["label"]: item for item in snapshots}
    diffs: list[dict[str, Any]] = []

    for benchmark in benchmarks:
        label = str(benchmark.get("label") or "").strip()
        actual = snapshot_by_label.get(label)
        if not label or not actual:
            continue
        actual_bias20 = actual.get("bias20")
        expected_bias20 = benchmark.get("expected_bias20")
        bias20_diff = None
        if actual_bias20 is not None and expected_bias20 is not None:
            bias20_diff = round(float(actual_bias20) - float(expected_bias20), 6)
        diffs.append(
            {
                "label": label,
                "as_of_date": str(benchmark.get("as_of_date") or actual.get("latest_date") or ""),
                "actual_bias20": actual_bias20,
                "expected_bias20": expected_bias20,
                "bias20_diff": bias20_diff,
                "actual_trend_state": actual.get("trend_state"),
                "expected_trend_state": benchmark.get("expected_trend_state"),
                "trend_state_match": actual.get("trend_state") == benchmark.get("expected_trend_state"),
                "actual_transition_date": actual.get("latest_transition_date"),
                "expected_transition_date": benchmark.get("expected_transition_date"),
                "transition_date_match": actual.get("latest_transition_date")
                == benchmark.get("expected_transition_date"),
            }
        )
    return diffs
```

Replace `build_summary` with:

```python
def build_summary(
    resolved: list[dict[str, Any]],
    kline_results: list[dict[str, Any]],
    trend_results: list[dict[str, Any]],
) -> str:
    ok_count = sum(1 for item in kline_results if item["status"] == "ok")
    unresolved_count = sum(1 for item in resolved if item["status"] == "unresolved")
    search_failed_count = sum(1 for item in resolved if item["status"] == "search_failed")
    kline_failed_count = sum(1 for item in kline_results if item["status"] == "kline_failed")

    lines = [
        "# ETF Trend Source Inspection",
        "",
        f"- total targets: {len(resolved)}",
        f"- ok: {ok_count}",
        f"- unresolved: {unresolved_count}",
        f"- search_failed: {search_failed_count}",
        f"- kline_failed: {kline_failed_count}",
        "",
        "## Per Target",
        "",
    ]

    kline_by_label = {item["label"]: item for item in kline_results}
    trend_by_label = {item["label"]: item for item in trend_results}

    for item in resolved:
        label = item["label"]
        kline = kline_by_label.get(label, {})
        trend = trend_by_label.get(label, {})
        latest_snapshot = trend.get("latest_snapshot") or {}
        selected = item.get("selected_primary")
        selected_text = (
            f"{selected['kind']}:{selected['code']} {selected['name']}" if selected else "none"
        )
        lines.append(
            f"- {label}: resolve={item['status']} kline={kline.get('status', 'unknown')} "
            f"selected={selected_text} trend={latest_snapshot.get('trend_state', '-')} "
            f"bias20={format_optional_float(latest_snapshot.get('bias20'))} "
            f"transition={latest_snapshot.get('latest_transition_date') or '-'}"
        )

    return "\n".join(lines) + "\n"
```

Update the `run()` tail to:

```python
    kline_results = [materialize_kline(item) for item in resolved_results]
    write_json(OUTPUT_ROOT / "kline_samples.json", kline_results)

    trend_results = [materialize_trend_analysis(item) for item in kline_results]
    write_json(OUTPUT_ROOT / "trend_analysis_results.json", trend_results)

    trend_summary_payload = [
        {
            "label": item["label"],
            "selected_primary": item["selected_primary"],
            **(item["latest_snapshot"] or {}),
        }
        for item in trend_results
        if item["status"] == "ok" and item.get("latest_snapshot")
    ]
    write_json(TREND_METRICS_SUMMARY_PATH, trend_summary_payload)

    benchmarks = load_manual_trend_benchmarks()
    if benchmarks:
        benchmark_diffs = build_trend_benchmark_diffs(trend_summary_payload, benchmarks)
        write_json(TREND_BENCHMARK_DIFF_PATH, benchmark_diffs)

    summary_text = build_summary(resolved_results, kline_results, trend_results)
    (OUTPUT_ROOT / "summary.md").write_text(summary_text, encoding="utf-8")
```

- [ ] **Step 4: Run both targeted test files and verify integration passes**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; python -m pytest tests/test_etf_trend_analysis.py tests/test_inspect_etf_trend_sources.py -q
```

Expected:

- all tests pass

- [ ] **Step 5: Commit the script integration**

```powershell
git add inspect_etf_trend_sources.py tests/test_inspect_etf_trend_sources.py etf_trend_analysis.py tests/test_etf_trend_analysis.py
git commit -m "feat: integrate trend metrics into ETF inspection artifacts"
```

### Task 4: Verify Artifacts Against Real Data and Preserve the Research Entry Point

**Files:**
- Modify: `inspect_etf_trend_sources.py` if verification reveals missing fields or formatting gaps
- Output: `.test_artifacts/etf_trend_sources/series_analysis/*.json`
- Output: `.test_artifacts/etf_trend_sources/trend_metrics_summary.json`
- Output: `.test_artifacts/etf_trend_sources/summary.md`

- [ ] **Step 1: Run the full focused test suite before any live verification**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; python -m pytest tests/test_etf_trend_analysis.py tests/test_inspect_etf_trend_sources.py -q
```

Expected:

- all tests pass

- [ ] **Step 2: Run the live ETF.com.cn inspection script and generate fresh artifacts**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; python inspect_etf_trend_sources.py
```

Expected:

- live search / K-line logs
- final log line: `artifacts written to .test_artifacts\etf_trend_sources`

- [ ] **Step 3: Inspect the generated summary and verify the new trend fields exist**

Run:

```powershell
Get-Content .test_artifacts/etf_trend_sources/summary.md
```

Expected:

- each target line includes `trend=...`
- each target line includes `bias20=...`
- each target line includes `transition=...`

- [ ] **Step 4: Inspect the new JSON artifacts and verify snapshot / per-series outputs exist**

Run:

```powershell
Get-Content .test_artifacts/etf_trend_sources/trend_metrics_summary.json | Select-Object -First 80
Get-ChildItem .test_artifacts/etf_trend_sources/series_analysis | Select-Object Name
```

Expected:

- `trend_metrics_summary.json` contains `bias20_raw`, `bias20`, `direction5`, `trend_state`, `latest_transition_date`
- `series_analysis` contains one JSON per resolved primary instrument

- [ ] **Step 5: Commit the verified implementation**

```powershell
git add etf_trend_analysis.py inspect_etf_trend_sources.py tests/test_etf_trend_analysis.py tests/test_inspect_etf_trend_sources.py
git commit -m "feat: add ETF trend metric research workflow"
```

## Self-Review Checklist

- Spec coverage:
  - `bias20_raw` / `bias20` / `direction5`: Task 1
  - four-state `综合趋势`: Task 2
  - two-day confirmed `转变日`: Task 2
  - per-series and latest-summary artifacts: Task 3
  - manual benchmark diff entrypoint: Task 3
  - real-data verification: Task 4
- Placeholder scan:
  - no `TODO`, `TBD`, or “similar to previous task” shortcuts
- Type consistency:
  - `analyze_trend_series()` always returns `records`, `latest_transition_date`, `latest_valid_state`, `latest_valid_date`
  - snapshot payload always uses `latest_transition_date`
  - script summary always reads `latest_snapshot`
