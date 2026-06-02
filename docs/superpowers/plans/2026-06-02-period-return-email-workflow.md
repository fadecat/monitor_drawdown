# Period Return Email Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone scheduled GitHub Actions workflow that sends the "跨品种ETF区间收益日报" email using the existing SMTP env-var conventions, without invoking the existing drawdown monitor or webhook flow.

**Architecture:** Add a dedicated `send_period_return_email.py` runtime entrypoint that reuses the verified period-return analysis, chart rendering, and env-based email config loading. Add a separate workflow file that mirrors the existing monitor schedule but runs only the new sender script, keeping the new email path isolated from `monitor_drawdown.py` main flow.

**Tech Stack:** Python 3.10+, `requests`, `pyyaml`, `matplotlib`, `smtplib`, `email.message`, `pytest`, GitHub Actions

---

## File Map

- Create: `send_period_return_email.py`
- Create: `.github/workflows/period_return_email.yml`
- Create: `tests/test_send_period_return_email.py`

## Task Checklist

- [ ] Task 1: Add failing tests for standalone period-return email sending
- [ ] Task 2: Implement the standalone sender script
- [ ] Task 3: Add the dedicated GitHub Actions workflow
- [ ] Task 4: Verify tests and local sender execution
