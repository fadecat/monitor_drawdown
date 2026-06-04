# ETF Trend Source Inspection Design

## Goal

Add a repeatable local inspection tool that starts from a manually maintained target list, resolves each target to ETF and index candidates through ETF.com.cn keyword search, selects one primary instrument by explicit rules, and captures real K-line data from ETF.com.cn-owned data sources for downstream trend research.

This phase is only for data-source discovery and pipeline stabilization. It does not attempt to reproduce the screenshot's `偏离率`、`综合趋势`、`转变日` calculations yet.

## Confirmed Scope

The tool will:

1. use a script-internal default target list derived from the screenshot
2. search ETF.com.cn by configured keywords for each target
3. retain both ETF and index candidate lines during resolution
4. select one primary instrument per target by explicit rules
5. fetch real K-line data for the selected primary instrument from ETF.com.cn sources
6. save structured local artifacts for later metric research

The default target list for the first version is:

- `通信ETF`
- `煤炭ETF`
- `创成长`
- `纳指ETF`
- `创业板50`
- `人工智能`
- `标普500`
- `半导体ETF`
- `恒生科技`
- `沪深300`
- `科创100`
- `科创50`
- `30年国债`
- `银行ETF`
- `红利低波`
- `恒生ETF`
- `有色金属`
- `上证指数`
- `机器人ETF`
- `中证1000`
- `证券ETF`
- `豆粕ETF`
- `中证2000`
- `黄金ETF`
- `光伏ETF`
- `酒ETF`
- `石油ETF`
- `新能源车`
- `医疗ETF`
- `军工ETF`

## Explicit Non-Goals

This phase will not:

- perform OCR or parse images
- build a browser page or visualization UI
- integrate the new workflow into `monitor_drawdown.py`
- compute `偏离率`
- compute `综合趋势`
- compute `转变日`
- add simulated or mocked data flows
- add deterministic pytest coverage for live upstream responses

## Implementation Shape

Add one standalone script at the repository root:

- `inspect_etf_trend_sources.py`

This follows the repository's existing pattern of using focused root-level scripts for exploratory or operational tasks without forcing the logic into the main monitoring entrypoint.

The script will contain an internal default configuration list. Each item should use a structured shape rather than a bare string:

```python
{
    "label": "煤炭ETF",
    "search_keywords": ["煤炭", "煤炭ETF"],
    "kline_kind": "auto",
}
```

Field meanings:

- `label`: display label preserved from the source list
- `search_keywords`: ordered keyword attempts used against ETF.com.cn
- `kline_kind`: first-version fixed to `auto`

## ETF.com.cn Search Behavior Assumption

The design assumes the previously verified ETF.com.cn search endpoints remain usable:

- `POST /api/etf-api-service/search/all`
- `POST /api/etf-api-service/search/quick`

The first version will use `search/all` for resolution work.

The design also assumes ETF.com.cn search is broad and can over-match generic terms such as `ETF`. Because of that, search and resolution are intentionally separated into two steps instead of trusting the first returned row.

## Resolution Pipeline

Each target should pass through these stages:

1. normalize the configured target entry
2. try `search_keywords` in order
3. collect ETF.com.cn candidate data
4. score ETF candidates and index candidates separately
5. retain the best ETF candidate and best index candidate
6. choose one `selected_primary` instrument
7. fetch K-line data for the selected primary instrument

If one keyword yields sufficiently strong candidates, the script stops trying later keywords for that target. If no keyword yields a credible candidate, the target is marked `unresolved`.

## Candidate Pools

For the first version:

- `etfFundList` is treated as the primary ETF candidate pool
- `indexList` is treated as the primary index candidate pool
- `outIndexFundList` is captured only for debugging and analysis

`outIndexFundList` must not be used to select the first-version primary instrument.

## Candidate Normalization

ETF.com.cn may return highlighted HTML in names. Before scoring:

- strip highlight tags such as `<span ...>`
- trim whitespace
- preserve the original raw returned value in artifacts
- preserve normalized name and code fields used by the resolver

This keeps downstream analysis reproducible while avoiding HTML-driven false matches.

## Candidate Scoring Rules

Scoring must stay simple and explainable. The first version should prefer rule-based ranking, not hidden heuristics.

Recommended scoring signals:

1. exact match between candidate short name and `label`
2. exact match between candidate short name and one configured `search_keyword`
3. presence of non-generic theme tokens such as `煤炭`、`通信`、`军工`、`黄金`
4. penalty when a match only relies on generic terms such as `ETF`
5. type preference bonus:
   - ETF-side boost when `label` contains `ETF`
   - index-side boost when `label` does not contain `ETF`

The score does not need to be mathematically sophisticated. It only needs to be stable and auditable.

## Final Selection Rules

For every target, keep three outputs:

- `etf_candidate`
- `index_candidate`
- `selected_primary`

Primary selection rules are fixed for the first version:

- if `label` contains `ETF`, prefer the ETF candidate
- if `label` does not contain `ETF`, prefer the index candidate
- if the preferred side is missing or not credible, fall back to the other side
- if both sides are not credible, mark the target as `unresolved`

Credibility is defined by explicit rule hits, not by blind first-result acceptance. A candidate is considered credible when it has either:

- an exact name or exact keyword match
- or at least one non-generic theme-token match

Otherwise it should not be auto-selected.

## K-Line Fetching

The first version should treat ETF.com.cn as the canonical time-series source for all successfully resolved targets.

Because targets are discovered through ETF.com.cn search, the design assumes that successfully mapped ETF and index instruments should also be fetchable through ETF.com.cn-owned data endpoints.

### ETF Series

When `selected_primary.kind == "etf"`:

- fetch `https://cdn.efunds.com.cn/etf-net/etf_fund_nav_{code}.json`
- normalize `trdDt -> date`
- normalize `adjUnitNav -> close`

The repository already contains ETF.com.cn NAV-loading logic in `analyze_etf_com_cn_period_returns.py`, and that logic should be reused rather than replaced.

### Index Series

When `selected_primary.kind == "index"`:

- fetch `https://cdn.efunds.com.cn/etf-net/index_eod_price_{index_code}.json`
- normalize `trdDt -> date`
- normalize `pxClose -> close`

The repository already contains ETF.com.cn index EOD parsing helpers in `monitor_drawdown.py`, and those ETF.com.cn-specific helpers should be reused where practical.

### No Cross-Source Fallback In First Version

The first version should not fall back to TickFlow or AkShare inside this inspection script.

If ETF.com.cn search can resolve the target but the corresponding ETF.com.cn K-line endpoint still fails, the result should be recorded as `kline_failed` rather than silently switching to another market-data provider.

That constraint is intentional. The purpose of this phase is to verify the ETF.com.cn search-to-series pipeline itself, not to maximize data availability through mixed providers.

The first version should fetch a unified lookback window of about the latest 365 natural days. This is large enough to confirm that real series are available and suitable for later trend-metric research.

## Output Layout

The script will write artifacts under:

- `.test_artifacts/etf_trend_sources/`

Expected top-level files:

- `targets.json`
- `candidate_matches.json`
- `resolved_instruments.json`
- `kline_samples.json`
- `summary.md`

Expected series directory:

- `.test_artifacts/etf_trend_sources/series/`

Each selected primary instrument should also produce a full local time-series artifact, for example:

- `series/etf_515220.json`
- `series/index_399998.json`

## Output Semantics

### `targets.json`

Contains the exact target entries used in the current run. It is a runtime snapshot, not the canonical configuration source.

### `candidate_matches.json`

Contains raw and normalized candidate information per target, including:

- keyword used
- ETF candidate list summary
- index candidate list summary
- debug-only `outIndexFundList` summary when present

### `resolved_instruments.json`

Contains the best ETF candidate, best index candidate, selected primary instrument, and rule-based reason string for each target.

### `kline_samples.json`

Contains per-target K-line summary information, such as:

- status
- selected instrument kind
- selected instrument code
- row count
- date range
- latest close
- data-source notes when available

### `summary.md`

Contains a concise human-readable overview of:

- total targets
- successful target count
- unresolved target count
- K-line failures
- per-target one-line status summary

## Failure Handling

The script must continue processing other targets even if one target fails.

Per-target status values should be limited to:

- `ok`
- `search_failed`
- `unresolved`
- `kline_failed`

Each failure must:

- emit a concise log line
- be persisted in JSON artifacts
- be reflected in `summary.md`

The script should never abort the whole run merely because one target failed to resolve or fetch.

## Logging

Logging should stay concise and consistent with the repository style:

- `[INFO] search keyword=煤炭`
- `[WARN] unresolved label=创成长`
- `[ERROR] kline failed label=纳指ETF reason=...`

Logs should describe stage and target clearly, but avoid noisy dumps of whole responses.

## Validation Strategy

The first version validates against real upstream data only.

Validation is manual:

1. run `inspect_etf_trend_sources.py`
2. confirm `.test_artifacts/etf_trend_sources/` is created
3. confirm every configured target lands in one of the four explicit statuses
4. confirm successfully resolved targets produce both resolution metadata and local K-line artifacts
5. confirm `summary.md` makes it obvious where failures occur

No simulation or mock-data workflow is part of this phase.

## Design Rationale

### Recommended Approach: Standalone Resolver Script

This is preferred because it keeps the work isolated, stays aligned with the ETF.com.cn search origin of the targets, and produces stable local artifacts for later metric research without coupling exploratory logic to production alerting flows.

### Rejected Approach: OCR or Image Parsing

This was rejected because the user explicitly confirmed that future use will be manual configuration rather than image-driven extraction.

### Rejected Approach: Immediate Metric Reproduction

This was rejected because the current priority is to stabilize the target-to-series pipeline first. Computing screenshot metrics before source resolution would entangle debugging across too many layers.

### Rejected Approach: Mixed-Provider K-Line Fallback

This was rejected because the current objective is to validate that ETF.com.cn-discovered targets can also be serviced by ETF.com.cn-owned time-series endpoints. Falling back to TickFlow or AkShare in this phase would hide source-coverage problems that the inspection tool is supposed to expose.

## Success Criteria

The design is successful when:

- one script can run from a manually maintained target list
- each target produces auditable ETF/index search candidates
- each target either resolves to a primary instrument or is explicitly marked unresolved
- each resolved target either fetches real K-line data through ETF.com.cn-owned endpoints or is explicitly marked as an ETF.com.cn K-line failure
- the output artifacts are sufficient to start later research on `偏离率`、`综合趋势`、`转变日`
