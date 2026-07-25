# Guorn Meta Archive Email Design

## Goal

Capture the full `https://guorn.com/stock/query/meta` response on each scheduled monitoring run, archive one complete JSON snapshot per data date, and append the `行业估值` table to the bottom of the `核心标的监控告警` email.

This work adds an auxiliary data module to the existing monitoring run. It does not replace the current valuation sources used by `monitor_drawdown.py`, and it does not block the main alert email when Guorn is unavailable.

## Confirmed Scope

The first implementation will:

- fetch the Guorn meta endpoint during the existing `monitor_drawdown.py` run
- save the full raw JSON payload under `data_archive/guorn_meta/YYYY-MM-DD.json`
- derive the archive filename from `data.latest_date`, normalized to `YYYY-MM-DD`
- extract the `data.pepb.industry` rows from the live response
- render the full `行业估值` table at the bottom of the HTML email
- keep sending the main email even if the Guorn fetch or render step fails

## Explicit Non-Goals

This phase will not:

- create a separate GitHub Actions workflow dedicated to Guorn capture
- replace the existing ETF.com.cn and archive-backed valuation metrics
- render other Guorn tabs such as `指数估值`, `指数景气程度`, `行业景气程度`, or `指数IC`
- backfill historical Guorn snapshots
- optimize the request down to the minimum possible header set

The initial trigger will piggyback on the existing `核心标的监控告警` run. A dedicated workflow can be added later after the data path is stable.

## Data Source Contract

The design assumes the validated response shape observed on July 25, 2026:

- top level keys: `status`, `data`
- success marker: `status == "ok"`
- archive date source: `data.latest_date`
- industry valuation rows: `data.pepb.industry`

Each `industry` row is expected to contain these fields used by the email table:

- `ticker`
- `name`
- `month_return`
- `year_return`
- `PE`
- `PEPercentile`
- `PB`
- `PBPercentile`
- `PEPB`
- `PEPBPercentile`

If any of these structural requirements are missing, the Guorn module is considered failed for that run and the main email continues without the table.

## Request Strategy

Add a small helper set inside `monitor_drawdown.py` for:

- building Guorn request headers
- fetching and validating the JSON payload
- archiving the snapshot
- extracting `行业估值` rows
- rendering the email section

The first implementation should keep the request strategy conservative:

- reuse the validated browser-like request header pattern
- keep static non-sensitive headers in code
- read sensitive cookie material from an environment variable such as `GUORN_COOKIE`

The repository must not hardcode live Guorn cookies or tokens. Local runs should use environment variables, and GitHub Actions should use repository secrets.

## Archive Layout and Idempotence

Archive root:

- `data_archive/guorn_meta/`

Per-run file layout:

- `data_archive/guorn_meta/YYYY-MM-DD.json`

Persistence rules:

1. Parse `data.latest_date` from the live payload.
2. Normalize it to `YYYY-MM-DD`.
3. Write the full response object as formatted UTF-8 JSON.

Idempotence behavior:

- if the target file does not exist, create it
- if the target file exists and the normalized JSON content is unchanged, skip rewriting and log `[INFO]`
- if the target file exists and the content differs, overwrite it and log `[WARN]`

This keeps the archive aligned to the upstream data date rather than the job execution date, which matters when the run occurs on a non-trading day or before Guorn rolls to a new market date.

## Email Rendering Shape

The new section should appear near the end of the HTML email, after the existing valuation and style content and before the footer.

Suggested section title:

- `果仁行业估值`

Suggested subtitle:

- `数据日期 YYYY-MM-DD`

The rendered table should include these columns:

1. `序号`
2. `指数代码`
3. `指数名称`
4. `近一月涨幅`
5. `近一年涨幅`
6. `PE`
7. `PE5年分位点`
8. `PB`
9. `PB5年分位点`
10. `PEXPB`
11. `PEXPB5年分位点`

Formatting rules:

- generate `序号` from the row order in `data.pepb.industry`
- render `month_return` and `year_return` as percentages with 2 decimals
- render percentile fields as `0-1` fractions converted to percentages with 2 decimals
- render `PE`, `PB`, and `PEPB` as plain numbers with concise decimal formatting
- escape text fields such as `name` and `ticker`

The first implementation will render the full industry list without truncation.

## Failure Behavior

If the Guorn module fails for any reason, `monitor_drawdown.py` should still send the main email.

Failure cases include:

- missing `GUORN_COOKIE`
- request timeout or non-200 response
- invalid JSON
- `status != "ok"`
- missing `data.latest_date`
- missing or invalid `data.pepb.industry`
- local archive write failure

Failure handling rules:

- emit a concise `[WARN]` or `[ERROR]` log line
- do not write an archive file for that run
- append a small muted notice in the email indicating that `行业估值` data was unavailable

The Guorn section is informative, not critical-path.

## Testing Strategy

Add deterministic unit tests for the new pure helpers and archive behavior.

Primary test targets:

- payload validation and latest-date extraction
- industry-row extraction
- archive path selection and idempotent write behavior
- HTML section rendering for a normal payload
- HTML fallback rendering for a failed payload

Fixtures should be local and minimal. They should not depend on live Guorn network access.

Recommended cases:

1. valid payload with two industry rows
2. payload with `status != "ok"`
3. payload missing `latest_date`
4. payload missing `pepb.industry`
5. first archive write
6. second archive write with identical content
7. second archive write with changed content
8. full email HTML containing the Guorn section
9. full email HTML containing the fallback notice

## Implementation Shape

Keep the implementation inside `monitor_drawdown.py` for now, following the repository's existing single-entrypoint pattern.

Add focused helpers with narrow responsibilities, for example:

- `build_guorn_meta_headers()`
- `fetch_guorn_meta_payload()`
- `extract_guorn_latest_date()`
- `archive_guorn_meta_snapshot()`
- `extract_guorn_industry_valuation_rows()`
- `render_guorn_industry_valuation_html()`

The main flow should:

1. attempt Guorn fetch after the existing monitoring data is assembled and before email generation
2. archive the payload when valid
3. pass either extracted rows plus date, or a failure marker, into email rendering
4. continue the existing email path regardless of the Guorn outcome

## Design Rationale

### Recommended Approach: Full Daily Snapshot Plus Runtime Table Rendering

This is preferred because it preserves the full upstream payload for future reuse while keeping the first user-visible feature limited to the `行业估值` table.

It also avoids premature schema design for long-lived derived history files.

### Rejected Approach: Store Only the Industry Table

This was rejected because it would discard the rest of the Guorn payload and make future expansion to other tabs impossible without starting a new archive history from scratch.

### Rejected Approach: Separate Workflow First

This was rejected because the user explicitly wants the first phase to run at the same time as the existing `核心标的监控告警` email, and a second workflow would add operational complexity before the data path is validated.

## Success Criteria

The design is successful when:

- each monitoring run attempts to fetch the Guorn meta payload without breaking the main alert flow
- valid responses are archived as one full JSON snapshot per Guorn data date
- the HTML email includes the `果仁行业估值` table when Guorn succeeds
- the HTML email includes a clear fallback notice when Guorn fails
- no live Guorn cookie or token is committed to the repository
