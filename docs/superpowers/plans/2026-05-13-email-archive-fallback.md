# Email Archive Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add archive-backed fallback reads to the email and valuation enhancement path so slow-changing metrics still render when live APIs fail.

**Architecture:** Keep the existing live fetch helpers unchanged as primary data readers. Add archive readers and archive-aware wrappers in `monitor_drawdown.py`, then wire those wrappers only into the valuation/email enhancement path and annotate rendered values when archive data was used.

**Tech Stack:** Python 3.10, pytest, pandas, requests, JSON file archives under `data_archive/`

---

## File Structure

### Files To Modify

- `monitor_drawdown.py`
- `tests/test_monitor_drawdown.py`

### Files To Create

- `docs/superpowers/plans/2026-05-13-email-archive-fallback.md`

### Responsibility Map

- `monitor_drawdown.py`: archive loading, freshness checks, archive-aware wrappers, email rendering labels, valuation-path wiring
- `tests/test_monitor_drawdown.py`: regression coverage for fallback policy, archive freshness, PE reconstruction, text/html archive labels

## Task 1: Add failing tests for archive readers and fallback wrappers

**Files:**
- Modify: `tests/test_monitor_drawdown.py`
- Reference: `data_archive/`

- [ ] **Step 1: Write failing tests for archive loading and freshness**

```python
def test_load_archive_records_reads_index_archive(tmp_path):
    archive_root = tmp_path / "data_archive"
    payload = {
        "source": "archive",
        "index_code": "931052",
        "updated_at": "2026-05-13T12:00:00+08:00",
        "records": [{"trdDt": "2026-05-12", "pETtm": 10.84}],
    }
    path = archive_root / "index_valuation_percentile" / "931052.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    records = md.load_archive_records("index_valuation_percentile", "931052", archive_root=archive_root)

    assert records == [{"trdDt": "2026-05-12", "pETtm": 10.84}]


def test_is_archive_fresh_rejects_records_older_than_seven_days():
    now = md.datetime(2026, 5, 13, 10, 0, tzinfo=md.BEIJING_TZ)

    assert md.is_archive_fresh("2026-05-06", now=now) is True
    assert md.is_archive_fresh("2026-05-05", now=now) is False
```

- [ ] **Step 2: Write failing tests for live success and archive fallback**

```python
def test_fetch_index_dividend_yield_with_archive_fallback_prefers_live(monkeypatch, tmp_path):
    monkeypatch.setattr(md, "fetch_index_dividend_yield", lambda index_code, url="": {
        "index_code": index_code,
        "index_dividend_yield": 4.23,
        "index_dividend_yield_date": "2026-05-13",
    })

    result = md.fetch_index_dividend_yield_with_archive_fallback(
        "931052",
        archive_root=tmp_path / "data_archive",
    )

    assert result["data_source"] == "live"
    assert result.get("archive_latest_date") is None


def test_fetch_index_dividend_yield_with_archive_fallback_uses_fresh_archive(monkeypatch, tmp_path):
    monkeypatch.setattr(
        md,
        "fetch_index_dividend_yield",
        lambda index_code, url="": (_ for _ in ()).throw(RuntimeError("live failed")),
    )
    archive_root = tmp_path / "data_archive"
    path = archive_root / "index_dividend_ratio" / "931052.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "source": "archive",
        "index_code": "931052",
        "updated_at": "2026-05-13T12:00:00+08:00",
        "records": [{"trdCode": "931052", "trdDt": "2026-05-12", "dividendYield": 4.23}],
    }, ensure_ascii=False), encoding="utf-8")

    result = md.fetch_index_dividend_yield_with_archive_fallback(
        "931052",
        archive_root=archive_root,
        now=md.datetime(2026, 5, 13, 15, 0, tzinfo=md.BEIJING_TZ),
    )

    assert result["data_source"] == "archive"
    assert result["archive_latest_date"] == "2026-05-12"
```

- [ ] **Step 3: Run the focused tests to verify they fail**

Run: `python -m pytest tests/test_monitor_drawdown.py -k "archive_fallback or load_archive_records or is_archive_fresh" -v --basetemp D:\gitub_codes\monitor_drawdown\tmp-pytest`

Expected: FAIL with missing helper or wrapper errors

## Task 2: Implement archive helpers and wrappers

**Files:**
- Modify: `monitor_drawdown.py`

- [ ] **Step 1: Add archive file readers and freshness helpers**

```python
ARCHIVE_ROOT = Path(__file__).resolve().parent / "data_archive"


def load_archive_payload(path: Path) -> Dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"archive payload must be object: {path}")
    return payload
```

- [ ] **Step 2: Add archive-aware wrappers for dividend, valuation, PE history, and bond history**

```python
def fetch_index_dividend_yield_with_archive_fallback(...):
    try:
        result = fetch_index_dividend_yield(index_code, url=url)
        result["data_source"] = "live"
        result["archive_latest_date"] = None
        return result
    except Exception:
        ...
```

- [ ] **Step 3: Wire wrappers only into valuation/email enhancement path**

```python
result.update(fetch_index_dividend_yield_with_archive_fallback(...))
result.update(fetch_index_valuation_percentile_with_archive_fallback(...))
```

```python
pe_df, pe_meta = fetch_index_pe_history_with_archive_fallback(...)
bond_df, bond_meta = fetch_cn_10y_bond_history_with_archive_fallback(...)
```

- [ ] **Step 4: Run the focused tests to verify they pass**

Run: `python -m pytest tests/test_monitor_drawdown.py -k "archive_fallback or load_archive_records or is_archive_fresh" -v --basetemp D:\gitub_codes\monitor_drawdown\tmp-pytest`

Expected: PASS

## Task 3: Add failing tests for PE reconstruction and email archive labels

**Files:**
- Modify: `tests/test_monitor_drawdown.py`

- [ ] **Step 1: Write failing PE-history reconstruction test**

```python
def test_fetch_index_pe_history_with_archive_fallback_reconstructs_pe_series(...):
    ...
```

- [ ] **Step 2: Write failing text/html email label tests**

```python
def test_build_email_plain_text_content_marks_archive_metrics():
    ...


def test_build_email_html_content_marks_archive_metrics():
    ...
```

- [ ] **Step 3: Run the focused tests to verify they fail**

Run: `python -m pytest tests/test_monitor_drawdown.py -k "pe_history_with_archive_fallback or marks_archive_metrics" -v --basetemp D:\gitub_codes\monitor_drawdown\tmp-pytest`

Expected: FAIL on missing label output

## Task 4: Implement label rendering and final verification

**Files:**
- Modify: `monitor_drawdown.py`

- [ ] **Step 1: Add metric-level archive label formatters for text and HTML**

```python
def format_archive_suffix(data_source: str, archive_latest_date: str) -> str:
    ...
```

- [ ] **Step 2: Apply labels only to affected metrics in plain text and HTML**

```python
lines.append(f"  股息率: {dy}{format_archive_suffix(...)}")
```

- [ ] **Step 3: Run targeted regression verification**

Run: `python -m pytest tests/test_monitor_drawdown.py -k "archive or email_html_content or email_plain_text_content or fetch_index_pe_history_retries_on_connection_abort" -v --basetemp D:\gitub_codes\monitor_drawdown\tmp-pytest`

Expected: PASS

- [ ] **Step 4: Run full monitor test file verification**

Run: `python -m pytest tests/test_monitor_drawdown.py -v --basetemp D:\gitub_codes\monitor_drawdown\tmp-pytest`

Expected: PASS
