# Style Rotation Core Email Merge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Include the existing style rotation return-spread report in every core monitor email without blocking the email if that supplemental section fails.

**Architecture:** Reuse `preview_style_rotation_email.collect_style_rotation_email_payloads()` from `monitor_drawdown.py` when an email is about to be sent. Pass the resulting payload, as-of label, and chart path through the existing email builder chain, render a compact HTML section, add a plain-text summary, and attach the chart as a CID image.

**Tech Stack:** Python 3.10, `email.message.EmailMessage`, pandas-based existing style rotation pipeline, pytest.

---

## File Structure

- Modify `monitor_drawdown.py`: add style rotation helper/rendering functions, extend email builder function signatures, attach the chart, and collect supplemental content in `main()`.
- Modify `tests/test_monitor_drawdown.py`: add focused regression tests and update `send_email` mocks to accept the new optional parameters.
- No workflow changes. No changes to `send_style_rotation_email.py`, `preview_style_rotation_email.py`, `style_rotation_preview.py`, or chart generation logic.

---

### Task 1: Add Email Rendering Tests

**Files:**
- Modify: `tests/test_monitor_drawdown.py`

- [ ] **Step 1: Write failing tests for HTML, plain text, and CID attachment**

Add this helper near existing email tests:

```python
def sample_style_rotation_payload():
    return {
        "meta": {
            "left_name": "国证小盘成长",
            "right_name": "国证大盘价值",
            "return_window_days": 250,
            "display_window_days": 252,
        },
        "series": {
            "dates": ["2026-06-12"],
            "spread": [12.34],
        },
    }
```

Add these tests near `test_build_email_html_content_renders_full_bleed_charts_and_fx_chart`:

```python
def test_build_email_content_includes_style_rotation_section():
    payload = sample_style_rotation_payload()

    html = md.build_email_html_content(
        [],
        valuation_items=[],
        current_time=md.datetime(2026, 6, 13, 15, 30, tzinfo=md.BEIJING_TZ),
        style_rotation_payload=payload,
        style_rotation_as_of_label="2026-06-12",
        style_rotation_chart_path=md.Path(".test_artifacts/style_rotation/style_rotation_preview.png"),
    )
    text = md.build_email_plain_text_content(
        [],
        valuation_items=[],
        current_time=md.datetime(2026, 6, 13, 15, 30, tzinfo=md.BEIJING_TZ),
        style_rotation_payload=payload,
        style_rotation_as_of_label="2026-06-12",
    )

    assert "风格轮动收益率差值" in html
    assert "国证小盘成长 vs 国证大盘价值" in html
    assert "当前差值 12.34%" in html
    assert "cid:style_rotation_chart" in html
    assert "风格轮动收益率差值" in text
    assert "国证小盘成长 vs 国证大盘价值" in text
    assert "当前差值: 12.34%" in text
```

Add this test near other email message tests:

```python
def test_build_email_message_attaches_style_rotation_chart(tmp_path):
    chart_path = tmp_path / "style_rotation.png"
    chart_path.write_bytes(b"png-bytes")

    message = md.build_email_message(
        "sender@example.com",
        ["alice@example.com"],
        "核心标的监控告警",
        [],
        valuation_items=[],
        current_time=md.datetime(2026, 6, 13, 15, 30, tzinfo=md.BEIJING_TZ),
        style_rotation_payload=sample_style_rotation_payload(),
        style_rotation_as_of_label="2026-06-12",
        style_rotation_chart_path=chart_path,
    )

    html_part = message.get_payload()[-1]
    related = html_part.get_payload()

    assert any(part.get("Content-ID") == "<style_rotation_chart>" for part in related)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_monitor_drawdown.py::test_build_email_content_includes_style_rotation_section tests/test_monitor_drawdown.py::test_build_email_message_attaches_style_rotation_chart -q
```

Expected: FAIL because the email builder signatures do not yet accept `style_rotation_*` parameters.

---

### Task 2: Implement Email Builder Support

**Files:**
- Modify: `monitor_drawdown.py`

- [ ] **Step 1: Add style rotation summary helpers**

Add these helpers near the existing email formatting helpers before `build_email_plain_text_content`:

```python
STYLE_ROTATION_CHART_CID = "style_rotation_chart"


def _get_latest_style_rotation_spread(style_rotation_payload: Optional[Dict[str, Any]]) -> Optional[float]:
    if not isinstance(style_rotation_payload, dict):
        return None
    series = style_rotation_payload.get("series")
    if not isinstance(series, dict):
        return None
    spread_values = series.get("spread")
    if not isinstance(spread_values, list) or not spread_values:
        return None
    latest = parse_float(spread_values[-1])
    return latest


def _build_style_rotation_summary(style_rotation_payload: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(style_rotation_payload, dict):
        return None
    meta = style_rotation_payload.get("meta")
    if not isinstance(meta, dict):
        return None
    latest_spread = _get_latest_style_rotation_spread(style_rotation_payload)
    return {
        "left_name": str(meta.get("left_name") or "左侧标的").strip(),
        "right_name": str(meta.get("right_name") or "右侧标的").strip(),
        "return_window_days": meta.get("return_window_days"),
        "display_window_days": meta.get("display_window_days"),
        "latest_spread": latest_spread,
    }
```

- [ ] **Step 2: Extend plain text content**

Change `build_email_plain_text_content` signature to:

```python
def build_email_plain_text_content(
    triggered_items: List[Dict],
    valuation_items: Optional[List[Dict]] = None,
    current_time: Optional[datetime] = None,
    style_rotation_payload: Optional[Dict[str, Any]] = None,
    style_rotation_as_of_label: Optional[str] = None,
) -> str:
```

Before returning the joined lines, append:

```python
    style_summary = _build_style_rotation_summary(style_rotation_payload)
    if style_summary:
        lines.extend(
            [
                "",
                "风格轮动收益率差值",
                f"数据截至: {style_rotation_as_of_label or '-'}",
                f"{style_summary['left_name']} vs {style_summary['right_name']}",
            ]
        )
        latest_spread = style_summary.get("latest_spread")
        if latest_spread is not None:
            lines.append(f"当前差值: {format_percent(latest_spread, decimals=2, strip=False)}%")
```

- [ ] **Step 3: Add HTML section renderer**

Add this function before `build_email_html_content`:

```python
def _render_style_rotation_email_section(
    *,
    style_rotation_payload: Optional[Dict[str, Any]],
    style_rotation_as_of_label: Optional[str],
    style_rotation_chart_path: Optional[Path],
) -> str:
    summary = _build_style_rotation_summary(style_rotation_payload)
    if not summary:
        return ""

    latest_spread = summary.get("latest_spread")
    spread_text = (
        f"{format_percent(latest_spread, decimals=2, strip=False)}%"
        if latest_spread is not None
        else "-"
    )
    return_window = summary.get("return_window_days")
    display_window = summary.get("display_window_days")
    chart_html = ""
    if style_rotation_chart_path:
        chart_html = (
            f'<div style="padding:14px 0 0 0">'
            f'<img src="cid:{STYLE_ROTATION_CHART_CID}" alt="风格轮动收益率差值图" '
            f'style="width:100%;max-width:100%;height:auto;display:block">'
            f'</div>'
        )

    return (
        f'<tr><td style="padding:24px 28px 0 28px">'
        f'<div style="border-top:1px solid {EMAIL_BORDER_CARD_SPLIT};padding-top:24px">'
        f'<div style="font-size:18px;font-weight:700;color:{EMAIL_TEXT_PRIMARY}">'
        f'风格轮动收益率差值</div>'
        f'<div style="font-size:12px;color:{EMAIL_LABEL_COLOR};margin-top:4px">'
        f'数据截至 {escape(str(style_rotation_as_of_label or "-"))}</div>'
        f'<div style="font-size:14px;color:{EMAIL_TEXT_PRIMARY};margin-top:10px">'
        f'{escape(str(summary["left_name"]))} vs {escape(str(summary["right_name"]))}</div>'
        f'<div style="font-size:12px;color:{EMAIL_MUTED_COLOR};margin-top:6px">'
        f'展示窗口 {escape(str(display_window or "-"))} 天'
        f' &nbsp;|&nbsp; 计算窗口 {escape(str(return_window or "-"))} 天'
        f' &nbsp;|&nbsp; 当前差值 {escape(spread_text)}</div>'
        f'{chart_html}'
        f'</div></td></tr>'
    )
```

- [ ] **Step 4: Extend HTML builder signature and render before footer**

Change `build_email_html_content` signature to include:

```python
    style_rotation_payload: Optional[Dict[str, Any]] = None,
    style_rotation_as_of_label: Optional[str] = None,
    style_rotation_chart_path: Optional[Path] = None,
```

Before `footer = (...)`, append:

```python
    style_rotation_section = _render_style_rotation_email_section(
        style_rotation_payload=style_rotation_payload,
        style_rotation_as_of_label=style_rotation_as_of_label,
        style_rotation_chart_path=style_rotation_chart_path,
    )
```

In the final return, concatenate `style_rotation_section` before `footer`:

```python
        + "".join(card_rows)
        + style_rotation_section
        + footer
```

- [ ] **Step 5: Extend message and send function signatures**

Add optional parameters to `build_email_message()` and pass them to text and HTML builders:

```python
    style_rotation_payload: Optional[Dict[str, Any]] = None,
    style_rotation_as_of_label: Optional[str] = None,
    style_rotation_chart_path: Optional[Path] = None,
```

After FX chart attachment, add:

```python
    if style_rotation_chart_path:
        html_part = message.get_payload()[-1]
        try:
            with open(style_rotation_chart_path, "rb") as file:
                img_bytes = file.read()
            html_part.add_related(
                img_bytes,
                maintype="image",
                subtype="png",
                cid=f"<{STYLE_ROTATION_CHART_CID}>",
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[WARN] 风格轮动图表挂载失败: {exc}")
```

Add the same optional parameters to `send_email()` and pass them through to `build_email_message()`.

- [ ] **Step 6: Run focused tests**

Run:

```powershell
python -m pytest tests/test_monitor_drawdown.py::test_build_email_content_includes_style_rotation_section tests/test_monitor_drawdown.py::test_build_email_message_attaches_style_rotation_chart -q
```

Expected: PASS.

---

### Task 3: Collect Style Rotation During Main Email Send

**Files:**
- Modify: `tests/test_monitor_drawdown.py`
- Modify: `monitor_drawdown.py`

- [ ] **Step 1: Write failing test for supplemental failure isolation**

In `test_main_keeps_other_charts_when_one_valuation_chart_fails`, update the `send_email` monkeypatch lambda to accept:

```python
style_rotation_payload=None,
style_rotation_as_of_label=None,
style_rotation_chart_path=None,
```

Add this separate test near it:

```python
def test_main_sends_email_when_style_rotation_collection_fails(monkeypatch, capsys, tmp_path):
    workspace_tmp = tmp_path / "style_rotation_failure"
    workspace_tmp.mkdir()
    monkeypatch.setenv("WEBHOOK_URL", "https://example.invalid/webhook")
    monkeypatch.setenv("CONFIG_PATH", str(workspace_tmp / "config.yaml"))
    monkeypatch.setenv("RECEIVER_EMAIL", "alice@example.com")
    monkeypatch.setenv("SMTP_USER", "sender@example.com")
    monkeypatch.setenv("SMTP_PASS", "secret")

    (workspace_tmp / "config.yaml").write_text(
        """
targets:
  - name: "沪深300"
    code: "000300"
    type: "valuation"
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setattr(md, "fetch_cn_10y_bond_yield", lambda: None)
    monkeypatch.setattr(
        md,
        "fetch_cn_10y_bond_history_with_archive_fallback",
        lambda: (pd.DataFrame({"date": pd.to_datetime(["2026-06-12"]), "yield_pct": [1.7]}), {"data_source": "live", "archive_latest_date": None}),
    )
    monkeypatch.setattr(
        md,
        "fetch_target_index_metrics",
        lambda target: {
            "index_code": "000300",
            "index_name": "沪深300",
            "index_dividend_yield": 2.46,
            "index_valuation_date": "2026-06-12",
            "index_valuation_metrics": {"PE(TTM)": {"current": 12.3, "percentiles": {"5Y": 55.0}}},
        },
    )
    monkeypatch.setattr(md, "attach_equity_bond_spread", lambda item, bond_history: None)
    monkeypatch.setattr(md, "send_webhook", lambda *args, **kwargs: None)
    monkeypatch.setattr("prototype_fx_chart.generate_fx_chart", lambda output_dir: None)
    monkeypatch.setattr("prototype_valuation_percentile_chart.generate_valuation_percentile_chart", lambda target, output_dir: None)
    monkeypatch.setattr("preview_style_rotation_email.collect_style_rotation_email_payloads", lambda output_dir: (_ for _ in ()).throw(RuntimeError("style failed")))

    captured = {}

    def fake_send_email(
        config,
        triggered_items,
        valuation_items=None,
        current_time=None,
        chart_paths=None,
        fx_chart_path=None,
        style_rotation_payload=None,
        style_rotation_as_of_label=None,
        style_rotation_chart_path=None,
    ):
        captured["sent"] = True
        captured["style_rotation_payload"] = style_rotation_payload
        captured["style_rotation_chart_path"] = style_rotation_chart_path

    monkeypatch.setattr(md, "send_email", fake_send_email)

    md.main()

    output = capsys.readouterr().out
    assert captured["sent"] is True
    assert captured["style_rotation_payload"] is None
    assert captured["style_rotation_chart_path"] is None
    assert "风格轮动邮件区块生成失败" in output
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests/test_monitor_drawdown.py::test_main_sends_email_when_style_rotation_collection_fails -q
```

Expected: FAIL because `main()` does not yet collect style rotation or pass the new parameters.

- [ ] **Step 3: Implement main collection**

Inside `main()`, in the `if email_config:` block before `send_email(...)`, initialize:

```python
                style_rotation_payload: Optional[Dict[str, Any]] = None
                style_rotation_as_of_label: Optional[str] = None
                style_rotation_chart_path: Optional[Path] = None
                try:
                    from preview_style_rotation_email import collect_style_rotation_email_payloads

                    style_rotation_payloads = collect_style_rotation_email_payloads(chart_output_dir)
                    style_rotation_payload = dict(style_rotation_payloads["payload"])
                    style_rotation_as_of_label = str(style_rotation_payloads["as_of_label"])
                    style_rotation_chart_path = Path(style_rotation_payloads["chart_path"])
                except Exception as exc:  # noqa: BLE001
                    print(f"[WARN] 风格轮动邮件区块生成失败: {exc}")
```

Pass these values to `send_email(...)`:

```python
                    style_rotation_payload=style_rotation_payload,
                    style_rotation_as_of_label=style_rotation_as_of_label,
                    style_rotation_chart_path=style_rotation_chart_path,
```

- [ ] **Step 4: Run focused test**

Run:

```powershell
python -m pytest tests/test_monitor_drawdown.py::test_main_sends_email_when_style_rotation_collection_fails -q
```

Expected: PASS.

---

### Task 4: Full Verification

**Files:**
- No additional file edits expected.

- [ ] **Step 1: Run monitor and style rotation tests**

Run:

```powershell
python -m pytest tests/test_monitor_drawdown.py tests/test_send_style_rotation_email.py tests/test_preview_style_rotation_email.py tests/test_style_rotation_preview.py -q
```

Expected: PASS.

- [ ] **Step 2: Inspect git diff**

Run:

```powershell
git diff -- monitor_drawdown.py tests/test_monitor_drawdown.py docs/superpowers/specs/2026-06-13-style-rotation-core-email-merge-design.md docs/superpowers/plans/2026-06-13-style-rotation-core-email-merge.md
```

Expected: diff only contains the style rotation merge design, implementation plan, email merge code, and tests.

- [ ] **Step 3: Commit**

Run:

```powershell
git add docs/superpowers/specs/2026-06-13-style-rotation-core-email-merge-design.md docs/superpowers/plans/2026-06-13-style-rotation-core-email-merge.md monitor_drawdown.py tests/test_monitor_drawdown.py
git commit -m "feat: merge style rotation into core email"
```

Expected: commit succeeds.

---

## Self-Review

Spec coverage: The plan covers reuse of the existing style rotation pipeline, every-email inclusion, HTML rendering, plain-text summary, CID attachment, failure isolation, and no workflow/script removal.

Placeholder scan: No placeholder tasks remain.

Type consistency: Optional parameters use `Dict[str, Any]`, `str`, and `Path`, matching existing imports and email builder patterns in `monitor_drawdown.py`.
