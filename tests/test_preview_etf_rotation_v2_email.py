from __future__ import annotations

from pathlib import Path

import preview_etf_rotation_v2_email as module


def _rotation_result(
    *,
    aligned: bool = True,
    data_status: str = "ready",
    selection_reason: str = "top_ranked_risk_asset",
):
    selected = {
        "label": "黄金ETF易方达",
        "symbol": "159934",
        "name": "黄金ETF易方达",
        "score_25": 2.345,
        "annualized_return_25": 1.234,
        "r_squared_25": 0.912,
        "return_10d": 0.0321,
        "qualified": True,
        "data_date": "2026-06-05",
    }
    if selection_reason == "fallback_defensive_asset":
        selected = {
            "label": "银华日利ETF",
            "symbol": "511880",
            "name": "银华日利ETF",
            "qualified": True,
        }
    return {
        "data_status": {
            "status": data_status,
            "signal_date": "2026-06-05",
            "all_targets_aligned": aligned,
            "latest_dates_by_label": {
                "黄金ETF易方达": "2026-06-05",
                "纳指ETF国泰": "2026-06-04" if not aligned else "2026-06-05",
            },
            "lagging_labels": [] if aligned else ["纳指ETF国泰"],
            "missing_labels": [],
        },
        "candidate_metrics": [
            selected,
            {
                "label": "纳指ETF国泰",
                "symbol": "513100",
                "name": "纳指ETF国泰",
                "score_25": 1.111,
                "annualized_return_25": 0.567,
                "r_squared_25": 0.812,
                "return_10d": -0.002,
                "qualified": False,
                "rejection_reason": "return_10d_not_positive",
                "data_date": "2026-06-04" if not aligned else "2026-06-05",
            },
        ],
        "ranked_candidates": [selected] if selection_reason != "fallback_defensive_asset" else [],
        "portfolio_decision": {
            "selection_reason": selection_reason,
            "selected_holdings": [selected],
        },
    }


def test_build_email_subject_marks_data_unavailable():
    subject = module.build_email_subject(
        _rotation_result(aligned=False, data_status="data_unavailable"),
        previous_holding_label="黄金ETF易方达",
    )

    assert subject == "【数据不可用】ETF轮动V2 | 沿用上一信号 | 信号日 2026-06-05"


def test_build_email_subject_marks_unchanged_and_defensive():
    unchanged = module.build_email_subject(
        _rotation_result(),
        previous_holding_label="黄金ETF易方达",
    )
    defensive = module.build_email_subject(
        _rotation_result(selection_reason="fallback_defensive_asset"),
        previous_holding_label="黄金ETF易方达",
    )

    assert unchanged == "【持仓不变】ETF轮动V2 | 黄金ETF易方达 | 信号日 2026-06-05"
    assert defensive == "【切入防守】ETF轮动V2 | → 银华日利ETF | 信号日 2026-06-05"


def test_build_email_html_shows_data_dates_candidate_scores_and_ascii_curve():
    html = module.build_email_html(
        _rotation_result(aligned=False),
        previous_holding_label="上一有效持仓",
        equity_curve=[
            {"date": "2026-06-01", "strategy_nav": 38.0},
            {"date": "2026-06-02", "strategy_nav": 38.5},
            {"date": "2026-06-03", "strategy_nav": 38.2},
        ],
    )

    assert "数据日期不一致" in html
    assert "纳指ETF国泰" in html
    assert "2026-06-04" in html
    assert "score_25" in html
    assert "近60日策略净值走势" in html
    assert "当前信号持仓：黄金ETF易方达" in html


def test_write_preview_html_outputs_file(tmp_path: Path):
    output_path = module.write_preview_html("<html>ok</html>", tmp_path)

    assert output_path == tmp_path / "preview_etf_rotation_v2_email.html"
    assert output_path.read_text(encoding="utf-8") == "<html>ok</html>"


def test_collect_payload_uses_previous_state_for_unchanged_subject(monkeypatch, tmp_path: Path):
    state_path = tmp_path / "state.json"
    state_path.write_text('{"last_holding_label": "黄金ETF易方达"}', encoding="utf-8")
    seen = {}

    def fake_run(*, output_root, source_output_root):
        seen["output_root"] = output_root
        seen["source_output_root"] = source_output_root
        return _rotation_result()

    monkeypatch.setattr(module.runner, "run", fake_run)

    payload = module.collect_etf_rotation_v2_email_payloads(
        output_dir=tmp_path / "out",
        state_path=state_path,
    )

    assert seen == {
        "output_root": tmp_path / "out" / "rotation",
        "source_output_root": tmp_path / "out" / "source",
    }
    assert payload["subject"].startswith("【持仓不变】")
    assert payload["next_state"] == {
        "last_signal_date": "2026-06-05",
        "last_holding_label": "黄金ETF易方达",
        "last_selection_reason": "top_ranked_risk_asset",
    }


def test_collect_payload_does_not_update_state_when_data_not_aligned(monkeypatch, tmp_path: Path):
    state_path = tmp_path / "state.json"
    state_path.write_text('{"last_holding_label": "黄金ETF易方达"}', encoding="utf-8")
    monkeypatch.setattr(
        module.runner,
        "run",
        lambda **kwargs: _rotation_result(aligned=False, data_status="data_unavailable"),
    )

    payload = module.collect_etf_rotation_v2_email_payloads(
        output_dir=tmp_path / "out",
        state_path=state_path,
    )

    assert payload["subject"].startswith("【数据不可用】")
    assert payload["next_state"] is None
