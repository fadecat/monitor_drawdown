# ETF Trend Source Inspection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone script that starts from a manually maintained target list, resolves ETF.com.cn ETF/index candidates, selects one primary instrument per target, and captures ETF.com.cn-owned K-line artifacts for later trend-metric research.

**Architecture:** Add one focused root-level script, `inspect_etf_trend_sources.py`, and keep the workflow isolated from `monitor_drawdown.py`. Reuse existing ETF.com.cn helpers where possible: ETF NAV loading from `analyze_etf_com_cn_period_returns.py` and ETF.com.cn index EOD parsing from `monitor_drawdown.py`. Persist all run artifacts under `.test_artifacts/etf_trend_sources/` and validate by running the script against real upstream data.

**Tech Stack:** Python 3.10, `requests`, `json`, `pathlib`, `re`, existing repo helpers in `analyze_etf_com_cn_period_returns.py` and `monitor_drawdown.py`

---

## File Structure

### New files

- `inspect_etf_trend_sources.py`
  - Owns the end-to-end inspection workflow.
  - Contains the default target list, ETF.com.cn search client, candidate scoring, primary resolution, ETF.com.cn K-line fetching, artifact writing, and summary generation.

- `docs/superpowers/specs/2026-06-04-etf-trend-source-inspection-design.md`
  - Already written and approved as the design source of truth.

- `docs/superpowers/plans/2026-06-04-etf-trend-source-inspection.md`
  - This implementation plan.

### Existing files to read but not modify unless needed

- `analyze_etf_com_cn_period_returns.py`
  - Reuse `load_nav_rows()` for ETF NAV history from ETF.com.cn.

- `monitor_drawdown.py`
  - Reuse `build_index_eod_price_url()`, `fetch_json_response()`, and `parse_index_eod_price_rows()` if practical for ETF.com.cn index EOD loading.

- `style_rotation_preview.py`
  - Reference the existing ETF.com.cn ETF history normalization pattern.

### No test-file additions in this phase

- This plan intentionally does not add pytest coverage because the user explicitly wants the first version to connect directly to real upstream data rather than simulated fixtures or mocked pipelines.

---

### Task 1: Scaffold the inspection script with static target configuration

**Files:**
- Create: `inspect_etf_trend_sources.py`

- [ ] **Step 1: Create the script header, imports, constants, and default target list**

Add this initial structure:

```python
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from html import unescape
from pathlib import Path
from typing import Any

import requests

import analyze_etf_com_cn_period_returns as etf_analysis
import monitor_drawdown as md


SEARCH_ALL_URL = "https://www.etf.com.cn/api/etf-api-service/search/all"
OUTPUT_ROOT = Path(".test_artifacts/etf_trend_sources")
SERIES_DIR = OUTPUT_ROOT / "series"
REQUEST_TIMEOUT = 15
LOOKBACK_DAYS = 365

DEFAULT_TARGETS: list[dict[str, Any]] = [
    {"label": "通信ETF", "search_keywords": ["通信", "通信ETF"], "kline_kind": "auto"},
    {"label": "煤炭ETF", "search_keywords": ["煤炭", "煤炭ETF"], "kline_kind": "auto"},
    {"label": "创成长", "search_keywords": ["创成长", "创业成长"], "kline_kind": "auto"},
    {"label": "纳指ETF", "search_keywords": ["纳指", "纳指ETF"], "kline_kind": "auto"},
    {"label": "创业板50", "search_keywords": ["创业板50"], "kline_kind": "auto"},
    {"label": "人工智能", "search_keywords": ["人工智能"], "kline_kind": "auto"},
    {"label": "标普500", "search_keywords": ["标普500"], "kline_kind": "auto"},
    {"label": "半导体ETF", "search_keywords": ["半导体", "半导体ETF"], "kline_kind": "auto"},
    {"label": "恒生科技", "search_keywords": ["恒生科技"], "kline_kind": "auto"},
    {"label": "沪深300", "search_keywords": ["沪深300"], "kline_kind": "auto"},
    {"label": "科创100", "search_keywords": ["科创100"], "kline_kind": "auto"},
    {"label": "科创50", "search_keywords": ["科创50"], "kline_kind": "auto"},
    {"label": "30年国债", "search_keywords": ["30年国债"], "kline_kind": "auto"},
    {"label": "银行ETF", "search_keywords": ["银行", "银行ETF"], "kline_kind": "auto"},
    {"label": "红利低波", "search_keywords": ["红利低波"], "kline_kind": "auto"},
    {"label": "恒生ETF", "search_keywords": ["恒生ETF", "恒生"], "kline_kind": "auto"},
    {"label": "有色金属", "search_keywords": ["有色金属"], "kline_kind": "auto"},
    {"label": "上证指数", "search_keywords": ["上证指数"], "kline_kind": "auto"},
    {"label": "机器人ETF", "search_keywords": ["机器人", "机器人ETF"], "kline_kind": "auto"},
    {"label": "中证1000", "search_keywords": ["中证1000"], "kline_kind": "auto"},
    {"label": "证券ETF", "search_keywords": ["证券", "证券ETF"], "kline_kind": "auto"},
    {"label": "豆粕ETF", "search_keywords": ["豆粕", "豆粕ETF"], "kline_kind": "auto"},
    {"label": "中证2000", "search_keywords": ["中证2000"], "kline_kind": "auto"},
    {"label": "黄金ETF", "search_keywords": ["黄金", "黄金ETF"], "kline_kind": "auto"},
    {"label": "光伏ETF", "search_keywords": ["光伏", "光伏ETF"], "kline_kind": "auto"},
    {"label": "酒ETF", "search_keywords": ["酒", "酒ETF"], "kline_kind": "auto"},
    {"label": "石油ETF", "search_keywords": ["石油", "石油ETF"], "kline_kind": "auto"},
    {"label": "新能源车", "search_keywords": ["新能源车"], "kline_kind": "auto"},
    {"label": "医疗ETF", "search_keywords": ["医疗", "医疗ETF"], "kline_kind": "auto"},
    {"label": "军工ETF", "search_keywords": ["军工", "军工ETF"], "kline_kind": "auto"},
]
```

- [ ] **Step 2: Add simple logging and path helpers**

Append:

```python
def log(level: str, message: str) -> None:
    print(f"[{level}] {message}")


def ensure_output_dirs() -> None:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    SERIES_DIR.mkdir(parents=True, exist_ok=True)


def today_range_strings() -> tuple[str, str]:
    end_date = datetime.today().date()
    start_date = end_date - timedelta(days=LOOKBACK_DAYS)
    return start_date.strftime("%Y%m%d"), end_date.strftime("%Y%m%d")
```

- [ ] **Step 3: Add target normalization helpers**

Append:

```python
def dedupe_keep_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def normalize_targets(raw_targets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in raw_targets:
        label = str(item.get("label") or "").strip()
        keywords = item.get("search_keywords") or []
        kline_kind = str(item.get("kline_kind") or "auto").strip() or "auto"
        if not label:
            continue
        normalized.append(
            {
                "label": label,
                "search_keywords": dedupe_keep_order([str(keyword) for keyword in keywords] or [label]),
                "kline_kind": kline_kind,
            }
        )
    return normalized
```

- [ ] **Step 4: Add JSON writer helpers**

Append:

```python
def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
```

- [ ] **Step 5: Commit**

```bash
git add inspect_etf_trend_sources.py docs/superpowers/plans/2026-06-04-etf-trend-source-inspection.md docs/superpowers/specs/2026-06-04-etf-trend-source-inspection-design.md
git commit -m "feat: scaffold etf trend source inspection script"
```

### Task 2: Implement ETF.com.cn search collection and candidate normalization

**Files:**
- Modify: `inspect_etf_trend_sources.py`

- [ ] **Step 1: Add HTML stripping and token helpers**

Append:

```python
TAG_RE = re.compile(r"<[^>]+>")
GENERIC_TOKENS = {"etf", "指数"}
THEME_TOKENS = [
    "煤炭", "通信", "半导体", "恒生", "黄金", "军工", "医疗", "石油",
    "银行", "证券", "光伏", "酒", "机器人", "人工智能", "新能源车",
    "沪深300", "中证1000", "中证2000", "科创50", "科创100",
    "创业板50", "纳指", "标普500", "30年国债", "有色金属", "红利低波",
]


def strip_html(text: Any) -> str:
    return unescape(TAG_RE.sub("", str(text or ""))).strip()


def extract_theme_hits(*parts: str) -> list[str]:
    haystack = " ".join(part for part in parts if part)
    return [token for token in THEME_TOKENS if token in haystack]
```

- [ ] **Step 2: Add ETF.com.cn search client**

Append:

```python
def search_all(keyword: str) -> dict[str, Any]:
    response = requests.post(
        SEARCH_ALL_URL,
        json={"keyword": keyword, "page": 1, "pageSize": 10},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError(f"unexpected search payload type: {type(payload).__name__}")
    return payload
```

- [ ] **Step 3: Add candidate normalization for ETF and index rows**

Append:

```python
def normalize_etf_candidate(row: dict[str, Any], keyword: str) -> dict[str, Any]:
    return {
        "kind": "etf",
        "keyword": keyword,
        "code": str(row.get("trdCode") or row.get("originalTrdCode") or "").strip(),
        "original_code": str(row.get("originalTrdCode") or "").strip(),
        "name": strip_html(row.get("fundSht")),
        "raw_name": str(row.get("fundSht") or ""),
        "fund_name": strip_html(row.get("fundName")),
        "manager": strip_html(row.get("manager")),
        "theme_hits": extract_theme_hits(strip_html(row.get("fundSht")), strip_html(row.get("fundName"))),
    }


def normalize_index_candidate(row: dict[str, Any], keyword: str) -> dict[str, Any]:
    return {
        "kind": "index",
        "keyword": keyword,
        "code": str(row.get("originalTrdCode") or row.get("trdCode") or "").strip(),
        "display_code": str(row.get("trdCode") or "").strip(),
        "name": strip_html(row.get("indexSht")),
        "raw_name": str(row.get("indexSht") or ""),
        "index_name": strip_html(row.get("indexName")),
        "theme_hits": extract_theme_hits(strip_html(row.get("indexSht")), strip_html(row.get("indexName"))),
    }
```

- [ ] **Step 4: Add one-keyword collection helper**

Append:

```python
def collect_candidates_for_keyword(keyword: str) -> dict[str, Any]:
    payload = search_all(keyword)
    data = payload.get("data") or {}
    etf_rows = data.get("etfFundList", {}).get("data") or []
    index_rows = data.get("indexList", {}).get("data") or []
    out_rows = data.get("outIndexFundList", {}).get("data") or []
    return {
        "keyword": keyword,
        "success": bool(payload.get("success")),
        "message": str(payload.get("message") or ""),
        "etf_candidates": [normalize_etf_candidate(row, keyword) for row in etf_rows if isinstance(row, dict)],
        "index_candidates": [normalize_index_candidate(row, keyword) for row in index_rows if isinstance(row, dict)],
        "out_index_debug": [
            {
                "code": str(row.get("trdCode") or row.get("originalTrdCode") or "").strip(),
                "name": strip_html(row.get("fundSht")),
            }
            for row in out_rows
            if isinstance(row, dict)
        ],
    }
```

- [ ] **Step 5: Commit**

```bash
git add inspect_etf_trend_sources.py
git commit -m "feat: collect etf.com.cn trend search candidates"
```

### Task 3: Implement candidate scoring and primary resolution

**Files:**
- Modify: `inspect_etf_trend_sources.py`

- [ ] **Step 1: Add scoring helpers**

Append:

```python
def score_candidate(candidate: dict[str, Any], label: str, search_keywords: list[str]) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    name = str(candidate.get("name") or "")
    secondary_name = str(candidate.get("fund_name") or candidate.get("index_name") or "")
    haystack = " ".join([name, secondary_name])

    if name == label:
        score += 100
        reasons.append("exact_label_match")

    for keyword in search_keywords:
        if name == keyword:
            score += 90
            reasons.append(f"exact_keyword_match:{keyword}")
        elif keyword in haystack and keyword not in {"ETF", "指数"}:
            score += 30
            reasons.append(f"keyword_contains:{keyword}")

    theme_hits = candidate.get("theme_hits") or []
    if theme_hits:
        score += 20 * len(theme_hits)
        reasons.append("theme_hits:" + ",".join(theme_hits))

    if "ETF" in label and candidate.get("kind") == "etf":
        score += 15
        reasons.append("etf_label_bonus")
    if "ETF" not in label and candidate.get("kind") == "index":
        score += 15
        reasons.append("index_label_bonus")

    if "ETF" in name and not theme_hits and all(keyword not in haystack for keyword in search_keywords if keyword not in {"ETF", "指数"}):
        score -= 40
        reasons.append("generic_etf_penalty")

    return score, reasons
```

- [ ] **Step 2: Add credibility and best-candidate selectors**

Append:

```python
def is_credible(score: int, reasons: list[str]) -> bool:
    return any(reason.startswith("exact_") for reason in reasons) or any(reason.startswith("theme_hits:") for reason in reasons)


def pick_best_candidate(candidates: list[dict[str, Any]], label: str, search_keywords: list[str]) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    for candidate in candidates:
        score, reasons = score_candidate(candidate, label, search_keywords)
        enriched = dict(candidate)
        enriched["score"] = score
        enriched["score_reasons"] = reasons
        enriched["credible"] = is_credible(score, reasons)
        if best is None or enriched["score"] > best["score"]:
            best = enriched
    return best
```

- [ ] **Step 3: Add target resolution workflow**

Append:

```python
def resolve_target(target: dict[str, Any]) -> dict[str, Any]:
    label = target["label"]
    search_keywords = target["search_keywords"]
    search_attempts: list[dict[str, Any]] = []
    best_etf: dict[str, Any] | None = None
    best_index: dict[str, Any] | None = None
    failure_message = ""

    for keyword in search_keywords:
        log("INFO", f"search keyword={keyword}")
        try:
            attempt = collect_candidates_for_keyword(keyword)
            search_attempts.append(attempt)
            current_best_etf = pick_best_candidate(attempt["etf_candidates"], label, search_keywords)
            current_best_index = pick_best_candidate(attempt["index_candidates"], label, search_keywords)
            if current_best_etf and (best_etf is None or current_best_etf["score"] > best_etf["score"]):
                best_etf = current_best_etf
            if current_best_index and (best_index is None or current_best_index["score"] > best_index["score"]):
                best_index = current_best_index
            if (best_etf and best_etf["credible"]) or (best_index and best_index["credible"]):
                break
        except Exception as exc:
            failure_message = str(exc)
            search_attempts.append({"keyword": keyword, "error": str(exc)})

    selected_primary = select_primary(label, best_etf, best_index)
    status = "ok" if selected_primary else ("search_failed" if not search_attempts else "unresolved")
    if status == "search_failed" and failure_message:
        log("ERROR", f"search failed label={label} reason={failure_message}")
    if status == "unresolved":
        log("WARN", f"unresolved label={label}")
    return {
        "label": label,
        "search_keywords": search_keywords,
        "search_attempts": search_attempts,
        "etf_candidate": best_etf,
        "index_candidate": best_index,
        "selected_primary": selected_primary,
        "status": status,
    }
```

- [ ] **Step 4: Add primary selector**

Append:

```python
def select_primary(label: str, etf_candidate: dict[str, Any] | None, index_candidate: dict[str, Any] | None) -> dict[str, Any] | None:
    prefer_etf = "ETF" in label
    first = etf_candidate if prefer_etf else index_candidate
    second = index_candidate if prefer_etf else etf_candidate

    if first and first.get("credible"):
        return {
            "kind": first["kind"],
            "code": first["code"],
            "name": first["name"],
            "reason": "preferred_kind_candidate",
            "score": first["score"],
        }
    if second and second.get("credible"):
        return {
            "kind": second["kind"],
            "code": second["code"],
            "name": second["name"],
            "reason": "fallback_kind_candidate",
            "score": second["score"],
        }
    return None
```

- [ ] **Step 5: Commit**

```bash
git add inspect_etf_trend_sources.py
git commit -m "feat: resolve primary ETF or index candidates"
```

### Task 4: Implement ETF.com.cn K-line fetching and series persistence

**Files:**
- Modify: `inspect_etf_trend_sources.py`

- [ ] **Step 1: Add ETF and index loaders using ETF.com.cn-owned sources**

Append:

```python
def normalize_series_frame(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen_dates: set[str] = set()
    for row in records:
        date_text = str(row.get("date") or "").strip()
        close_value = row.get("close")
        if not date_text or close_value is None:
            continue
        if date_text in seen_dates:
            result = [existing for existing in result if existing["date"] != date_text]
        seen_dates.add(date_text)
        result.append({"date": date_text, "close": float(close_value)})
    result.sort(key=lambda item: item["date"])
    return result


def load_etf_series(code: str) -> list[dict[str, Any]]:
    rows = etf_analysis.load_nav_rows(code)
    return normalize_series_frame(
        [
            {"date": str(row.get("trdDt") or "").strip(), "close": row.get("adjUnitNav")}
            for row in rows
            if isinstance(row, dict)
        ]
    )


def load_index_series(code: str) -> list[dict[str, Any]]:
    source_url = md.build_index_eod_price_url(code)
    rows = md.fetch_json_response("index_eod_price", source_url)
    frame = md.parse_index_eod_price_rows(rows)
    if frame.empty:
        return []
    records = frame.to_dict(orient="records")
    return normalize_series_frame(
        [
            {
                "date": record["date"].strftime("%Y-%m-%d"),
                "close": record["close"],
            }
            for record in records
        ]
    )
```

- [ ] **Step 2: Add selected-primary K-line fetcher**

Append:

```python
def fetch_selected_series(selected_primary: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    kind = selected_primary["kind"]
    code = selected_primary["code"]
    if kind == "etf":
        series = load_etf_series(code)
    elif kind == "index":
        series = load_index_series(code)
    else:
        raise ValueError(f"unsupported kind: {kind}")

    if not series:
        raise RuntimeError(f"empty ETF.com.cn series for {kind}:{code}")

    summary = {
        "status": "ok",
        "selected_kind": kind,
        "selected_code": code,
        "rows": len(series),
        "date_start": series[0]["date"],
        "date_end": series[-1]["date"],
        "latest_close": series[-1]["close"],
    }
    return series, summary
```

- [ ] **Step 3: Add per-target K-line materialization**

Append:

```python
def materialize_kline(result: dict[str, Any]) -> dict[str, Any]:
    selected_primary = result.get("selected_primary")
    if not selected_primary:
        return {
            "label": result["label"],
            "status": result["status"],
            "selected_primary": None,
        }

    try:
        series, summary = fetch_selected_series(selected_primary)
        filename = f"{selected_primary['kind']}_{selected_primary['code']}.json"
        write_json(SERIES_DIR / filename, series)
        return {
            "label": result["label"],
            "status": "ok",
            "selected_primary": selected_primary,
            "kline": summary,
            "series_file": str((SERIES_DIR / filename).as_posix()),
        }
    except Exception as exc:
        log("ERROR", f"kline failed label={result['label']} reason={exc}")
        return {
            "label": result["label"],
            "status": "kline_failed",
            "selected_primary": selected_primary,
            "error": str(exc),
        }
```

- [ ] **Step 4: Commit**

```bash
git add inspect_etf_trend_sources.py
git commit -m "feat: fetch etf.com.cn kline series for resolved targets"
```

### Task 5: Implement artifact writing, summary generation, and script entrypoint

**Files:**
- Modify: `inspect_etf_trend_sources.py`

- [ ] **Step 1: Add summary generator**

Append:

```python
def build_summary(resolved: list[dict[str, Any]], kline_results: list[dict[str, Any]]) -> str:
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
    for item in resolved:
        label = item["label"]
        kline = kline_by_label.get(label, {})
        selected = item.get("selected_primary")
        selected_text = f"{selected['kind']}:{selected['code']} {selected['name']}" if selected else "none"
        lines.append(f"- {label}: resolve={item['status']} kline={kline.get('status', 'unknown')} selected={selected_text}")

    return "\n".join(lines) + "\n"
```

- [ ] **Step 2: Add run orchestration**

Append:

```python
def run() -> None:
    ensure_output_dirs()
    targets = normalize_targets(DEFAULT_TARGETS)
    write_json(OUTPUT_ROOT / "targets.json", targets)

    resolved_results = [resolve_target(target) for target in targets]
    candidate_payload = [
        {
            "label": item["label"],
            "search_keywords": item["search_keywords"],
            "search_attempts": item["search_attempts"],
        }
        for item in resolved_results
    ]
    write_json(OUTPUT_ROOT / "candidate_matches.json", candidate_payload)

    resolved_payload = [
        {
            "label": item["label"],
            "status": item["status"],
            "etf_candidate": item["etf_candidate"],
            "index_candidate": item["index_candidate"],
            "selected_primary": item["selected_primary"],
        }
        for item in resolved_results
    ]
    write_json(OUTPUT_ROOT / "resolved_instruments.json", resolved_payload)

    kline_results = [materialize_kline(item) for item in resolved_results]
    write_json(OUTPUT_ROOT / "kline_samples.json", kline_results)

    summary_text = build_summary(resolved_results, kline_results)
    (OUTPUT_ROOT / "summary.md").write_text(summary_text, encoding="utf-8")
    log("INFO", f"artifacts written to {OUTPUT_ROOT}")


if __name__ == "__main__":
    run()
```

- [ ] **Step 3: Run the script against real data**

Run:

```bash
python inspect_etf_trend_sources.py
```

Expected:

- `[INFO]` search logs for multiple keywords
- possible `[WARN]` unresolved lines for ambiguous names
- possible `[ERROR]` lines when ETF.com.cn K-line endpoints are unavailable for some resolved targets
- final `[INFO] artifacts written to .test_artifacts/etf_trend_sources`

- [ ] **Step 4: Inspect generated artifact files**

Run:

```bash
Get-ChildItem -Recurse .test_artifacts\etf_trend_sources
```

Expected:

- `targets.json`
- `candidate_matches.json`
- `resolved_instruments.json`
- `kline_samples.json`
- `summary.md`
- one or more files under `.test_artifacts\etf_trend_sources\series\`

- [ ] **Step 5: Commit**

```bash
git add inspect_etf_trend_sources.py .test_artifacts/etf_trend_sources
git commit -m "feat: add etf trend source inspection workflow"
```

## Self-Review

### Spec coverage

- manual target list: covered in Task 1
- ETF.com.cn search resolution: covered in Tasks 2 and 3
- ETF and index dual-candidate retention: covered in Task 3
- ETF.com.cn-only K-line fetching: covered in Task 4
- artifact persistence and summary: covered in Task 5

No design requirement is left without a task.

### Placeholder scan

- No `TBD`, `TODO`, or deferred implementation notes remain in the actionable tasks.
- Every code-writing step includes the exact code to add.
- Every run step includes an exact command and expected outcome.

### Type consistency

- `resolve_target()` returns `status`, `etf_candidate`, `index_candidate`, `selected_primary`, and `search_attempts`, which are the same names used later in artifact writing.
- `selected_primary` consistently uses `kind`, `code`, `name`, `reason`, and `score`.
- K-line summaries consistently use `status`, `selected_kind`, `selected_code`, `rows`, `date_start`, `date_end`, and `latest_close`.
