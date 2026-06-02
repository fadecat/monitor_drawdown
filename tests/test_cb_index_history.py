import json
import os

import cb_index_history as module
import refresh_cb_index_history as refresh_module


def test_parse_jisilu_page_extracts_date_and_data_variables():
    body = """
    <script>
    var __date = ['2026-05-28','2026-05-29'];
    var __data = {
      'price':[4880.1,4892.121],
      'avg_price':[161.5,162.102],
      'temperature':[78.5,79.08],
      'idx_price':[4010.5,4030.8]
    };
    </script>
    """

    records = module.parse_jisilu_page(body)

    assert records == [
        {
            "date": "2026-05-28",
            "index_value": "4880.1",
            "avg_price": "161.5",
            "temperature": "78.5",
            "idx_price": "4010.5",
        },
        {
            "date": "2026-05-29",
            "index_value": "4892.121",
            "avg_price": "162.102",
            "temperature": "79.08",
            "idx_price": "4030.8",
        },
    ]


def test_parse_jisilu_page_raises_clear_error_when_date_missing():
    body = """
    <script>
    var __data = {'price':[4892.121]};
    </script>
    """

    try:
        module.parse_jisilu_page(body)
    except RuntimeError as error:
        assert str(error) == "missing var __date"
    else:
        raise AssertionError("expected RuntimeError")


def test_merge_records_updates_same_date_and_preserves_old_fields():
    history = [
        {"date": "2026-05-28", "index_value": "4875.0", "legacy_only": "keep"},
        {"date": "2026-05-29", "index_value": "4888.0", "avg_price": "160.0"},
    ]
    live = [
        {"date": "2026-05-29", "index_value": "4892.121", "temperature": "79.08"},
        {"date": "2026-05-30", "index_value": "4900.000", "temperature": "80.00"},
    ]

    merged, stats = module.merge_records(history, live)

    assert merged == [
        {"date": "2026-05-28", "index_value": "4875.0", "legacy_only": "keep"},
        {"date": "2026-05-29", "index_value": "4892.121", "avg_price": "160.0", "temperature": "79.08"},
        {"date": "2026-05-30", "index_value": "4900.000", "temperature": "80.00"},
    ]
    assert stats == {"history": 2, "updated": 1, "added": 1}


def test_merge_records_raises_clear_error_when_live_record_date_missing():
    history = [{"date": "2026-05-28", "index_value": "4875.0"}]
    live = [{"index_value": "4892.121"}]

    try:
        module.merge_records(history, live)
    except ValueError as error:
        assert str(error) == "live record missing date"
    else:
        raise AssertionError("expected ValueError")


def test_build_merged_history_uses_local_archive_and_live_page(monkeypatch, tmp_path):
    archive_path = tmp_path / "market_temperature_history.json"
    archive_path.write_text(
        json.dumps([{"date": "2026-05-28", "index_value": "4875.0"}], ensure_ascii=False),
        encoding="utf-8",
    )

    monkeypatch.setattr(module, "MARKET_TEMPERATURE_HISTORY_JSON", archive_path)
    monkeypatch.setattr(
        module,
        "fetch_cb_index_page",
        lambda: """
        <script>
        var __date = ['2026-05-28','2026-05-29'];
        var __data = {
          'price':[4880.1,4892.121],
          'temperature':[78.5,79.08]
        };
        </script>
        """,
    )

    merged, stats = module.build_merged_history()

    assert merged == [
        {"date": "2026-05-28", "index_value": "4880.1", "temperature": "78.5"},
        {"date": "2026-05-29", "index_value": "4892.121", "temperature": "79.08"},
    ]
    assert stats == {"history": 1, "updated": 1, "added": 1}


def test_build_merged_history_treats_missing_archive_as_empty_history(monkeypatch, tmp_path):
    archive_path = tmp_path / "market_temperature_history.json"

    monkeypatch.setattr(module, "MARKET_TEMPERATURE_HISTORY_JSON", archive_path)
    monkeypatch.setattr(
        module,
        "fetch_cb_index_page",
        lambda: """
        <script>
        var __date = ['2026-05-29','2026-05-30'];
        var __data = {
          'price':[4892.121,4900.000],
          'temperature':[79.08,80.00]
        };
        </script>
        """,
    )

    merged, stats = module.build_merged_history()

    assert merged == [
        {"date": "2026-05-29", "index_value": "4892.121", "temperature": "79.08"},
        {"date": "2026-05-30", "index_value": "4900.000", "temperature": "80.00"},
    ]
    assert stats == {"history": 0, "updated": 0, "added": 2}


def test_refresh_main_writes_archive_successfully_on_first_run(monkeypatch, tmp_path, capsys):
    archive_path = tmp_path / "market_temperature_history.json"
    merged = [{"date": "2026-05-30", "index_value": "4900.000", "temperature": "80.00"}]

    monkeypatch.setattr(module, "MARKET_TEMPERATURE_HISTORY_JSON", archive_path)
    monkeypatch.setattr(refresh_module.history, "MARKET_TEMPERATURE_HISTORY_JSON", archive_path)
    monkeypatch.setattr(
        refresh_module.history,
        "build_merged_history",
        lambda: (merged, {"history": 0, "updated": 0, "added": 1}),
    )

    result = refresh_module.main()

    assert result == 0
    assert archive_path.read_text(encoding="utf-8") == json.dumps(merged, ensure_ascii=False, indent=2) + "\n"
    assert "[INFO] 归档已更新" in capsys.readouterr().out


def test_build_refresh_webhook_payload_formats_stats():
    payload = refresh_module.build_refresh_webhook_payload(
        stats={"history": 1968, "updated": 171, "added": 71},
        changed=True,
        latest_date="2026-06-01",
    )

    assert payload["msgtype"] == "markdown"
    content = payload["markdown"]["content"]
    assert "转债等权历史归档完成" in content
    assert "updated: `171`" in content
    assert "added: `71`" in content
    assert "latest: `2026-06-01`" in content


def test_notify_refresh_webhook_skips_when_env_missing(monkeypatch, capsys):
    monkeypatch.delenv("CB_INDEX_REFRESH_WEBHOOK_URL", raising=False)

    refresh_module.notify_refresh_webhook(
        stats={"history": 0, "updated": 0, "added": 0},
        changed=False,
        latest_date=None,
    )

    assert "未配置 CB_INDEX_REFRESH_WEBHOOK_URL" in capsys.readouterr().out
