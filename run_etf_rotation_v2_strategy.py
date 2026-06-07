from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

import etf_rotation_v2_strategy as strategy
import etf_rotation_v2_data as data_sources


DEFAULT_CONFIG_PATH = Path("etf_rotation_v2_config.yaml")
SOURCE_OUTPUT_ROOT = Path(".test_artifacts/etf_trend_sources")
DEFAULT_OUTPUT_ROOT = Path(".test_artifacts/etf_rotation_v2_strategy")


def load_rotation_config(path: Path | str = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("rotation v2 config must be a mapping")
    return payload


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def collect_rotation_inputs(
    config: dict[str, Any],
    output_root: Path | None = None,
) -> list[dict[str, Any]]:
    targets = list(config.get("risk_targets") or []) + list(config.get("defensive_targets") or [])
    snapshots: list[dict[str, Any]] = []
    unresolved_targets: list[dict[str, Any]] = []

    for target in targets:
        label = str(target.get("label") or "").strip()
        code = str(target.get("code") or "").strip()
        kind = str(target.get("kind") or "").strip()
        if label and code and kind:
            snapshots.append(
                {
                    "label": label,
                    "status": "ok",
                    "selected_primary": {
                        "kind": kind,
                        "code": code,
                        "name": str(target.get("name") or label).strip(),
                        "reason": "config_primary",
                    },
                }
            )
            continue
        unresolved_targets.append(target)

    if unresolved_targets:
        _ = output_root
        resolved_results = [data_sources.resolve_target(target) for target in unresolved_targets]
        for item in resolved_results:
            snapshots.append(
                {
                    "label": item["label"],
                    "status": item["status"],
                    "selected_primary": item.get("selected_primary"),
                }
            )

    return snapshots


def get_expected_snapshot_labels(config: dict[str, Any]) -> list[str]:
    labels: list[str] = []
    for target in list(config.get("risk_targets") or []) + list(config.get("defensive_targets") or []):
        label = str(target.get("label") or "").strip()
        if label:
            labels.append(label)
    return labels


def validate_snapshot_coverage(
    config: dict[str, Any],
    snapshots: list[dict[str, Any]],
) -> None:
    expected_labels = get_expected_snapshot_labels(config)
    snapshot_labels = {
        str(snapshot.get("label") or "").strip()
        for snapshot in snapshots
        if str(snapshot.get("label") or "").strip()
    }
    missing_labels = [label for label in expected_labels if label not in snapshot_labels]
    if missing_labels:
        raise ValueError(f"missing snapshots for configured targets: {', '.join(missing_labels)}")


def load_series_records(
    selected_primary: dict[str, Any],
    source_output_root: Path,
) -> list[dict[str, Any]]:
    kind = str(selected_primary["kind"])
    code = str(selected_primary["code"])
    series_path = source_output_root / "series" / f"{kind}_{code}.json"
    if series_path.exists():
        return json.loads(series_path.read_text(encoding="utf-8"))

    series_records, _summary = data_sources.fetch_selected_series(selected_primary)
    write_json(series_path, series_records)
    return series_records


def get_latest_series_date(series_records: list[dict[str, Any]]) -> str | None:
    for row in reversed(series_records):
        date_text = str(row.get("date") or "").strip()
        if date_text:
            return date_text
    return None


def trim_series_records_to_signal_date(
    series_records: list[dict[str, Any]],
    signal_date: str | None,
) -> list[dict[str, Any]]:
    if not signal_date:
        return series_records
    return [
        row
        for row in series_records
        if str(row.get("date") or "").strip() <= signal_date
    ]


def build_data_status(
    snapshots: list[dict[str, Any]],
    source_output_root: Path,
) -> dict[str, Any]:
    latest_dates_by_label: dict[str, str] = {}
    missing_labels: list[str] = []
    for snapshot in snapshots:
        label = str(snapshot.get("label") or "").strip()
        selected_primary = snapshot.get("selected_primary")
        if not label or not isinstance(selected_primary, dict):
            missing_labels.append(label or "unknown")
            continue
        series_records = load_series_records(selected_primary, source_output_root)
        latest_date = get_latest_series_date(series_records)
        if latest_date is None:
            missing_labels.append(label)
            continue
        latest_dates_by_label[label] = latest_date

    signal_date = min(latest_dates_by_label.values()) if latest_dates_by_label else None
    all_targets_aligned = bool(latest_dates_by_label) and len(set(latest_dates_by_label.values())) == 1
    max_latest_date = max(latest_dates_by_label.values()) if latest_dates_by_label else None
    lagging_labels = [
        label
        for label, latest_date in latest_dates_by_label.items()
        if max_latest_date is not None and latest_date != max_latest_date
    ]
    is_ready = signal_date is not None and not missing_labels
    return {
        "signal_date": signal_date,
        "all_targets_aligned": all_targets_aligned,
        "latest_dates_by_label": latest_dates_by_label,
        "lagging_labels": lagging_labels,
        "missing_labels": missing_labels,
        "status": "ready" if is_ready else "data_unavailable",
    }


def _trim_candidate_output(candidate: dict[str, Any]) -> dict[str, Any]:
    selected_primary = candidate.get("latest_snapshot", {}).get("selected_primary") or {}
    return {
        "label": candidate.get("label"),
        "symbol": selected_primary.get("code"),
        "name": selected_primary.get("name"),
        "kind": selected_primary.get("kind"),
        "data_date": candidate.get("data_date"),
        "score_25": candidate.get("score_25"),
        "annualized_return_25": candidate.get("annualized_return_25"),
        "r_squared_25": candidate.get("r_squared_25"),
        "return_10d": candidate.get("return_10d"),
        "qualified": candidate.get("qualified"),
        "rejection_reason": candidate.get("rejection_reason"),
    }


def build_candidate_metrics(
    snapshots: list[dict[str, Any]],
    strategy_config: dict[str, Any],
    source_output_root: Path,
    risk_labels: set[str],
    signal_date: str | None = None,
) -> list[dict[str, Any]]:
    candidate_metrics: list[dict[str, Any]] = []
    for snapshot in snapshots:
        label = str(snapshot.get("label") or "").strip()
        if label not in risk_labels:
            continue

        selected_primary = snapshot.get("selected_primary")
        if not isinstance(selected_primary, dict):
            continue
        series_records = trim_series_records_to_signal_date(
            load_series_records(selected_primary, source_output_root),
            signal_date,
        )
        candidate = strategy.build_rotation_candidate(
            latest_snapshot=snapshot,
            series_records=series_records,
            strategy_config=strategy_config,
        )
        if candidate is None:
            candidate_metrics.append(
                {
                    "label": label,
                    "symbol": selected_primary.get("code"),
                    "name": selected_primary.get("name"),
                    "kind": selected_primary.get("kind"),
                    "score_25": None,
                    "annualized_return_25": None,
                    "r_squared_25": None,
                    "return_10d": None,
                    "qualified": False,
                    "rejection_reason": "insufficient_history_or_invalid_series",
                }
            )
            continue

        candidate["data_date"] = get_latest_series_date(series_records)
        candidate_metrics.append(_trim_candidate_output(candidate))
    return candidate_metrics


def build_ranked_candidates(
    snapshots: list[dict[str, Any]],
    strategy_config: dict[str, Any],
    source_output_root: Path,
    risk_labels: set[str],
    signal_date: str | None = None,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for snapshot in snapshots:
        label = str(snapshot.get("label") or "").strip()
        if label not in risk_labels:
            continue

        selected_primary = snapshot.get("selected_primary")
        if not isinstance(selected_primary, dict):
            continue
        series_records = trim_series_records_to_signal_date(
            load_series_records(selected_primary, source_output_root),
            signal_date,
        )
        candidate = strategy.build_rotation_candidate(
            latest_snapshot=snapshot,
            series_records=series_records,
            strategy_config=strategy_config,
        )
        if candidate is None:
            continue
        candidate["data_date"] = get_latest_series_date(series_records)
        candidates.append(candidate)

    return [_trim_candidate_output(item) for item in strategy.rank_candidates(candidates)]


def build_defensive_holding(
    snapshots: list[dict[str, Any]],
    defensive_labels: set[str],
) -> dict[str, Any] | None:
    for snapshot in snapshots:
        label = str(snapshot.get("label") or "").strip()
        if label not in defensive_labels:
            continue
        selected_primary = snapshot.get("selected_primary")
        if not isinstance(selected_primary, dict):
            continue
        return {
            "label": label,
            "symbol": selected_primary.get("code"),
            "name": selected_primary.get("name"),
            "kind": selected_primary.get("kind"),
            "score_25": None,
            "annualized_return_25": None,
            "r_squared_25": None,
            "return_10d": None,
            "qualified": True,
            "rejection_reason": "",
        }
    return None


def build_portfolio_decision(
    ranked_candidates: list[dict[str, Any]],
    strategy_config: dict[str, Any],
    defensive_holding: dict[str, Any] | None,
) -> dict[str, Any]:
    holdings_num = max(int(strategy_config.get("holdings_num") or 1), 1)
    if ranked_candidates:
        return {
            "selected_holdings": ranked_candidates[:holdings_num],
            "selection_reason": "top_ranked_risk_asset",
            "rejected_candidates": ranked_candidates[holdings_num:],
            "fallback_holding": None,
        }

    fallback_holdings = [defensive_holding] if defensive_holding else []
    return {
        "selected_holdings": fallback_holdings,
        "selection_reason": "fallback_defensive_asset",
        "rejected_candidates": [],
        "fallback_holding": defensive_holding,
    }


def build_summary(
    candidate_metrics: list[dict[str, Any]],
    ranked_candidates: list[dict[str, Any]],
    portfolio_decision: dict[str, Any],
    data_status: dict[str, Any] | None = None,
) -> str:
    selected_labels = ",".join(
        str(item.get("label") or "").strip()
        for item in portfolio_decision.get("selected_holdings") or []
        if str(item.get("label") or "").strip()
    )
    lines = [
        "# ETF Rotation Strategy V2",
        "",
        f"- risk_candidates={len(candidate_metrics)}",
        f"- qualified_candidates={len(ranked_candidates)}",
        f"- selected={selected_labels or 'none'}",
        f"- selection_reason={portfolio_decision.get('selection_reason')}",
        f"- data_status={(data_status or {}).get('status') or 'unknown'}",
        f"- signal_date={(data_status or {}).get('signal_date') or 'unknown'}",
        "",
        "## Ranked Candidates",
        "",
    ]

    if not ranked_candidates:
        lines.append("- none")
    else:
        for item in ranked_candidates:
            lines.append(
                "- "
                f"{item['label']}: score_25={float(item['score_25']):.6f} "
                f"return_10d={float(item['return_10d']):.6f}"
            )

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
    validate_snapshot_coverage(config, snapshots)
    data_status = build_data_status(snapshots, resolved_source_root)
    signal_date = data_status.get("signal_date")
    strategy_config = dict(config.get("strategy") or {})
    risk_labels = {
        str(target.get("label") or "").strip()
        for target in config.get("risk_targets") or []
        if str(target.get("label") or "").strip()
    }
    defensive_labels = {
        str(target.get("label") or "").strip()
        for target in config.get("defensive_targets") or []
        if str(target.get("label") or "").strip()
    }

    candidate_metrics = build_candidate_metrics(
        snapshots=snapshots,
        strategy_config=strategy_config,
        source_output_root=resolved_source_root,
        risk_labels=risk_labels,
        signal_date=str(signal_date) if signal_date else None,
    )
    ranked_candidates = build_ranked_candidates(
        snapshots=snapshots,
        strategy_config=strategy_config,
        source_output_root=resolved_source_root,
        risk_labels=risk_labels,
        signal_date=str(signal_date) if signal_date else None,
    )
    defensive_holding = build_defensive_holding(snapshots, defensive_labels)
    portfolio_decision = build_portfolio_decision(
        ranked_candidates=ranked_candidates,
        strategy_config=strategy_config,
        defensive_holding=defensive_holding,
    )
    summary = build_summary(
        candidate_metrics=candidate_metrics,
        ranked_candidates=ranked_candidates,
        portfolio_decision=portfolio_decision,
        data_status=data_status,
    )

    write_json(resolved_output_root / "data_status.json", data_status)
    write_json(resolved_output_root / "candidate_metrics.json", candidate_metrics)
    write_json(resolved_output_root / "ranked_candidates.json", ranked_candidates)
    write_json(resolved_output_root / "portfolio_decision.json", portfolio_decision)
    (resolved_output_root / "summary.md").write_text(summary, encoding="utf-8")

    return {
        "config": config,
        "snapshots": snapshots,
        "data_status": data_status,
        "candidate_metrics": candidate_metrics,
        "ranked_candidates": ranked_candidates,
        "portfolio_decision": portfolio_decision,
        "summary": summary,
    }


if __name__ == "__main__":
    run()
