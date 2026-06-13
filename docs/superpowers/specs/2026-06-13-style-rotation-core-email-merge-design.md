# Style Rotation Core Email Merge Design

## Summary

Merge the "风格轮动收益率差值日报" content into the existing "核心标的监控告警" email. The core monitor remains the only automatic send path for this combined email. Every time `monitor_drawdown.py` sends an email, it should attempt to include the style rotation summary and chart.

## Current Behavior

`monitor_drawdown.py` loads monitored targets, sends webhook alerts for triggered drawdown items, builds the valuation email, attaches valuation and FX charts, and sends the core email when there are triggered or valuation items.

`send_style_rotation_email.py` is a separate manual entrypoint. It delegates collection and HTML rendering to `preview_style_rotation_email.py`, which calls `style_rotation_preview.py` and `prototype_style_rotation_chart.py` to calculate the return spread and generate a PNG chart.

The style rotation workflow schedule is currently disabled. This merge should not delete the independent script or workflow.

## Desired Behavior

Whenever `monitor_drawdown.py` sends the core email, it should:

- collect the existing style rotation payload;
- generate the existing style rotation PNG chart;
- append a style rotation section to the HTML email before the footer;
- add a short style rotation summary to the plain text email;
- attach the style rotation PNG as a CID image in the same email.

The style rotation section should show:

- title: `风格轮动收益率差值`;
- as-of date;
- left and right names, currently `国证小盘成长 vs 国证大盘价值`;
- display window, return calculation window, and latest spread;
- the generated chart.

## Failure Handling

Style rotation is supplemental content. If collection, calculation, chart generation, or attachment fails, the monitor should log a warning and still send the core email.

Attachment failures should not prevent the email from being sent. This matches the existing valuation chart attachment behavior.

## Architecture

Reuse the existing style rotation pipeline instead of duplicating calculations:

- `monitor_drawdown.py` imports `preview_style_rotation_email.collect_style_rotation_email_payloads` inside the email preparation block.
- The collected payload, chart path, and as-of label are passed through `send_email()`, `build_email_message()`, `build_email_plain_text_content()`, and `build_email_html_content()`.
- `build_email_html_content()` renders a compact style rotation block using existing email colors and table-safe inline styles.
- `build_email_message()` attaches the style rotation chart with CID `<style_rotation_chart>`.

No new config is required. No workflow changes are required.

## Testing

Update tests in `tests/test_monitor_drawdown.py` to cover:

- HTML rendering includes the style rotation title, metadata, and `cid:style_rotation_chart`.
- Plain text rendering includes the style rotation summary.
- `build_email_message()` attaches the PNG when a style rotation chart path is provided.
- `main()` still sends the core email if style rotation collection fails.

Existing style rotation tests should continue to pass unchanged.

## Out Of Scope

- Removing `send_style_rotation_email.py`.
- Removing or changing `.github/workflows/style_rotation_email.yml`.
- Changing the style rotation calculation symbols, windows, or chart design.
- Adding schedule-specific behavior; the merged content appears every time the core email is sent.
