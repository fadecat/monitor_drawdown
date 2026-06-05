from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

import etf_rotation_strategy as strategy
import inspect_etf_trend_sources as sources


DEFAULT_CONFIG_PATH = Path("etf_rotation_config.yaml")
SOURCE_OUTPUT_ROOT = Path(".test_artifacts/etf_trend_sources")
DEFAULT_OUTPUT_ROOT = Path(".test_artifacts/etf_rotation_strategy")


def load_rotation_config(path: Path | str = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("rotation config must be a mapping")
    return payload


def collect_rotation_inputs(
    config: dict[str, Any],
    output_root: Path | None = None,
) -> list[dict[str, Any]]:
    targets = list(config.get("targets") or []) + list(config.get("defensive_targets") or [])
    return sources.collect_trend_metrics(targets=targets, output_root=output_root)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_series_records(
    selected_primary: dict[str, Any],
    source_output_root: Path,
) -> list[dict[str, Any]]:
    kind = str(selected_primary["kind"])
    code = str(selected_primary["code"])
    series_path = source_output_root / "series" / f"{kind}_{code}.json"
    if series_path.exists():
        return json.loads(series_path.read_text(encoding="utf-8"))

    series_records, _summary = sources.fetch_selected_series(selected_primary)
    sources.write_json(series_path, series_records)
    return series_records


def build_ranked_candidates(
    snapshots: list[dict[str, Any]],
    strategy_config: dict[str, Any],
    source_output_root: Path,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for snapshot in snapshots:
        selected_primary = snapshot.get("selected_primary")
        if not isinstance(selected_primary, dict):
            continue
        series_records = load_series_records(selected_primary, source_output_root)
        candidate = strategy.build_rotation_candidate(
            latest_snapshot=snapshot,
            series_records=series_records,
            strategy_config=strategy_config,
        )
        if candidate is None:
            continue
        candidate["selected_primary"] = selected_primary
        candidates.append(candidate)

    return strategy.rank_candidates(candidates)


def build_summary(
    ranked_candidates: list[dict[str, Any]],
    portfolio_decision: dict[str, Any],
) -> str:
    selected_labels = ",".join(
        str(item.get("label") or "").strip()
        for item in portfolio_decision.get("selected_holdings") or []
        if str(item.get("label") or "").strip()
    )
    lines = [
        "# ETF Rotation Strategy",
        "",
        f"- ranked_candidates={len(ranked_candidates)}",
        f"- selected={selected_labels or 'none'}",
        f"- selection_reason={portfolio_decision.get('selection_reason')}",
        "",
        "## Ranked Candidates",
        "",
    ]

    if not ranked_candidates:
        lines.append("- none")
    else:
        for item in ranked_candidates:
            lines.append(f"- {item['label']}: return_20d={float(item['return_20d']):.4f}")

    return "\n".join(lines) + "\n"


def run(
    config_path: Path | str = DEFAULT_CONFIG_PATH,
    output_root: Path | str = DEFAULT_OUTPUT_ROOT,
    source_output_root: Path | str = SOURCE_OUTPUT_ROOT,
) -> dict[str, Any]:
    config = load_rotation_config(config_path)
    resolved_output_root = Path(output_root)
    resolved_source_root = Path(source_output_root)
    resolved_output_root.mkdir(parents=True, exist_ok=True)

    snapshots = collect_rotation_inputs(config, output_root=resolved_source_root)
    strategy_config = dict(config.get("strategy") or {})
    ranked_candidates = build_ranked_candidates(
        snapshots=snapshots,
        strategy_config=strategy_config,
        source_output_root=resolved_source_root,
    )
    portfolio_decision = strategy.select_portfolio(
        candidates=ranked_candidates,
        strategy_config=strategy_config,
    )
    summary = build_summary(
        ranked_candidates=ranked_candidates,
        portfolio_decision=portfolio_decision,
    )

    write_json(resolved_output_root / "ranked_candidates.json", ranked_candidates)
    write_json(resolved_output_root / "portfolio_decision.json", portfolio_decision)
    (resolved_output_root / "summary.md").write_text(summary, encoding="utf-8")

    return {
        "config": config,
        "snapshots": snapshots,
        "ranked_candidates": ranked_candidates,
        "portfolio_decision": portfolio_decision,
        "summary": summary,
    }


if __name__ == "__main__":
    run()
