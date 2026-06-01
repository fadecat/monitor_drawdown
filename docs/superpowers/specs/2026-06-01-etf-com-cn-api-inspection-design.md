# ETF.com.cn API Inspection Design

## Goal

Add a repeatable local inspection tool that captures the current responses for a fixed set of ETF.com.cn-related endpoints, saves the raw payloads locally for manual analysis, and generates a concise structural summary.

This work is strictly exploratory. It does not change `monitor_drawdown.py`, does not feed new data into monitoring logic, and does not implement the return, drawdown, or chart calculations shown in the referenced website screenshots.

## Confirmed Scope

The inspection tool will cover exactly these six ETF codes:

- `159934`
- `159941`
- `159259`
- `159263`
- `511130`
- `511380`

The tool will capture these endpoint categories:

1. The comparison page URL:
   - `https://www.etf.com.cn/contrastETF.html#/result?codes=159934,159941,159259,159263,511130,511380`
2. The fund quotes list API:
   - `POST https://www.etf.com.cn/api/etf-api-service/fund-quotes/list`
   - Request body: the fixed six-code JSON array
3. The per-fund NAV JSON endpoints:
   - `https://cdn.efunds.com.cn/etf-net/etf_fund_nav_159934.json`
   - `https://cdn.efunds.com.cn/etf-net/etf_fund_nav_159941.json`
   - `https://cdn.efunds.com.cn/etf-net/etf_fund_nav_159259.json`
   - `https://cdn.efunds.com.cn/etf-net/etf_fund_nav_159263.json`
   - `https://cdn.efunds.com.cn/etf-net/etf_fund_nav_511130.json`
   - `https://cdn.efunds.com.cn/etf-net/etf_fund_nav_511380.json`

## Explicit Non-Goals

This phase will not:

- integrate ETF.com.cn data into the production monitoring flow
- replace or modify existing ETF data sources in `monitor_drawdown.py`
- compute return windows such as `近1月`, `近3月`, `近6月`, `近1年`, `年初至今`, or `近3年`
- compute maximum drawdown
- render charts or recreate the ETF.com.cn comparison page
- create stable regression fixtures from live remote responses

## Implementation Shape

Add a new standalone script at the repository root:

- `inspect_etf_com_cn_api.py`

This follows the existing repository pattern of keeping one-off or focused operational tools as standalone scripts rather than mixing them into the main monitoring entrypoint.

The script will use fixed internal constants for:

- the six ETF codes
- the comparison page URL
- the fund quotes list API URL
- the NAV JSON URL template
- the default local output directory

The script is intentionally not a pytest case because:

- it depends on live remote network access
- it is for research and structure discovery, not regression verification
- the repository testing guidance prefers deterministic tests that avoid live upstream dependencies

## Output Layout

The script will write artifacts under:

- `.test_artifacts/etf_com_cn_api/`

Expected files:

- `contrast_page.html`
- `fund_quotes_list.json`
- `etf_fund_nav_159934.json`
- `etf_fund_nav_159941.json`
- `etf_fund_nav_159259.json`
- `etf_fund_nav_159263.json`
- `etf_fund_nav_511130.json`
- `etf_fund_nav_511380.json`
- `summary.md`

The raw response files are intentionally local-only artifacts. They should not be committed to the repository.

## Request and Persistence Behavior

The script should:

1. Create the output directory if it does not exist.
2. Fetch the comparison page HTML and save it exactly as returned.
3. Send the fixed JSON array to the fund quotes list endpoint using `POST` and save the JSON response.
4. Fetch each per-code NAV JSON file and save each response as-is.
5. Generate a summary document based on the saved responses.

If one request fails, the script should continue with the remaining endpoints and record the failure in the summary rather than aborting the whole inspection run.

Logging should stay minimal and consistent with the repository style, using concise status markers such as `[INFO]`, `[WARN]`, and `[ERROR]`.

## Summary Document Contents

The generated `summary.md` should be objective and structural. It should not hardcode business conclusions that depend on subjective interpretation.

For each captured response, include:

- source URL
- HTTP method
- local output file path
- HTTP status code when available
- content type when available
- byte size
- whether the payload parsed as JSON
- top-level JSON type when applicable: object or array
- top-level keys when the payload is an object
- item count when the payload is an array
- first-item keys when the payload is an array of objects
- identification of likely record-list fields when the payload is an object containing nested arrays
- candidate business-relevant fields based on field-name heuristics

The candidate-field heuristic should flag names containing markers such as:

- `code`
- `name`
- `date`
- `nav`
- `yield`
- `return`
- `drawdown`
- `ratio`
- `percent`
- `close`

If a payload cannot be parsed as JSON, the summary should describe it as raw text or HTML and report a short structural note such as line count or whether the page appears to be a frontend shell.

## Interpretation Guidance After Capture

After running the tool and inspecting the saved samples, a manual analysis step will answer these questions outside the script:

- whether `fund-quotes/list` appears to map to the comparison table shown in the screenshot
- whether `etf_fund_nav_<code>.json` contains enough historical series data to support the line chart shown in the screenshot
- whether these two endpoint groups appear sufficient or whether the page likely triggers additional hidden APIs for derived metrics
- what future calculations would likely be needed to derive the period returns and maximum drawdown displays

Those conclusions belong in the implementation follow-up discussion, not in the automated summary generator.

## Error Handling

The script should handle these cases explicitly:

- non-200 responses
- timeouts
- invalid JSON on endpoints expected to return JSON
- local write failures

Each failure should:

- emit a concise log line
- be reflected in `summary.md`
- not prevent the rest of the inspection run from completing

## Testing Strategy

No automated network test will be added in this phase.

Verification will be manual:

1. Run the script locally.
2. Confirm that the output directory is created.
3. Confirm that each configured endpoint produces either a saved response or a documented failure entry.
4. Confirm that `summary.md` describes the structure of each saved response.

This keeps the exploratory tool separate from deterministic unit-test coverage.

## Design Rationale

### Recommended Approach: Standalone Inspection Script

This approach is preferred because it keeps research code isolated, produces reusable local artifacts, and avoids coupling exploratory logic to the production monitoring script.

### Rejected Approach: Live pytest Sampling

This was rejected because it would create a fragile test that depends on upstream availability and changing live data.

### Rejected Approach: Extend `monitor_drawdown.py`

This was rejected because the user explicitly wants to clarify the external API behavior first, and mixing inspection logic into the main script would increase maintenance risk without serving production behavior.

## Success Criteria

The design is successful when:

- a user can run one script and collect all raw responses for the fixed ETF set
- the raw responses are saved locally in a predictable directory
- the generated summary is enough to quickly inspect response shapes and likely relevant fields
- the main monitoring flow remains unchanged
