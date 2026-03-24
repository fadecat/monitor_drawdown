import compare_jisilu_patch as cjp


def test_build_patch_summary_for_missing_patch():
    assert cjp.build_patch_summary("etf", None) == "未应用集思录补价。"


def test_build_patch_summary_for_etf_patch():
    patch = {
        "date": "2026-03-24",
        "fund_id": "159307",
        "fund_nm": "红利低波100ETF(博时)",
        "close": 1.058,
        "increase_rt": 1.15,
        "last_time": "15:00:00",
    }

    text = cjp.build_patch_summary("etf", patch)

    assert "159307" in text
    assert "现价 1.0580" in text
    assert "涨跌 1.15%" in text


def test_build_comparison_lines_marks_no_patch():
    report = {
        "name": "价值100ETF",
        "code": "512040",
        "type": "etf",
        "threshold": 0.05,
        "lookback_days": 120,
        "base_rows": 243,
        "patched_rows": 243,
        "patch_applied": False,
        "patch": None,
        "base_result": {
            "current_date": "2026-03-24",
            "current_price": 0.9387,
            "peak_price": 1.0000,
            "peak_date": "2025-12-18",
            "drawdown": 0.0613,
        },
        "patched_result": {
            "current_date": "2026-03-24",
            "current_price": 0.9387,
            "peak_price": 1.0000,
            "peak_date": "2025-12-18",
            "drawdown": 0.0613,
        },
    }

    lines = cjp.build_comparison_lines(report)

    assert any("是否补价 否" in line for line in lines)
    assert any("回撤变化 +0.00%" in line for line in lines)
    assert any("补丁明细: 未应用集思录补价。" in line for line in lines)
