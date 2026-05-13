import json
import inspect
from datetime import datetime, timezone, timedelta
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
import refresh_data_archive as rda


def test_resolve_archive_index_codes_prefers_tracking_index_then_index_then_code(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
targets:
  - name: etf-a
    type: etf
    code: "510300"
    tracking_index_code: "000300"
  - name: index-a
    type: index
    code: "399303"
  - name: valuation-a
    type: valuation
    code: "930955"
    index_detail_url: "https://www.etf.com.cn/api/etf-api-service/index/detail?indexCode=930955"
  - name: explicit-index
    type: etf
    code: "159307"
    index_code: "931052"
""".strip(),
        encoding="utf-8",
    )

    targets = rda.load_config(str(config_path))

    assert rda.resolve_archive_index_codes(targets) == ["000300", "399303", "930955", "931052"]


def test_resolve_archive_index_codes_prefers_index_code_from_index_detail_url_for_valuation_targets():
    targets = [
        {
            "name": "etf-with-valuation-data",
            "type": "valuation",
            "code": "512040",
            "index_detail_url": "https://www.efunds.com.cn/center/pc/index.html#/index?indexCode=931052",
        }
    ]

    assert rda.resolve_archive_index_codes(targets) == ["931052"]


def test_resolve_archive_index_codes_dedupes_and_skips_unresolved_targets(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
targets:
  - name: one
    type: valuation
    code: "930955"
  - name: two
    type: etf
    code: "515000"
    tracking_index_code: "930955"
  - name: three
    type: calendar
    code: "ignored"
  - name: four
    type: etf
    code: "159001"
""".strip(),
        encoding="utf-8",
    )

    targets = rda.load_config(str(config_path))

    assert rda.resolve_archive_index_codes(targets) == ["930955"]


def test_merge_records_by_key_overwrites_existing_record_for_non_date_key():
    existing = [
        {"symbol": "510300", "value": 1, "source": "existing"},
    ]
    incoming = [
        {"symbol": "510300", "value": 2, "source": "incoming"},
    ]

    merged = rda.merge_records_by_key(existing, incoming, "symbol")

    assert merged == [{"symbol": "510300", "value": 2, "source": "incoming"}]


def test_merge_records_by_key_sorts_merged_records_by_key():
    existing = [
        {"symbol": "B", "value": 3},
        {"symbol": "A", "value": 1},
    ]
    incoming = [
        {"symbol": "C", "value": 2},
    ]

    merged = rda.merge_records_by_key(existing, incoming, "symbol")

    assert merged == [
        {"symbol": "A", "value": 1},
        {"symbol": "B", "value": 3},
        {"symbol": "C", "value": 2},
    ]


def test_merge_records_by_key_skips_empty_and_missing_keys():
    existing = [
        {"symbol": "", "value": 1},
        {"value": 2},
    ]
    incoming = [
        {"symbol": None, "value": 3},
        {"symbol": "valid", "value": 4},
    ]

    merged = rda.merge_records_by_key(existing, incoming, "symbol")

    assert merged == [{"symbol": "valid", "value": 4}]


def test_merge_records_by_key_preserves_incoming_raw_field_on_overwrite():
    existing = [
        {"symbol": "510300", "value": 1, "raw": {"symbol": "510300", "value": 1, "note": "old"}},
    ]
    incoming = [
        {"symbol": "510300", "value": 2, "raw": {"symbol": "510300", "value": 2, "note": "new"}},
    ]

    merged = rda.merge_records_by_key(existing, incoming, "symbol")

    assert merged == [
        {"symbol": "510300", "value": 2, "raw": {"symbol": "510300", "value": 2, "note": "new"}},
    ]


def test_merge_records_by_key_keeps_falsy_numeric_and_boolean_keys():
    existing = [
        {"rank": 0, "value": "zero"},
        {"rank": False, "value": "false"},
    ]
    incoming = [
        {"rank": 1, "value": "one"},
    ]

    merged = rda.merge_records_by_key(existing, incoming, "rank")

    assert merged == [
        {"rank": 0, "value": "zero"},
        {"rank": 1, "value": "one"},
        {"rank": False, "value": "false"},
    ]


def test_build_archive_payload_writes_expected_json_envelope():
    payload = rda.build_archive_payload(
        source="akshare",
        identity={"index_code": "000300"},
        records=[{"date": "2026-05-13", "value": 1.23}],
        updated_at="2026-05-13T10:00:00+08:00",
    )

    assert payload == {
        "source": "akshare",
        "index_code": "000300",
        "updated_at": "2026-05-13T10:00:00+08:00",
        "records": [{"date": "2026-05-13", "value": 1.23}],
    }


def test_write_archive_file_detects_unchanged_content(tmp_path: Path):
    output_path = tmp_path / "archive" / "000300.json"
    expected_text = (
        "{\n"
        '  "source": "akshare",\n'
        '  "index_code": "000300",\n'
        '  "updated_at": "2026-05-13T10:00:00+08:00",\n'
        '  "records": [\n'
        "    {\n"
        '      "date": "2026-05-13",\n'
        '      "value": 1.23\n'
        "    }\n"
        "  ]\n"
        "}\n"
    )

    first_write = rda.write_archive_file(
        output_path=output_path,
        source="akshare",
        identity={"index_code": "000300"},
        records=[{"date": "2026-05-13", "value": 1.23}],
        updated_at="2026-05-13T10:00:00+08:00",
    )
    second_write = rda.write_archive_file(
        output_path=output_path,
        source="akshare",
        identity={"index_code": "000300"},
        records=[{"date": "2026-05-13", "value": 1.23}],
        updated_at="2026-05-13T10:00:00+08:00",
    )

    assert first_write is True
    assert second_write is False
    assert output_path.read_text(encoding="utf-8") == expected_text
    assert json.loads(output_path.read_text(encoding="utf-8")) == {
        "source": "akshare",
        "index_code": "000300",
        "updated_at": "2026-05-13T10:00:00+08:00",
        "records": [{"date": "2026-05-13", "value": 1.23}],
    }


def test_write_archive_file_overwrites_stale_content(tmp_path: Path):
    output_path = tmp_path / "archive" / "china_10y.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("{\"source\": \"old\"}\n", encoding="utf-8")

    wrote = rda.write_archive_file(
        output_path=output_path,
        source="akshare",
        identity={"series": "china_10y"},
        records=[{"date": "2026-05-13", "value": 2.34}],
        updated_at="2026-05-13T10:00:00+08:00",
    )

    assert wrote is True
    assert json.loads(output_path.read_text(encoding="utf-8")) == {
        "source": "akshare",
        "series": "china_10y",
        "updated_at": "2026-05-13T10:00:00+08:00",
        "records": [{"date": "2026-05-13", "value": 2.34}],
    }


def test_write_archive_file_serializes_date_values_in_records(tmp_path: Path):
    output_path = tmp_path / "archive" / "china_10y.json"

    wrote = rda.write_archive_file(
        output_path=output_path,
        source="akshare",
        identity={"series": "china_10y"},
        records=[{"日期": date(2026, 5, 13), "中国国债收益率10年": 2.34}],
        updated_at="2026-05-13T10:00:00+08:00",
    )

    assert wrote is True
    assert json.loads(output_path.read_text(encoding="utf-8")) == {
        "source": "akshare",
        "series": "china_10y",
        "updated_at": "2026-05-13T10:00:00+08:00",
        "records": [{"日期": "2026-05-13", "中国国债收益率10年": 2.34}],
    }


def test_task3_writer_helpers_are_type_annotated():
    build_signature = inspect.signature(rda.build_archive_payload)
    write_signature = inspect.signature(rda.write_archive_file)

    assert build_signature.parameters["source"].annotation is str
    assert build_signature.parameters["identity"].annotation is not inspect._empty
    assert build_signature.parameters["records"].annotation is not inspect._empty
    assert build_signature.parameters["updated_at"].annotation is str
    assert build_signature.return_annotation is not inspect._empty

    assert write_signature.parameters["output_path"].annotation is not inspect._empty
    assert write_signature.parameters["source"].annotation is str
    assert write_signature.parameters["identity"].annotation is not inspect._empty
    assert write_signature.parameters["records"].annotation is not inspect._empty
    assert write_signature.parameters["updated_at"].annotation is str
    assert write_signature.return_annotation is bool


def test_fetch_index_archive_records_returns_upstream_rows_unchanged(monkeypatch):
    upstream_rows = [
        {"trdDt": "2026-05-13", "pxClose": "1.23", "meta": {"source": "upstream"}},
        {"trdDt": "2026-05-12", "pxClose": "1.22"},
    ]

    monkeypatch.setattr(rda, "fetch_json_response", lambda dataset_name, url: upstream_rows)

    records = rda.fetch_index_archive_records("index_eod", "000300", "https://example.invalid/archive")

    assert records == upstream_rows


def test_fetch_index_archive_records_raises_value_error_for_non_list_payload(monkeypatch):
    monkeypatch.setattr(rda, "fetch_json_response", lambda dataset_name, url: {"data": []})

    with pytest.raises(ValueError, match="must be a list"):
        rda.fetch_index_archive_records("index_eod", "000300", "https://example.invalid/archive")


def test_fetch_index_archive_records_raises_value_error_for_mixed_list_payload(monkeypatch):
    monkeypatch.setattr(
        rda,
        "fetch_json_response",
        lambda dataset_name, url: [{"trdDt": "2026-05-13"}, "bad-row"],
    )

    with pytest.raises(ValueError, match="must contain only dict rows"):
        rda.fetch_index_archive_records("index_eod", "000300", "https://example.invalid/archive")


def test_fetch_bond_archive_records_preserves_original_column_names_and_raw_records(monkeypatch):
    forwarded = {}

    def bond_stub(start_date):
        forwarded["start_date"] = start_date
        return pd.DataFrame(
            [
                {"日期": "2026-05-13", "中国国债收益率10年": 2.34, "备注": None},
                {"日期": "2026-05-12", "中国国债收益率10年": float("nan"), "备注": "x"},
            ]
        )

    monkeypatch.setattr(
        rda,
        "ak",
        SimpleNamespace(bond_zh_us_rate=bond_stub),
        raising=False,
    )

    records = rda.fetch_bond_archive_records("20260501")

    assert forwarded["start_date"] == "20260501"
    assert records == [
        {"日期": "2026-05-13", "中国国债收益率10年": 2.34, "备注": None},
        {"日期": "2026-05-12", "中国国债收益率10年": None, "备注": "x"},
    ]


def test_fetch_bond_archive_records_returns_empty_list_for_empty_dataframe(monkeypatch):
    monkeypatch.setattr(
        rda,
        "ak",
        SimpleNamespace(
            bond_zh_us_rate=lambda start_date: pd.DataFrame(),
        ),
        raising=False,
    )

    assert rda.fetch_bond_archive_records("20260501") == []


def test_load_existing_records_returns_empty_list_when_file_is_missing(tmp_path: Path):
    output_path = tmp_path / "data_archive" / "index_eod" / "000300.json"

    assert rda.load_existing_records(output_path) == []


def test_load_existing_records_returns_dict_rows_from_payload_records(tmp_path: Path):
    output_path = tmp_path / "data_archive" / "bond_10y" / "china_10y.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            {
                "source": "akshare.bond_zh_us_rate",
                "series": "china_10y",
                "updated_at": "2026-05-13T09:00:00+08:00",
                "records": [
                    {"日期": "2026-05-12", "中国国债收益率10年": 1.72},
                    "skip-me",
                    {"日期": "2026-05-13", "中国国债收益率10年": 1.73},
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    assert rda.load_existing_records(output_path) == [
        {"日期": "2026-05-12", "中国国债收益率10年": 1.72},
        {"日期": "2026-05-13", "中国国债收益率10年": 1.73},
    ]


def test_load_existing_records_raises_value_error_for_malformed_archive_payload(tmp_path: Path):
    output_path = tmp_path / "data_archive" / "index_eod" / "000300.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            {
                "source": "https://example.invalid/archive",
                "index_code": "000300",
                "updated_at": "2026-05-13T09:00:00+08:00",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="invalid archive payload"):
        rda.load_existing_records(output_path)


def test_refresh_index_dataset_merges_existing_and_returns_changed_path(tmp_path: Path, monkeypatch):
    archive_root = tmp_path / "data_archive"
    output_path = archive_root / "index_eod" / "000300.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            {
                "source": "https://example.invalid/existing",
                "index_code": "000300",
                "updated_at": "2026-05-13T09:00:00+08:00",
                "records": [{"trdDt": "2026-05-12", "pxClose": 1.11}],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        rda,
        "fetch_index_archive_records",
        lambda dataset_name, index_code, url: [{"trdDt": "2026-05-13", "pxClose": 1.23}],
    )

    changed = rda.refresh_index_dataset(
        archive_root=archive_root,
        dataset_name="index_eod",
        index_code="000300",
        source_url="https://example.invalid/archive",
        merge_key="trdDt",
        updated_at="2026-05-13T15:10:00+08:00",
    )

    assert changed == [output_path]
    assert json.loads(output_path.read_text(encoding="utf-8")) == {
        "source": "https://example.invalid/archive",
        "index_code": "000300",
        "updated_at": "2026-05-13T15:10:00+08:00",
        "records": [
            {"trdDt": "2026-05-12", "pxClose": 1.11},
            {"trdDt": "2026-05-13", "pxClose": 1.23},
        ],
    }


def test_refresh_index_dataset_returns_empty_list_when_only_updated_at_differs(
    tmp_path: Path,
    monkeypatch,
):
    archive_root = tmp_path / "data_archive"
    output_path = archive_root / "index_eod" / "000300.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            {
                "source": "https://example.invalid/existing",
                "index_code": "000300",
                "updated_at": "2026-05-13T09:00:00+08:00",
                "records": [{"trdDt": "2026-05-13", "pxClose": 1.23}],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        rda,
        "fetch_index_archive_records",
        lambda dataset_name, index_code, url: [{"trdDt": "2026-05-13", "pxClose": 1.23}],
    )

    changed = rda.refresh_index_dataset(
        archive_root=archive_root,
        dataset_name="index_eod",
        index_code="000300",
        source_url="https://example.invalid/archive",
        merge_key="trdDt",
        updated_at="2026-05-13T15:10:00+08:00",
    )

    assert changed == []


def test_refresh_bond_dataset_returns_empty_list_when_content_is_unchanged(tmp_path: Path, monkeypatch):
    archive_root = tmp_path / "data_archive"
    output_path = archive_root / "bond_10y" / "china_10y.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            {
                "source": "akshare.bond_zh_us_rate",
                "series": "china_10y",
                "updated_at": "2026-05-13T09:00:00+08:00",
                "records": [{"日期": "2026-05-13", "中国国债收益率10年": 1.73}],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        rda,
        "fetch_bond_archive_records",
        lambda start_date: [{"日期": "2026-05-13", "中国国债收益率10年": 1.73}],
    )

    changed = rda.refresh_bond_dataset(
        archive_root=archive_root,
        updated_at="2026-05-13T15:10:00+08:00",
        start_date="20200101",
    )

    assert changed == []


def test_build_parser_uses_config_yaml_by_default():
    parser = rda.build_parser()

    args = parser.parse_args([])

    assert args.config == "config.yaml"


def test_now_iso_returns_beijing_iso_string():
    value = rda.now_iso()
    parsed = datetime.fromisoformat(value)

    assert value.endswith("+08:00")
    assert parsed.utcoffset() == timedelta(hours=8)


def test_main_returns_zero_when_any_archive_work_succeeds(monkeypatch, tmp_path: Path):
    called = {
        "load_config": None,
        "codes": None,
        "eod": [],
        "dividend": [],
        "valuation": [],
        "bond": None,
    }

    frozen_updated_at = "2026-05-13T15:10:00+08:00"
    expected_bond_start_date = (
        datetime.fromisoformat(frozen_updated_at) - timedelta(days=365 * 11)
    ).strftime("%Y%m%d")

    monkeypatch.setattr(rda, "ARCHIVE_ROOT", tmp_path / "archive-root")
    monkeypatch.setattr(rda, "now_iso", lambda: frozen_updated_at)
    monkeypatch.setattr(
        rda,
        "load_config",
        lambda config_path: called.__setitem__("load_config", config_path) or [{"code": "dummy"}],
    )
    monkeypatch.setattr(
        rda,
        "resolve_archive_index_codes",
        lambda targets: called.__setitem__("codes", targets) or ["000300", "930955"],
    )
    monkeypatch.setattr(rda, "build_index_eod_price_url", lambda index_code: f"eod:{index_code}")
    monkeypatch.setattr(
        rda,
        "build_index_dividend_yield_url",
        lambda index_code: f"dividend:{index_code}",
    )
    monkeypatch.setattr(
        rda,
        "build_index_valuation_percentile_url",
        lambda index_code: f"valuation:{index_code}",
    )

    def refresh_index_dataset_stub(archive_root, dataset_name, index_code, source_url, merge_key, updated_at):
        if dataset_name == "index_eod":
            called["eod"].append((archive_root, index_code, source_url, merge_key, updated_at))
        elif dataset_name == "index_dividend_ratio":
            called["dividend"].append((archive_root, index_code, source_url, merge_key, updated_at))
        elif dataset_name == "index_valuation_percentile":
            called["valuation"].append((archive_root, index_code, source_url, merge_key, updated_at))
        if dataset_name == "index_eod" and index_code == "000300":
            return [archive_root / dataset_name / f"{index_code}.json"]
        return []

    def refresh_bond_dataset_stub(archive_root, updated_at, start_date):
        called["bond"] = (archive_root, updated_at, start_date)
        return []

    monkeypatch.setattr(rda, "refresh_index_dataset", refresh_index_dataset_stub)
    monkeypatch.setattr(rda, "refresh_bond_dataset", refresh_bond_dataset_stub)

    exit_code = rda.main(["--config", "custom-config.yaml"])

    assert exit_code == 0
    assert called["load_config"] == "custom-config.yaml"
    assert called["codes"] == [{"code": "dummy"}]
    assert called["eod"] == [
        (tmp_path / "archive-root", "000300", "eod:000300", "trdDt", "2026-05-13T15:10:00+08:00"),
        (tmp_path / "archive-root", "930955", "eod:930955", "trdDt", "2026-05-13T15:10:00+08:00"),
    ]
    assert called["dividend"] == [
        (tmp_path / "archive-root", "000300", "dividend:000300", "trdDt", "2026-05-13T15:10:00+08:00"),
        (tmp_path / "archive-root", "930955", "dividend:930955", "trdDt", "2026-05-13T15:10:00+08:00"),
    ]
    assert called["valuation"] == [
        (tmp_path / "archive-root", "000300", "valuation:000300", "trdDt", "2026-05-13T15:10:00+08:00"),
        (tmp_path / "archive-root", "930955", "valuation:930955", "trdDt", "2026-05-13T15:10:00+08:00"),
    ]
    assert called["bond"] == (
        tmp_path / "archive-root",
        "2026-05-13T15:10:00+08:00",
        expected_bond_start_date,
    )


def test_main_returns_one_when_config_parse_fails(monkeypatch, capsys):
    monkeypatch.setattr(rda, "load_config", lambda config_path: (_ for _ in ()).throw(ValueError("bad config")))

    exit_code = rda.main(["--config", "broken.yaml"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "[ERROR] bad config" in captured.out
