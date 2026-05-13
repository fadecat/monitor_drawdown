# Data Archive Design

Date: 2026-05-13

## Goal

Add a separate archival pipeline for slow-changing historical data used by the monitor project, without coupling archival writes to the monitoring workflow.

The archive should:

- derive its target scope from `config.yaml`
- persist incremental history into versioned files in the repository
- auto-commit only when archived data changes
- keep monitoring and archival as separate workflows

## Non-Goals

- Do not change the purpose of `monitor_drawdown.py` from stateless monitoring and notification.
- Do not persist webhook payloads, email output, runtime alert state, login cookies, charts, or preview artifacts.
- Do not build a general-purpose market data warehouse.
- Do not delete archived files automatically when a target is removed from `config.yaml`.

## User Decisions

The design is based on these confirmed decisions:

- Archive scope comes only from `config.yaml`.
- Files are organized by data type and index code, not by date partitions.
- Archived content should preserve upstream raw fields as much as practical.
- Archive refresh runs once per trading day after close.
- Removing a target from `config.yaml` does not delete existing archive files.

## Why Separate Monitoring And Archival

The current monitoring workflow in `.github/workflows/monitor.yml` runs multiple times per trading day and is optimized for fetching current data, computing drawdown, and sending notifications.

That workflow is a poor place for repository persistence because:

- it would create excessive commit noise
- archival failures would become coupled to alerting behavior
- data persistence has different runtime and reliability concerns from notification delivery

A separate archival workflow provides cleaner failure isolation and a more stable repository history.

## Archive Scope

First version archives only slow-changing historical datasets that are already consumed by the project:

1. Index EOD history from the eFunds CDN endpoint.
2. Index dividend ratio history from the eFunds CDN endpoint.
3. Index valuation percentile history from the eFunds CDN endpoint.
4. China 10Y government bond history from `ak.bond_zh_us_rate`.

The scope is computed from the current `config.yaml` targets:

- read `targets`
- resolve index code from `tracking_index_code`, then `index_code`, then `code` for index targets
- deduplicate codes while preserving stable order

Only targets that resolve to an index code are included in the index archive set.

## File Layout

Archive files live under a new repository directory:

```text
data_archive/
  bond_10y/
    china_10y.json
  index_eod/
    000300.json
    930955.json
  index_dividend_ratio/
    000300.json
    930955.json
  index_valuation_percentile/
    000300.json
    930955.json
```

This layout is chosen because it:

- keeps diffs localized to the changed dataset
- avoids large monolithic files
- makes direct inspection and backfilling simple
- maps naturally onto auto-commit behavior

## File Format

Each archive file uses a stable JSON envelope with upstream-like records:

```json
{
  "source": "https://cdn.efunds.com.cn/etf-net/index_eod_price_930955.json",
  "index_code": "930955",
  "updated_at": "2026-05-13T15:10:00+08:00",
  "records": [
    {
      "...": "..."
    }
  ]
}
```

For the bond archive:

```json
{
  "source": "akshare.bond_zh_us_rate",
  "series": "china_10y",
  "updated_at": "2026-05-13T15:10:00+08:00",
  "records": [
    {
      "...": "..."
    }
  ]
}
```

### Format Rules

- Preserve upstream field names and raw record structure where practical.
- Add only minimal envelope metadata needed for provenance and refresh tracking.
- Sort records ascending by date key before writing.
- Use stable JSON formatting with `ensure_ascii=False` and fixed indentation.
- Normalize date-like values only as needed for merge keys and stable serialization.

## Merge Strategy

The archival script must be incremental and idempotent.

### Merge Keys

- Index EOD: `trdDt`
- Index dividend ratio: `trdDt`
- Index valuation percentile: `trdDt`
- China 10Y bond history: `日期`

### Merge Rules

1. Load existing archive file if present.
2. Load latest upstream records.
3. Merge by the dataset key.
4. If the same key exists in both old and new data, replace the old record with the new full record.
5. Sort by key ascending.
6. Write only if the final serialized content differs from the file on disk.

This avoids duplicate rows, stabilizes diffs, and allows same-day corrections from upstream data.

## Script Responsibilities

Add a new script: `refresh_data_archive.py`.

Its responsibilities are:

1. Read `config.yaml`.
2. Resolve and deduplicate archive target index codes.
3. Fetch each dataset from the appropriate upstream source.
4. Merge fetched data into the corresponding local archive file.
5. Emit concise `[INFO]` and `[WARN]` logs.
6. Exit non-zero only for script-level failures that should fail CI.

The script must not:

- send alerts
- send email
- read or write webhook state
- depend on `main()` from `monitor_drawdown.py`

## Function Reuse And Boundaries

The implementation should reuse stable, side-effect-free helpers from `monitor_drawdown.py` where possible:

- `load_config`
- `extract_index_digits`
- `dedupe_keep_order`
- `build_index_detail_url`
- `build_index_dividend_yield_url`
- `build_index_eod_price_url`
- `build_index_valuation_percentile_url`
- `fetch_json_response`
- the target index code resolution logic currently embodied in `resolve_target_index_code`

The archive script should not reuse normalized-output functions when they would discard raw upstream fields.

Specifically:

- do not use `fetch_cn_10y_bond_history()` for archive persistence because it converts the upstream DataFrame into a reduced `date/yield_pct` schema
- instead call `ak.bond_zh_us_rate()` in the archive path and serialize the original columns

If helper extraction is needed, move shared pure helpers into a small utility module rather than importing monitoring-side effects.

## Workflow Design

Add a new workflow file: `.github/workflows/refresh_data_archive.yml`.

### Trigger

- one scheduled run each trading day after close
- manual `workflow_dispatch`

### Permissions

- `contents: write`

### Steps

1. Checkout repository.
2. Setup Python.
3. Install minimal dependencies needed by the archive script.
4. Run `python refresh_data_archive.py`.
5. `git add data_archive/`
6. If no staged diff exists, log and exit successfully.
7. Otherwise commit and push.

### Commit Policy

Use a stable commit message:

`chore: refresh data archive`

The first version should prefer simplicity over dynamic commit message generation.

## Error Handling

The archival pipeline should continue past partial dataset failures when possible.

### Per-target Or Per-dataset Failures

- Log `[WARN]`
- Continue processing remaining archive files

Examples:

- one index valuation endpoint returns 502
- one dividend endpoint returns malformed data
- one target has an invalid code

### Script-level Failures

Fail the workflow only when the script cannot perform its core job, such as:

- `config.yaml` cannot be read or parsed
- all configured archive targets fail and no archive work is completed
- local file write fails
- dependency/runtime initialization fails

This keeps the archive workflow useful even when a single upstream endpoint is temporarily unstable.

## Testing Strategy

Add targeted regression tests for archive-specific business logic.

Minimum coverage for the first version:

1. Resolve archive targets from `config.yaml` correctly.
2. Deduplicate repeated index codes while preserving order.
3. Merge records by key with overwrite-on-conflict semantics.
4. Preserve upstream raw fields during merge.
5. Sort merged output deterministically.
6. Detect unchanged output and skip file rewrites.
7. Serialize bond history using the upstream-style column set rather than the reduced monitoring schema.

Tests must avoid live network calls and should use deterministic sample payloads.

## Open Implementation Decisions Already Resolved

The following ambiguities were reviewed and intentionally resolved in this spec:

- Archive scope is tied only to `config.yaml`, not to a separate index universe.
- Historical archive files are append/merge targets, not date-stamped snapshots.
- Archive files remain after targets are removed from config.
- Monitoring remains stateless with respect to repository persistence.

## Rollout Plan

Implementation should proceed in this order:

1. Add archive spec and tests for merge/target resolution.
2. Implement `refresh_data_archive.py`.
3. Add `data_archive/` layout handling.
4. Add `refresh_data_archive.yml`.
5. Verify no-op runs produce no staged diff.
6. Verify change runs stage only the intended archive files.

## Risks

- Upstream schemas may drift, especially JSON field sets from eFunds or tabular columns from AkShare.
- Importing helpers directly from `monitor_drawdown.py` may pull in more dependencies than desired.
- Raw-field preservation increases file size and diff size relative to normalized storage.

These risks are acceptable for v1 because the archive scope is narrow and the business value is in preserving source fidelity.
