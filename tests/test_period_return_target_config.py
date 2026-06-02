from pathlib import Path

import analyze_etf_com_cn_period_returns as module


def test_load_period_return_targets_deduplicates_and_skips_empty_values(tmp_path: Path):
    config_path = tmp_path / "period_return_email_config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "targets:",
                "  - id: '159934'",
                "    source: etf_com_cn",
                "    name: 黄金ETF易方达",
                "  - id: '159934'",
                "    source: etf_com_cn",
                "    name: 重复项应忽略",
                "  - id: ''",
                "    source: etf_com_cn",
                "    name: 空ID应忽略",
                "  - id: cb_equal_weight",
                "    source: ''",
                "    name: 空source应忽略",
                "  - id: cb_equal_weight",
                "    source: jisilu_cb_index",
                "    name: 集思录转债等权",
                "  - id: cb_equal_weight",
                "    source: jisilu_cb_index",
                "    name: 重复转债索引应忽略",
                "  - just: ignored",
            ]
        ),
        encoding="utf-8",
    )

    targets = module.load_period_return_targets(config_path)

    assert targets == [
        {"id": "159934", "source": "etf_com_cn", "name": "黄金ETF易方达"},
        {"id": "cb_equal_weight", "source": "jisilu_cb_index", "name": "集思录转债等权"},
    ]


def test_load_period_return_targets_allows_empty_name_for_etf_targets(tmp_path: Path):
    config_path = tmp_path / "period_return_email_config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "targets:",
                "  - id: '159934'",
                "    source: etf_com_cn",
                "  - id: cb_equal_weight",
                "    source: jisilu_cb_index",
                "    name: 集思录转债等权",
            ]
        ),
        encoding="utf-8",
    )

    targets = module.load_period_return_targets(config_path)

    assert targets == [
        {"id": "159934", "source": "etf_com_cn", "name": ""},
        {"id": "cb_equal_weight", "source": "jisilu_cb_index", "name": "集思录转债等权"},
    ]
