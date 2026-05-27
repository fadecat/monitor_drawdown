import argparse
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List

import akshare as ak
import pandas as pd

from monitor_drawdown import (
    BEIJING_TZ,
    build_index_dividend_yield_url,
    build_index_eod_price_url,
    build_index_valuation_percentile_url,
    fetch_json_response,
    load_config,
    run_with_retry,
)


ARCHIVE_ROOT = Path(__file__).resolve().parent / "data_archive"


def _extract_index_code_from_detail_url(index_detail_url: str) -> str:
    match = re.search(r"indexCode=(\d+)", index_detail_url)
    return match.group(1) if match else ""



def resolve_archive_index_code(target: Dict) -> str:
    tracking_index_code = str(target.get("tracking_index_code") or "").strip()
    if tracking_index_code:
        return tracking_index_code

    index_code = str(target.get("index_code") or "").strip()
    if index_code:
        return index_code

    target_type = str(target.get("type") or "").strip().lower()
    code = str(target.get("code") or "").strip()
    if target_type in {"index", "valuation"} and code:
        index_detail_code = _extract_index_code_from_detail_url(
            str(target.get("index_detail_url") or "").strip()
        )
        if index_detail_code:
            return index_detail_code
        return code

    return ""


def resolve_archive_index_codes(targets: List[Dict]) -> List[str]:
    seen = set()
    result: List[str] = []

    for target in targets:
        code = resolve_archive_index_code(target)
        if code and code not in seen:
            result.append(code)
            seen.add(code)

    return result


def _record_key(record: Dict, key: str) -> str:
    if key not in record:
        return ""

    value = record[key]
    if value is None:
        return ""

    return str(value).strip()


def merge_records_by_key(existing: List[Dict], incoming: List[Dict], key: str) -> List[Dict]:
    merged: Dict[str, Dict] = {}

    for record in existing:
        record_key = _record_key(record, key)
        if record_key:
            merged[record_key] = record

    for record in incoming:
        record_key = _record_key(record, key)
        if record_key:
            merged[record_key] = record

    return [merged[record_key] for record_key in sorted(merged)]


def fetch_index_archive_records(dataset_name: str, index_code: str, url: str) -> List[Dict]:
    payload = fetch_json_response(dataset_name, url)
    if not isinstance(payload, list):
        raise ValueError("index archive response must be a list")
    if any(not isinstance(row, dict) for row in payload):
        raise ValueError("index archive response must contain only dict rows")
    return payload


def fetch_bond_archive_records(start_date: str) -> List[Dict]:
    df = ak.bond_zh_us_rate(start_date=start_date)
    if df is None or getattr(df, "empty", True):
        return []

    cleaned = df.astype(object).where(pd.notna(df), None)
    return cleaned.to_dict(orient="records")


def load_existing_records(output_path: Path) -> List[Dict]:
    if not output_path.exists():
        return []

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid archive payload in {output_path}: expected object")
    if "records" not in payload:
        raise ValueError(f"invalid archive payload in {output_path}: missing records")
    records = payload["records"]
    if not isinstance(records, list):
        raise ValueError(f"invalid archive payload in {output_path}: records must be a list")
    return [record for record in records if isinstance(record, dict)]


def build_archive_payload(
    source: str,
    identity: Dict[str, str],
    records: List[Dict],
    updated_at: str,
) -> Dict[str, object]:
    return {
        "source": source,
        **(identity or {}),
        "updated_at": updated_at,
        "records": records,
    }


def write_archive_file(
    output_path: Path | str,
    source: str,
    identity: Dict[str, str],
    records: List[Dict],
    updated_at: str,
) -> bool:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    payload = build_archive_payload(source, identity, records, updated_at)
    serialized = json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default) + "\n"

    if output_path.exists() and output_path.read_text(encoding="utf-8") == serialized:
        return False

    output_path.write_text(serialized, encoding="utf-8")
    return True


def _json_default(value: object) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def refresh_index_dataset(
    archive_root: Path,
    dataset_name: str,
    index_code: str,
    source_url: str,
    merge_key: str,
    updated_at: str,
) -> List[Path]:
    output_path = archive_root / dataset_name / f"{index_code}.json"
    existing_records = load_existing_records(output_path)
    incoming_records = fetch_index_archive_records(
        dataset_name=dataset_name,
        index_code=index_code,
        url=source_url,
    )
    merged_records = merge_records_by_key(existing_records, incoming_records, key=merge_key)
    if merged_records == existing_records:
        return []
    changed = write_archive_file(
        output_path=output_path,
        source=source_url,
        identity={"index_code": index_code},
        records=merged_records,
        updated_at=updated_at,
    )
    return [output_path] if changed else []


def refresh_bond_dataset(archive_root: Path, updated_at: str, start_date: str) -> List[Path]:
    output_path = archive_root / "bond_10y" / "china_10y.json"
    existing_records = load_existing_records(output_path)
    incoming_records = fetch_bond_archive_records(start_date=start_date)
    merged_records = merge_records_by_key(existing_records, incoming_records, key="日期")
    if merged_records == existing_records:
        return []
    changed = write_archive_file(
        output_path=output_path,
        source="akshare.bond_zh_us_rate",
        identity={"series": "china_10y"},
        records=merged_records,
        updated_at=updated_at,
    )
    return [output_path] if changed else []


def fetch_fx_archive_records() -> List[Dict]:
    df = ak.forex_hist_em(symbol="USDCNH").copy()
    if df is None or getattr(df, "empty", True):
        return []
    df["日期"] = pd.to_datetime(df["日期"], errors="coerce")
    df["最新价"] = pd.to_numeric(df["最新价"], errors="coerce")
    cleaned = df.astype(object).where(pd.notna(df), None)
    return cleaned.to_dict(orient="records")


def refresh_fx_dataset(archive_root: Path, updated_at: str) -> List[Path]:
    output_path = archive_root / "fx" / "usd_cnh.json"
    existing_records = load_existing_records(output_path)
    incoming_records = run_with_retry("fx_archive", fetch_fx_archive_records)
    merged_records = merge_records_by_key(existing_records, incoming_records, key="日期")
    if merged_records == existing_records:
        return []
    changed = write_archive_file(
        output_path=output_path,
        source="akshare.forex_hist_em",
        identity={"series": "usd_cnh"},
        records=merged_records,
        updated_at=updated_at,
    )
    return [output_path] if changed else []


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Refresh local archive datasets.")
    parser.add_argument("--config", default="config.yaml")
    return parser


def now_iso() -> str:
    return datetime.now(BEIJING_TZ).isoformat()


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        targets = load_config(args.config)
        index_codes = resolve_archive_index_codes(targets)
        updated_at = now_iso()
        current_time = datetime.fromisoformat(updated_at)
        changed_paths: List[Path] = []

        for index_code in index_codes:
            changed_paths.extend(
                refresh_index_dataset(
                    archive_root=ARCHIVE_ROOT,
                    dataset_name="index_eod",
                    index_code=index_code,
                    source_url=build_index_eod_price_url(index_code),
                    merge_key="trdDt",
                    updated_at=updated_at,
                )
            )
            changed_paths.extend(
                refresh_index_dataset(
                    archive_root=ARCHIVE_ROOT,
                    dataset_name="index_dividend_ratio",
                    index_code=index_code,
                    source_url=build_index_dividend_yield_url(index_code),
                    merge_key="trdDt",
                    updated_at=updated_at,
                )
            )
            changed_paths.extend(
                refresh_index_dataset(
                    archive_root=ARCHIVE_ROOT,
                    dataset_name="index_valuation_percentile",
                    index_code=index_code,
                    source_url=build_index_valuation_percentile_url(index_code),
                    merge_key="trdDt",
                    updated_at=updated_at,
                )
            )

        bond_start_date = (current_time - timedelta(days=365 * 11)).strftime("%Y%m%d")
        changed_paths.extend(
            refresh_bond_dataset(
                archive_root=ARCHIVE_ROOT,
                updated_at=updated_at,
                start_date=bond_start_date,
            )
        )
        changed_paths.extend(
            refresh_fx_dataset(
                archive_root=ARCHIVE_ROOT,
                updated_at=updated_at,
            )
        )
        return 0
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
