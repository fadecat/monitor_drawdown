# CCTDA Coal Daily Email Design

## Goal

Add a separate daily GitHub Actions workflow that fetches the latest "煤炭运销日报" article from the CCTDA list page at Shanghai 15:00, extracts the full image content from the detail page, emails that content as a new message whose subject matches the article title, and records successful delivery state back into the repository.

## Context

The repository already contains:

- SMTP email delivery logic in `monitor_drawdown.py`
- local environment loading in `local_env.py`
- an existing GitHub Actions workflow pattern in `.github/workflows/monitor.yml`
- a `tests/` directory with unit-test coverage for parsing and email-related helpers

The new feature should remain isolated from drawdown monitoring behavior. It should not expand `monitor_drawdown.py` with unrelated website scraping responsibilities.

## Confirmed Requirements

- Run on GitHub Actions every day at Asia/Shanghai 15:00
- Scrape `https://www.cctda.org.cn/index.php?m=content&c=index&a=lists&catid=75`
- Treat the first report entry on the list page as the latest article
- Open the detail page and use the detail page title as the email subject
- Send a brand-new email, not a reply in an existing thread
- If the detail page contains images, download and email all images inline
- If the detail page contains a PDF instead, download it and convert all pages to images, then email all converted images inline
- Persist send state in a JSON file committed back to `main` after successful delivery
- Skip duplicate sends when the latest article matches previously recorded state
- Fail the workflow if scraping, rendering, email delivery, or post-send state commit breaks

## Recommended Approach

Implement a new standalone script, `monitor_cctda_coal_daily.py`, with focused helpers for list-page parsing, detail-page extraction, PDF-to-image conversion, HTML email assembly, and state persistence. Add a dedicated workflow file instead of modifying the existing drawdown workflow.

This keeps responsibilities clear:

- `monitor_drawdown.py` continues to own market monitoring
- the new script owns CCTDA scraping and report delivery
- workflow scheduling and bot commit logic stay localized to the new workflow

## Alternatives Considered

### 1. Standalone script and standalone workflow

Recommended.

Pros:

- clear ownership and simpler maintenance
- lower regression risk for drawdown monitoring
- easier to test site parsing independently

Cons:

- introduces one new top-level script

### 2. Merge the feature into `monitor_drawdown.py`

Rejected.

Pros:

- can reuse more existing code directly

Cons:

- makes a large script larger
- couples unrelated business logic
- increases regression risk for an existing workflow

### 3. Implement most logic inline inside workflow YAML

Rejected.

Pros:

- fewer files

Cons:

- poor testability
- harder debugging
- parsing and email logic become brittle

## Architecture

### Script entrypoint

Create `monitor_cctda_coal_daily.py` as the only application entrypoint for this feature. It will:

1. load environment variables and optional local overrides
2. fetch the CCTDA list page
3. parse the latest article metadata
4. load saved state
5. exit cleanly if the latest article has already been sent
6. fetch the detail page
7. extract either inline image URLs or a PDF URL
8. materialize all report pages as local PNG files
9. build and send an HTML email
10. write updated state JSON
11. exit success so the workflow can commit the new state file

### Reuse boundaries

The script may reuse:

- `local_env.load_local_env`
- `local_env.get_env_value`
- SMTP defaults or email helper patterns from `monitor_drawdown.py`

It should not import broad scraping or monitoring behavior from `monitor_drawdown.py` beyond narrow email-related helpers if reuse is truly clean. If that reuse would create awkward coupling, duplicate the minimal SMTP helpers into the new script instead.

### Persistent state

Store state in `data_state/cctda_coal_daily.json`.

This file should contain only the latest successfully sent article metadata:

```json
{
  "article_url": "https://www.cctda.org.cn/index.php?m=content&c=index&a=show&catid=75&id=5759",
  "article_title": "煤炭运销日报(2026-5-15)",
  "published_at": "2026-05-15 16:44:46",
  "content_type": "images",
  "image_count": 3,
  "content_hash": "sha256:...",
  "sent_at": "2026-05-17T15:00:12+08:00"
}
```

`article_url` is the primary duplicate key. `article_title` and `content_hash` provide auditability and guard against ambiguous cases.

## Data Flow

### 1. Fetch the list page

Request the list page URL with a deterministic user agent and a timeout. Parse the first report row under the article list. Extract:

- article title
- absolute detail URL
- list-page date string

Do not sort by date text. The live page is already ordered newest first, so the first row is authoritative.

### 2. Check prior state

Read `data_state/cctda_coal_daily.json` if present.

If `article_url` matches the latest list result, stop without sending email and without rewriting state.

### 3. Fetch the detail page

Request the detail URL and parse:

- detail-page title from the article header
- publication timestamp if present
- report body from `#article-content`

Use the detail-page title as the email subject exactly as displayed.

### 4. Determine content mode

Inspect the parsed article body in this order:

1. collect all `img` elements under `#article-content`
2. if no images exist, search for a `.pdf` link in the article body
3. if neither exists, fail the run

The content mode becomes:

- `images` when article images exist
- `pdf` when a PDF is found and will be rendered to images

### 5. Materialize image pages

If the article already contains images:

- normalize all image URLs to absolute URLs
- download every image in document order
- store them in a temporary working directory

If the article contains a PDF:

- download the PDF to a temporary working directory
- convert every page to PNG in order using `PyMuPDF`
- use the generated PNG files as the email body images

The resulting page-image list is the only rendering input for the email body.

### 6. Build and send email

Construct a fresh HTML email with:

- subject equal to the detail-page title
- top summary block containing article title, article URL, and fetch timestamp
- all page images embedded inline in original order

Do not attach the original PDF. The email must contain only inline images derived from the report.

### 7. Save state

After SMTP delivery succeeds:

- compute a content hash over the final ordered image URLs or rendered image bytes
- write the new state JSON
- return success

The workflow will then commit and push the updated JSON file to `main`.

## Components

### `monitor_cctda_coal_daily.py`

Primary responsibilities:

- environment loading
- HTTP fetching
- HTML parsing
- PDF rendering
- email construction
- state file I/O
- exit codes and logging

Suggested helper boundaries:

- `fetch_html(url: str) -> str`
- `parse_latest_article_from_list(html: str) -> dict`
- `parse_detail_content(html: str, base_url: str) -> dict`
- `download_report_images(image_urls: list[str], output_dir: Path) -> list[Path]`
- `download_pdf(pdf_url: str, output_path: Path) -> Path`
- `render_pdf_to_pngs(pdf_path: Path, output_dir: Path) -> list[Path]`
- `load_state(path: Path) -> dict`
- `save_state(path: Path, state: dict) -> None`
- `build_report_email(...) -> EmailMessage`
- `send_report_email(...) -> None`

### `.github/workflows/cctda-coal-daily.yml`

Responsibilities:

- daily schedule
- manual dispatch
- Python setup
- dependency installation
- script execution
- conditional commit and push of state JSON

### `tests/test_monitor_cctda_coal_daily.py`

Responsibilities:

- parsing regressions
- duplicate detection
- state file behavior
- email subject/body expectations

## Workflow Design

Create a new workflow file instead of modifying `.github/workflows/monitor.yml`.

The workflow should:

- run on `schedule` and `workflow_dispatch`
- use UTC cron corresponding to Asia/Shanghai 15:00
- install Python 3.10
- install runtime dependencies including:
  - `requests`
  - `beautifulsoup4`
  - `PyMuPDF`
- run the new script with SMTP environment variables
- check whether `data_state/cctda_coal_daily.json` changed
- if changed, commit and push to `main` using the GitHub Actions bot identity

The workflow should only commit after the script exits successfully.

## Email Design

The email should be intentionally simple for client compatibility:

- plain-text fallback with title, URL, and note that images are included in HTML view
- HTML body with a narrow wrapper and stacked images
- each image added as a MIME related part referenced by `cid`
- image width constrained for email rendering, while preserving aspect ratio

The subject line must match the detail-page title string exactly.

## Error Handling

The run should fail hard for incomplete content. No partial emails.

Fail conditions:

- list page request fails
- latest list item cannot be parsed
- detail page request fails
- detail content contains neither images nor PDF
- any report image download fails
- PDF download fails
- any PDF page render fails
- SMTP send fails

Special case:

- if the email sends successfully but the workflow later fails to commit state, the overall workflow should still fail so the operator can see the state mismatch
- logs should make clear that delivery succeeded but repository state persistence failed

## Logging

Use the repository’s existing concise logging style:

- `[INFO]` for normal milestones
- `[WARN]` for recoverable non-fatal conditions
- `[ERROR]` for failures before exit

Important milestones to log:

- latest article discovered
- duplicate detected and skipped
- content mode selected
- image count prepared
- email sent
- state file written

## Testing Strategy

Add deterministic unit tests with fixture HTML strings. Do not depend on live CCTDA or SMTP endpoints.

Minimum coverage:

- parse latest article from the list page HTML
- parse image-mode detail page HTML
- parse PDF-mode detail page HTML
- reject unsupported detail content
- skip duplicate when state matches latest `article_url`
- write and reload state JSON
- build email subject from detail-page title
- include the expected number of inline images in the email message

PDF rendering tests should avoid a real remote PDF. Either:

- render a small local fixture PDF created during the test, or
- mock the renderer boundary and verify call flow

## Security and Secrets

Reuse the existing environment-variable pattern for:

- `RECEIVER_EMAIL`
- `SMTP_USER`
- `SMTP_PASS`
- optional SMTP host and port overrides if already supported

Do not store credentials in the state JSON or workflow YAML.

## Scope Boundaries

Included:

- CCTDA list/detail scraping
- image/PDF detection
- PDF-to-PNG conversion
- inline email sending
- repository-backed delivery state
- dedicated workflow and tests

Excluded:

- OCR extraction from images or PDFs
- multiple-recipient templating beyond existing email env support
- historical backfill of older reports
- attachments in addition to inline images
- generalized website monitoring framework

## Rollout Notes

The first successful run will send the current latest report and create the initial state JSON. Subsequent runs will skip until a new latest article appears at the top of the list page.
