# Repository Guidelines

## Project Structure & Module Organization
This repository is intentionally small. [`monitor_drawdown.py`](/C:/Users/han/桌面/code/monitor_drawdown/monitor_drawdown.py) is the only application entrypoint and contains config loading, data fetching, drawdown calculation, and webhook delivery. [`config.yaml`](/C:/Users/han/桌面/code/monitor_drawdown/config.yaml) defines monitored ETF/index targets. [`.github/workflows/monitor.yml`](/C:/Users/han/桌面/code/monitor_drawdown/.github/workflows/monitor.yml) runs the job on a schedule and via manual dispatch. There is no `tests/` directory yet; add one at the repo root when introducing automated tests.

## Build, Test, and Development Commands
Install runtime dependencies with:

```powershell
python -m pip install --upgrade pip
pip install akshare pandas requests pyyaml
```

Run locally with a webhook configured:

```powershell
$env:WEBHOOK_URL="https://example.invalid/webhook"
$env:CONFIG_PATH=".\config.yaml"
python .\monitor_drawdown.py
```

Use `python -m pytest` for automated tests once a `tests/` package exists. Keep local runs aligned with the GitHub Actions Python version in the workflow (`3.10`).

## Coding Style & Naming Conventions
Follow PEP 8 with 4-space indentation and `snake_case` for functions, variables, and YAML keys. Preserve the current style of type hints on public helpers and concise status logging such as `[INFO]`, `[WARN]`, and `[ERROR]`. Prefer small, single-purpose helpers for symbol normalization, retries, and data cleanup instead of expanding `main()`.

## Testing Guidelines
There is no committed coverage baseline yet, so changes should at minimum include targeted regression tests for business logic. Prioritize tests for `build_em_index_symbols`, `normalize_dataframe`, `compute_drawdown`, and retry behavior. Name test files `tests/test_*.py` and keep sample inputs deterministic; avoid tests that depend on live AkShare or webhook network calls.

## Commit & Pull Request Guidelines
Recent history mixes short imperative subjects with optional prefixes such as `fix:` and `ADD:`. Prefer one-line commit messages in imperative mood, for example `fix: improve index symbol fallback`. Pull requests should describe the monitoring behavior changed, note any config or secret impacts, and include relevant log output or screenshots when webhook formatting is affected.

## Security & Configuration Tips
Never commit real webhook URLs or other secrets. Keep secrets in environment variables locally and GitHub Actions secrets in CI. Treat `config.yaml` as shareable target metadata only; if environment-specific configs are needed, add a local untracked override rather than editing production values directly.
