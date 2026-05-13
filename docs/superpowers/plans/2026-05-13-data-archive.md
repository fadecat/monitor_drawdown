# Data Archive Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a separate archival pipeline that persists slow-changing historical index and bond datasets into repository files, with incremental updates and automatic commit-on-change behavior.

**Architecture:** Add a dedicated `refresh_data_archive.py` script that reads `config.yaml`, resolves archive targets, fetches raw upstream history, merges it into stable JSON archive files, and exits independently from monitoring logic. Keep the existing monitor workflow unchanged, and add a new GitHub Actions workflow that runs once after close and commits only changed archive files.

**Tech Stack:** Python 3.10, pytest, requests, PyYAML, pandas, AkShare, GitHub Actions

---

## File Structure

### Files To Create

- `refresh_data_archive.py`
- `tests/test_refresh_data_archive.py`
- `.github/workflows/refresh_data_archive.yml`
- `docs/superpowers/specs/2026-05-13-data-archive-design.md`
- `docs/superpowers/plans/2026-05-13-data-archive.md`

### Files To Modify

- `.gitignore`
- `README.md`

### Responsibility Map

- `refresh_data_archive.py`: archive target resolution, upstream fetch, merge logic, stable JSON writing, logging, exit behavior
- `tests/test_refresh_data_archive.py`: regression tests for archive-specific logic, no live network calls
- `.github/workflows/refresh_data_archive.yml`: scheduled/manual archival run with conditional commit
- `.gitignore`: ensure archive output is tracked while runtime cache directories remain ignored
- `README.md`: document the new archive workflow and output layout

### Constraints To Preserve

- Do not couple archive execution to `monitor_drawdown.py` main flow.
- Do not change current monitoring workflow behavior.
- Do not delete archive files for removed targets.
- Preserve upstream raw fields in stored records where practical.

## Task 1: Add archive target resolution tests

**Files:**
- Create: `tests/test_refresh_data_archive.py`
- Reference: `config.yaml`

- [ ] **Step 1: Write the failing tests for target resolution and dedupe**

```python
from pathlib import Path

import refresh_data_archive as rda


def test_resolve_archive_index_codes_prefers_tracking_index_then_index_then_code(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
targets:
  - name: etf-a
    type: etf
    code: "510300"
    tracking_index_code: "000300"
  - name: index-a
    type: index
    code: "399303"
  - name: valuation-a
    type: valuation
    code: "930955"
    index_detail_url: "https://www.etf.com.cn/api/etf-api-service/index/detail?indexCode=930955"
  - name: explicit-index
    type: etf
    code: "159307"
    index_code: "931052"
""".strip(),
        encoding="utf-8",
    )

    targets = rda.load_config(str(config_path))

    assert rda.resolve_archive_index_codes(targets) == ["000300", "399303", "930955", "931052"]


def test_resolve_archive_index_codes_dedupes_and_skips_unresolved_targets(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
targets:
  - name: one
    type: valuation
    code: "930955"
  - name: two
    type: etf
    code: "515000"
    tracking_index_code: "930955"
  - name: three
    type: calendar
    code: "ignored"
  - name: four
    type: etf
    code: "159001"
""".strip(),
        encoding="utf-8",
    )

    targets = rda.load_config(str(config_path))

    assert rda.resolve_archive_index_codes(targets) == ["930955"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_refresh_data_archive.py -k resolve_archive_index_codes -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'refresh_data_archive'`

- [ ] **Step 3: Add a minimal archive script scaffold**

```python
from typing import Dict, List

from monitor_drawdown import load_config


def resolve_archive_index_codes(targets: List[Dict]) -> List[str]:
    raise NotImplementedError
```

- [ ] **Step 4: Implement the minimal target resolution logic**

```python
def resolve_archive_index_code(target: Dict) -> str:
    tracking_index_code = str(target.get("tracking_index_code") or "").strip()
    if tracking_index_code:
        return tracking_index_code

    index_code = str(target.get("index_code") or "").strip()
    if index_code:
        return index_code

    target_type = str(target.get("type") or "").strip().lower()
    code = str(target.get("code") or "").strip()
    if target_type in {"index", "valuation"} and code:
        return code

    return ""


def resolve_archive_index_codes(targets: List[Dict]) -> List[str]:
    seen = set()
    result: List[str] = []
    for target in targets:
        code = resolve_archive_index_code(target)
        if code and code not in seen:
            result.append(code)
            seen.add(code)
    return result
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_refresh_data_archive.py -k resolve_archive_index_codes -v`

Expected: PASS for both target resolution tests

- [ ] **Step 6: Commit**

```bash
git add refresh_data_archive.py tests/test_refresh_data_archive.py
git commit -m "test: add archive target resolution coverage"
```

## Task 2: Add merge logic tests for JSON archive records

**Files:**
- Modify: `tests/test_refresh_data_archive.py`
- Modify: `refresh_data_archive.py`

- [ ] **Step 1: Write failing merge tests for overwrite, sort, and raw field preservation**

```python
def test_merge_records_overwrites_same_key_and_preserves_new_raw_fields():
    existing = [
        {"trdDt": "2026-05-12", "pxClose": 101.2, "legacy": "keep-old"},
        {"trdDt": "2026-05-13", "pxClose": 102.5, "legacy": "replace-me"},
    ]
    incoming = [
        {"trdDt": "2026-05-13", "pxClose": 102.8, "newField": "fresh"},
        {"trdDt": "2026-05-14", "pxClose": 103.1, "newField": "latest"},
    ]

    merged = rda.merge_records_by_key(existing, incoming, key="trdDt")

    assert merged == [
        {"trdDt": "2026-05-12", "pxClose": 101.2, "legacy": "keep-old"},
        {"trdDt": "2026-05-13", "pxClose": 102.8, "newField": "fresh"},
        {"trdDt": "2026-05-14", "pxClose": 103.1, "newField": "latest"},
    ]


def test_merge_records_by_key_uses_date_column_for_bond_history():
    existing = [
        {"日期": "2026-05-12", "中国国债收益率10年": 1.71},
    ]
    incoming = [
        {"日期": "2026-05-13", "中国国债收益率10年": 1.73},
        {"日期": "2026-05-12", "中国国债收益率10年": 1.72},
    ]

    merged = rda.merge_records_by_key(existing, incoming, key="日期")

    assert merged == [
        {"日期": "2026-05-12", "中国国债收益率10年": 1.72},
        {"日期": "2026-05-13", "中国国债收益率10年": 1.73},
    ]
```

- [ ] **Step 2: Run the merge tests to verify they fail**

Run: `python -m pytest tests/test_refresh_data_archive.py -k merge_records_by_key -v`

Expected: FAIL with `AttributeError` because `merge_records_by_key` does not exist

- [ ] **Step 3: Implement minimal merge helpers**

```python
from typing import Any


def _record_key(record: Dict[str, Any], key: str) -> str:
    return str(record.get(key) or "").strip()


def merge_records_by_key(existing: List[Dict[str, Any]], incoming: List[Dict[str, Any]], key: str) -> List[Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}

    for record in existing:
        record_key = _record_key(record, key)
        if record_key:
            merged[record_key] = record

    for record in incoming:
        record_key = _record_key(record, key)
        if record_key:
            merged[record_key] = record

    return [merged[k] for k in sorted(merged)]
```

- [ ] **Step 4: Run the merge tests to verify they pass**

Run: `python -m pytest tests/test_refresh_data_archive.py -k merge_records_by_key -v`

Expected: PASS for overwrite and sort behavior

- [ ] **Step 5: Commit**

```bash
git add refresh_data_archive.py tests/test_refresh_data_archive.py
git commit -m "feat: add archive merge helpers"
```

## Task 3: Add stable envelope serialization and no-op write tests

**Files:**
- Modify: `tests/test_refresh_data_archive.py`
- Modify: `refresh_data_archive.py`

- [ ] **Step 1: Write failing tests for JSON envelope writing and unchanged output detection**

```python
import json


def test_write_archive_file_creates_expected_envelope(tmp_path: Path):
    output_path = tmp_path / "index_eod" / "930955.json"
    changed = rda.write_archive_file(
        output_path=output_path,
        source="https://cdn.efunds.com.cn/etf-net/index_eod_price_930955.json",
        identity={"index_code": "930955"},
        records=[{"trdDt": "2026-05-13", "pxClose": 4417.997}],
        updated_at="2026-05-13T15:10:00+08:00",
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert changed is True
    assert payload["source"].endswith("index_eod_price_930955.json")
    assert payload["index_code"] == "930955"
    assert payload["updated_at"] == "2026-05-13T15:10:00+08:00"
    assert payload["records"] == [{"trdDt": "2026-05-13", "pxClose": 4417.997}]


def test_write_archive_file_returns_false_when_content_is_unchanged(tmp_path: Path):
    output_path = tmp_path / "bond_10y" / "china_10y.json"

    first = rda.write_archive_file(
        output_path=output_path,
        source="akshare.bond_zh_us_rate",
        identity={"series": "china_10y"},
        records=[{"日期": "2026-05-13", "中国国债收益率10年": 1.73}],
        updated_at="2026-05-13T15:10:00+08:00",
    )
    second = rda.write_archive_file(
        output_path=output_path,
        source="akshare.bond_zh_us_rate",
        identity={"series": "china_10y"},
        records=[{"日期": "2026-05-13", "中国国债收益率10年": 1.73}],
        updated_at="2026-05-13T15:10:00+08:00",
    )

    assert first is True
    assert second is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_refresh_data_archive.py -k write_archive_file -v`

Expected: FAIL with `AttributeError` because `write_archive_file` does not exist

- [ ] **Step 3: Implement stable payload serialization and conditional write**

```python
import json
from pathlib import Path


def build_archive_payload(source: str, identity: Dict[str, str], records: List[Dict], updated_at: str) -> Dict:
    payload = {"source": source, **identity, "updated_at": updated_at, "records": records}
    return payload


def write_archive_file(output_path: Path, source: str, identity: Dict[str, str], records: List[Dict], updated_at: str) -> bool:
    payload = build_archive_payload(source=source, identity=identity, records=records, updated_at=updated_at)
    serialized = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False) + "\n"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        existing = output_path.read_text(encoding="utf-8")
        if existing == serialized:
            return False

    output_path.write_text(serialized, encoding="utf-8")
    return True
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_refresh_data_archive.py -k write_archive_file -v`

Expected: PASS for envelope creation and no-op detection

- [ ] **Step 5: Commit**

```bash
git add refresh_data_archive.py tests/test_refresh_data_archive.py
git commit -m "feat: add archive file writer"
```

## Task 4: Add fetch adapters and bond raw-field serialization tests

**Files:**
- Modify: `tests/test_refresh_data_archive.py`
- Modify: `refresh_data_archive.py`

- [ ] **Step 1: Write failing tests for index JSON fetch passthrough and bond raw record conversion**

```python
def test_fetch_index_archive_records_returns_upstream_rows(monkeypatch):
    payload = [
        {"trdDt": "2026-05-12", "trdCode": "930955", "pxClose": 4388.12},
        {"trdDt": "2026-05-13", "trdCode": "930955", "pxClose": 4417.99, "extra": "raw"},
    ]
    monkeypatch.setattr(rda, "fetch_json_response", lambda name, url: payload)

    rows = rda.fetch_index_archive_records(
        dataset_name="index_eod",
        index_code="930955",
        url="https://cdn.efunds.com.cn/etf-net/index_eod_price_930955.json",
    )

    assert rows == payload


def test_fetch_bond_archive_records_preserves_original_column_names(monkeypatch):
    df = pd.DataFrame(
        [
            {"日期": "2026-05-12", "中国国债收益率10年": 1.71, "中国国债收益率2年": 1.42},
            {"日期": "2026-05-13", "中国国债收益率10年": 1.73, "中国国债收益率2年": 1.44},
        ]
    )
    monkeypatch.setattr(rda.ak, "bond_zh_us_rate", lambda start_date: df, raising=False)

    rows = rda.fetch_bond_archive_records(start_date="20200101")

    assert rows == [
        {"日期": "2026-05-12", "中国国债收益率10年": 1.71, "中国国债收益率2年": 1.42},
        {"日期": "2026-05-13", "中国国债收益率10年": 1.73, "中国国债收益率2年": 1.44},
    ]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_refresh_data_archive.py -k "fetch_index_archive_records or fetch_bond_archive_records" -v`

Expected: FAIL with missing function errors

- [ ] **Step 3: Implement raw fetch adapters**

```python
import pandas as pd

import akshare as ak
from monitor_drawdown import (
    build_index_dividend_yield_url,
    build_index_eod_price_url,
    build_index_valuation_percentile_url,
    fetch_json_response,
)


def fetch_index_archive_records(dataset_name: str, index_code: str, url: str) -> List[Dict]:
    rows = fetch_json_response(dataset_name, url)
    if not isinstance(rows, list):
        raise ValueError(f"{dataset_name} returned non-list payload")
    return [row for row in rows if isinstance(row, dict)]


def fetch_bond_archive_records(start_date: str) -> List[Dict]:
    df = ak.bond_zh_us_rate(start_date=start_date)
    if df is None or df.empty:
        return []
    raw_df = df.where(pd.notna(df), None)
    return raw_df.to_dict(orient="records")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_refresh_data_archive.py -k "fetch_index_archive_records or fetch_bond_archive_records" -v`

Expected: PASS for both raw fetch tests

- [ ] **Step 5: Commit**

```bash
git add refresh_data_archive.py tests/test_refresh_data_archive.py
git commit -m "feat: add archive fetch adapters"
```

## Task 5: Implement the archive refresh orchestration

**Files:**
- Modify: `refresh_data_archive.py`
- Modify: `tests/test_refresh_data_archive.py`

- [ ] **Step 1: Write failing orchestration tests for one index dataset and one bond dataset**

```python
def test_refresh_index_archive_merges_existing_and_returns_changed_path(tmp_path: Path, monkeypatch):
    archive_root = tmp_path / "data_archive"
    existing_path = archive_root / "index_eod" / "930955.json"
    existing_path.parent.mkdir(parents=True, exist_ok=True)
    existing_path.write_text(
        json.dumps(
            {
                "source": "https://cdn.efunds.com.cn/etf-net/index_eod_price_930955.json",
                "index_code": "930955",
                "updated_at": "2026-05-12T15:10:00+08:00",
                "records": [{"trdDt": "2026-05-12", "pxClose": 4388.12}],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        rda,
        "fetch_index_archive_records",
        lambda dataset_name, index_code, url: [{"trdDt": "2026-05-13", "pxClose": 4417.99}],
    )

    changed = rda.refresh_index_dataset(
        archive_root=archive_root,
        dataset_name="index_eod",
        index_code="930955",
        source_url="https://cdn.efunds.com.cn/etf-net/index_eod_price_930955.json",
        merge_key="trdDt",
        updated_at="2026-05-13T15:10:00+08:00",
    )

    assert changed == [existing_path]


def test_refresh_bond_archive_returns_empty_when_no_content_change(tmp_path: Path, monkeypatch):
    archive_root = tmp_path / "data_archive"
    existing_path = archive_root / "bond_10y" / "china_10y.json"
    existing_path.parent.mkdir(parents=True, exist_ok=True)
    existing_path.write_text(
        json.dumps(
            {
                "source": "akshare.bond_zh_us_rate",
                "series": "china_10y",
                "updated_at": "2026-05-13T15:10:00+08:00",
                "records": [{"日期": "2026-05-13", "中国国债收益率10年": 1.73}],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        rda,
        "fetch_bond_archive_records",
        lambda start_date: [{"日期": "2026-05-13", "中国国债收益率10年": 1.73}],
    )

    changed = rda.refresh_bond_dataset(
        archive_root=archive_root,
        updated_at="2026-05-13T15:10:00+08:00",
        start_date="20200101",
    )

    assert changed == []
```

- [ ] **Step 2: Run the orchestration tests to verify they fail**

Run: `python -m pytest tests/test_refresh_data_archive.py -k "refresh_index_dataset or refresh_bond_dataset" -v`

Expected: FAIL with missing function errors

- [ ] **Step 3: Implement archive refresh helpers**

```python
def load_existing_records(output_path: Path) -> List[Dict]:
    if not output_path.exists():
        return []
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    records = payload.get("records") or []
    return [row for row in records if isinstance(row, dict)]


def refresh_index_dataset(
    archive_root: Path,
    dataset_name: str,
    index_code: str,
    source_url: str,
    merge_key: str,
    updated_at: str,
) -> List[Path]:
    output_path = archive_root / dataset_name / f"{index_code}.json"
    existing_records = load_existing_records(output_path)
    incoming_records = fetch_index_archive_records(dataset_name=dataset_name, index_code=index_code, url=source_url)
    merged_records = merge_records_by_key(existing_records, incoming_records, key=merge_key)
    changed = write_archive_file(
        output_path=output_path,
        source=source_url,
        identity={"index_code": index_code},
        records=merged_records,
        updated_at=updated_at,
    )
    return [output_path] if changed else []


def refresh_bond_dataset(archive_root: Path, updated_at: str, start_date: str) -> List[Path]:
    output_path = archive_root / "bond_10y" / "china_10y.json"
    existing_records = load_existing_records(output_path)
    incoming_records = fetch_bond_archive_records(start_date=start_date)
    merged_records = merge_records_by_key(existing_records, incoming_records, key="日期")
    changed = write_archive_file(
        output_path=output_path,
        source="akshare.bond_zh_us_rate",
        identity={"series": "china_10y"},
        records=merged_records,
        updated_at=updated_at,
    )
    return [output_path] if changed else []
```

- [ ] **Step 4: Run the orchestration tests to verify they pass**

Run: `python -m pytest tests/test_refresh_data_archive.py -k "refresh_index_dataset or refresh_bond_dataset" -v`

Expected: PASS for both dataset refresh helpers

- [ ] **Step 5: Commit**

```bash
git add refresh_data_archive.py tests/test_refresh_data_archive.py
git commit -m "feat: add archive refresh orchestration"
```

## Task 6: Implement the archive script main flow and CLI behavior

**Files:**
- Modify: `refresh_data_archive.py`
- Modify: `tests/test_refresh_data_archive.py`

- [ ] **Step 1: Write failing tests for `main()` success and script-level failure behavior**

```python
def test_main_returns_zero_when_any_archive_work_succeeds(monkeypatch, tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
targets:
  - name: valuation-a
    type: valuation
    code: "930955"
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(rda, "ARCHIVE_ROOT", tmp_path / "data_archive")
    monkeypatch.setattr(rda, "now_iso", lambda: "2026-05-13T15:10:00+08:00")
    monkeypatch.setattr(rda, "build_index_eod_price_url", lambda code: f"https://example.com/eod/{code}.json")
    monkeypatch.setattr(rda, "build_index_dividend_yield_url", lambda code: f"https://example.com/div/{code}.json")
    monkeypatch.setattr(rda, "build_index_valuation_percentile_url", lambda code: f"https://example.com/val/{code}.json")
    monkeypatch.setattr(rda, "refresh_index_dataset", lambda **kwargs: [tmp_path / "changed.json"])
    monkeypatch.setattr(rda, "refresh_bond_dataset", lambda **kwargs: [])

    result = rda.main(["--config", str(config_path)])

    assert result == 0


def test_main_returns_one_when_config_parse_fails(monkeypatch):
    monkeypatch.setattr(rda, "load_config", lambda path: (_ for _ in ()).throw(ValueError("bad config")))

    result = rda.main(["--config", "broken.yaml"])

    assert result == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_refresh_data_archive.py -k "test_main_returns_zero or test_main_returns_one" -v`

Expected: FAIL because `main` and its helpers are incomplete

- [ ] **Step 3: Implement CLI parsing and top-level orchestration**

```python
import argparse
from datetime import datetime, timedelta
from pathlib import Path

from monitor_drawdown import BEIJING_TZ


ARCHIVE_ROOT = Path("data_archive")


def now_iso() -> str:
    return datetime.now(BEIJING_TZ).replace(microsecond=0).isoformat()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Refresh local history archives for monitor_drawdown")
    parser.add_argument("--config", default="config.yaml")
    return parser


def main(argv: List[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        targets = load_config(args.config)
        index_codes = resolve_archive_index_codes(targets)
        updated_at = now_iso()
        changed_paths: List[Path] = []

        for index_code in index_codes:
            changed_paths.extend(
                refresh_index_dataset(
                    archive_root=ARCHIVE_ROOT,
                    dataset_name="index_eod",
                    index_code=index_code,
                    source_url=build_index_eod_price_url(index_code),
                    merge_key="trdDt",
                    updated_at=updated_at,
                )
            )
            changed_paths.extend(
                refresh_index_dataset(
                    archive_root=ARCHIVE_ROOT,
                    dataset_name="index_dividend_ratio",
                    index_code=index_code,
                    source_url=build_index_dividend_yield_url(index_code),
                    merge_key="trdDt",
                    updated_at=updated_at,
                )
            )
            changed_paths.extend(
                refresh_index_dataset(
                    archive_root=ARCHIVE_ROOT,
                    dataset_name="index_valuation_percentile",
                    index_code=index_code,
                    source_url=build_index_valuation_percentile_url(index_code),
                    merge_key="trdDt",
                    updated_at=updated_at,
                )
            )

        start_date = (datetime.now(BEIJING_TZ) - timedelta(days=365 * 11)).strftime("%Y%m%d")
        changed_paths.extend(
            refresh_bond_dataset(
                archive_root=ARCHIVE_ROOT,
                updated_at=updated_at,
                start_date=start_date,
            )
        )
        return 0
    except Exception as exc:
        print(f"[ERROR] 数据归档失败: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_refresh_data_archive.py -k "test_main_returns_zero or test_main_returns_one" -v`

Expected: PASS for both CLI behavior tests

- [ ] **Step 5: Run the full archive test file**

Run: `python -m pytest tests/test_refresh_data_archive.py -v`

Expected: PASS for all archive tests added so far

- [ ] **Step 6: Commit**

```bash
git add refresh_data_archive.py tests/test_refresh_data_archive.py
git commit -m "feat: add archive refresh script"
```

## Task 7: Add the GitHub Actions archival workflow

**Files:**
- Create: `.github/workflows/refresh_data_archive.yml`

- [ ] **Step 1: Write the new workflow file**

```yaml
name: Refresh Data Archive

on:
  schedule:
    - cron: "17 7 * * 1-5"
  workflow_dispatch:

permissions:
  contents: write

jobs:
  refresh:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.10"

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install akshare pandas requests pyyaml

      - name: Refresh archive
        run: python refresh_data_archive.py

      - name: Commit and push if changed
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add data_archive/
          if git diff --cached --quiet; then
            echo "archive unchanged, skip commit"
          else
            git commit -m "chore: refresh data archive"
            git push
          fi
```

- [ ] **Step 2: Validate the workflow YAML locally**

Run: `Get-Content .github\\workflows\\refresh_data_archive.yml`

Expected: workflow includes `contents: write`, `workflow_dispatch`, and conditional commit logic

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/refresh_data_archive.yml
git commit -m "ci: add data archive workflow"
```

## Task 8: Track the archive output and document the feature

**Files:**
- Modify: `.gitignore`
- Modify: `README.md`

- [ ] **Step 1: Update `.gitignore` to keep archive output tracked**

```gitignore
# Archived repository data
!data_archive/
!data_archive/**
```

Add the lines near the existing cache/output rules, without changing current ignored runtime cache directories such as `.email_chart_cache/`, `datacache/`, and `.pytest_cache/`.

- [ ] **Step 2: Document the new archival behavior in `README.md`**

```md
## Historical Archive

The repository includes a separate archival workflow for slow-changing historical datasets used by the monitor:

- index EOD history
- index dividend ratio history
- index valuation percentile history
- China 10Y government bond history

Archive scope is derived from `config.yaml`, output is written under `data_archive/`, and `.github/workflows/refresh_data_archive.yml` commits changes only when archive files change.

Run locally:

```powershell
python .\refresh_data_archive.py
```
```

- [ ] **Step 3: Review the docs diff for scope accuracy**

Run: `git diff -- .gitignore README.md`

Expected: docs mention archive scope, output path, and local command only; no monitor workflow behavior regressions

- [ ] **Step 4: Commit**

```bash
git add .gitignore README.md
git commit -m "docs: document data archive workflow"
```

## Task 9: Verify end-to-end behavior before completion

**Files:**
- Verify: `refresh_data_archive.py`
- Verify: `tests/test_refresh_data_archive.py`
- Verify: `.github/workflows/refresh_data_archive.yml`
- Verify: `README.md`
- Verify: `.gitignore`

- [ ] **Step 1: Run the archive-focused test suite**

Run: `python -m pytest tests/test_refresh_data_archive.py -v`

Expected: PASS for all archive-specific tests

- [ ] **Step 2: Run a targeted existing regression slice**

Run: `python -m pytest tests/test_monitor_drawdown.py -k "fetch_index_dividend_yield or fetch_index_pe_history" -v`

Expected: PASS, confirming archive work did not break existing data helper behavior

- [ ] **Step 3: Run the archive script locally once**

Run: `python refresh_data_archive.py`

Expected: `[INFO]` / `[WARN]` logs and archive files written or left unchanged under `data_archive/`

- [ ] **Step 4: Re-run the archive script immediately**

Run: `python refresh_data_archive.py`

Expected: no additional content changes if upstream data is unchanged

- [ ] **Step 5: Inspect git status**

Run: `git status --short`

Expected: only intended archive files, workflow, tests, docs, and script changes are present

- [ ] **Step 6: Final commit**

```bash
git add refresh_data_archive.py tests/test_refresh_data_archive.py .github/workflows/refresh_data_archive.yml .gitignore README.md data_archive
git commit -m "feat: add historical data archive pipeline"
```

## Self-Review

### Spec Coverage Check

- Separate archive workflow: covered by Task 7
- `config.yaml`-derived scope: covered by Tasks 1 and 6
- Data layout under `data_archive/`: covered by Tasks 5, 7, and 8
- Raw-field preservation: covered by Tasks 2, 4, and 5
- Incremental merge with overwrite: covered by Task 2
- No-op behavior on unchanged content: covered by Tasks 3 and 9
- Keep monitoring separate: preserved across Tasks 6, 7, and 8

No spec gaps found.

### Placeholder Scan

- No `TBD`, `TODO`, or deferred implementation placeholders remain.
- All code steps include concrete code blocks.
- All test steps include concrete commands and expected outcomes.

### Type Consistency Check

- Archive helpers consistently use `List[Dict]` and `Path`.
- Merge keys are `trdDt` for index datasets and `日期` for bond history in all tasks.
- Main flow consistently writes to `data_archive/` and uses `refresh_index_dataset` / `refresh_bond_dataset`.

Plan is internally consistent.
