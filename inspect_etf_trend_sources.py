from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from html import unescape
from pathlib import Path
from typing import Any

import requests

import analyze_etf_com_cn_period_returns as etf_analysis
import etf_trend_analysis as trend_analysis
import monitor_drawdown as md


SEARCH_ALL_URL = "https://www.etf.com.cn/api/etf-api-service/search/all"
OUTPUT_ROOT = Path(".test_artifacts/etf_trend_sources")
SERIES_DIR = OUTPUT_ROOT / "series"
SERIES_ANALYSIS_DIR = OUTPUT_ROOT / "series_analysis"
MANUAL_TREND_BENCHMARKS_PATH = OUTPUT_ROOT / "manual_trend_benchmarks.json"
TREND_METRICS_SUMMARY_PATH = OUTPUT_ROOT / "trend_metrics_summary.json"
TREND_BENCHMARK_DIFF_PATH = OUTPUT_ROOT / "trend_benchmark_diff.json"
REQUEST_TIMEOUT = 15
LOOKBACK_DAYS = 365

DEFAULT_TARGETS: list[dict[str, Any]] = [
    {"label": "通信ETF", "search_keywords": ["通信", "通信ETF"], "kline_kind": "auto"},
    {"label": "煤炭ETF", "search_keywords": ["煤炭", "煤炭ETF"], "kline_kind": "auto"},
    {"label": "创成长", "search_keywords": ["创成长", "创业成长"], "kline_kind": "auto"},
    {"label": "纳指ETF", "search_keywords": ["纳指", "纳指ETF"], "kline_kind": "auto"},
    {"label": "创业板50", "search_keywords": ["创业板50"], "kline_kind": "auto"},
    {"label": "人工智能", "search_keywords": ["人工智能"], "kline_kind": "auto"},
    {"label": "标普500", "search_keywords": ["标普500"], "kline_kind": "auto"},
    {"label": "半导体ETF", "search_keywords": ["半导体", "半导体ETF"], "kline_kind": "auto"},
    {"label": "恒生科技", "search_keywords": ["恒生科技"], "kline_kind": "auto"},
    {"label": "沪深300", "search_keywords": ["沪深300"], "kline_kind": "auto"},
    {"label": "科创100", "search_keywords": ["科创100"], "kline_kind": "auto"},
    {"label": "科创50", "search_keywords": ["科创50"], "kline_kind": "auto"},
    {"label": "30年国债", "search_keywords": ["30年国债"], "kline_kind": "auto"},
    {"label": "银行ETF", "search_keywords": ["银行", "银行ETF"], "kline_kind": "auto"},
    {"label": "红利低波", "search_keywords": ["红利低波"], "kline_kind": "auto"},
    {"label": "恒生ETF", "search_keywords": ["恒生ETF", "恒生"], "kline_kind": "auto"},
    {"label": "有色金属", "search_keywords": ["有色金属"], "kline_kind": "auto"},
    {"label": "上证指数", "search_keywords": ["上证指数"], "kline_kind": "auto"},
    {"label": "机器人ETF", "search_keywords": ["机器人", "机器人ETF"], "kline_kind": "auto"},
    {"label": "中证1000", "search_keywords": ["中证1000"], "kline_kind": "auto"},
    {"label": "证券ETF", "search_keywords": ["证券", "证券ETF"], "kline_kind": "auto"},
    {"label": "豆粕ETF", "search_keywords": ["豆粕", "豆粕ETF"], "kline_kind": "auto"},
    {"label": "中证2000", "search_keywords": ["中证2000"], "kline_kind": "auto"},
    {"label": "黄金ETF", "search_keywords": ["黄金", "黄金ETF"], "kline_kind": "auto"},
    {"label": "光伏ETF", "search_keywords": ["光伏", "光伏ETF"], "kline_kind": "auto"},
    {"label": "酒ETF", "search_keywords": ["酒", "酒ETF"], "kline_kind": "auto"},
    {"label": "石油ETF", "search_keywords": ["石油", "石油ETF"], "kline_kind": "auto"},
    {"label": "新能源车", "search_keywords": ["新能源车"], "kline_kind": "auto"},
    {"label": "医疗ETF", "search_keywords": ["医疗", "医疗ETF"], "kline_kind": "auto"},
    {"label": "军工ETF", "search_keywords": ["军工", "军工ETF"], "kline_kind": "auto"},
]


def log(level: str, message: str) -> None:
    print(f"[{level}] {message}")


def ensure_output_dirs() -> None:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    SERIES_DIR.mkdir(parents=True, exist_ok=True)
    SERIES_ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)


def today_range_strings() -> tuple[str, str]:
    end_date = datetime.today().date()
    start_date = end_date - timedelta(days=LOOKBACK_DAYS)
    return start_date.strftime("%Y%m%d"), end_date.strftime("%Y%m%d")


def dedupe_keep_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def normalize_targets(raw_targets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in raw_targets:
        label = str(item.get("label") or "").strip()
        keywords = item.get("search_keywords") or []
        kline_kind = str(item.get("kline_kind") or "auto").strip() or "auto"
        if not label:
            continue
        normalized.append(
            {
                "label": label,
                "search_keywords": dedupe_keep_order([str(keyword) for keyword in keywords] or [label]),
                "kline_kind": kline_kind,
            }
        )
    return normalized


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def format_optional_float(value: Any) -> str:
    if value in {None, ""}:
        return "n/a"
    try:
        return f"{float(value):.4f}"
    except (TypeError, ValueError):
        return "n/a"


def remove_file_if_exists(path: Path) -> None:
    if path.exists():
        path.unlink()


TAG_RE = re.compile(r"<[^>]+>")
THEME_TOKENS = [
    "煤炭",
    "通信",
    "半导体",
    "恒生",
    "黄金",
    "军工",
    "医疗",
    "石油",
    "银行",
    "证券",
    "光伏",
    "酒",
    "机器人",
    "人工智能",
    "新能源车",
    "沪深300",
    "中证1000",
    "中证2000",
    "科创50",
    "科创100",
    "创业板50",
    "纳指",
    "标普500",
    "30年国债",
    "有色金属",
    "红利低波",
]


def strip_html(text: Any) -> str:
    return unescape(TAG_RE.sub("", str(text or ""))).strip()


def extract_theme_hits(*parts: str) -> list[str]:
    haystack = " ".join(part for part in parts if part)
    return [token for token in THEME_TOKENS if token in haystack]


def search_all(keyword: str) -> dict[str, Any]:
    response = requests.post(
        SEARCH_ALL_URL,
        json={"keyword": keyword, "page": 1, "pageSize": 10},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError(f"unexpected search payload type: {type(payload).__name__}")
    return payload


def normalize_etf_candidate(row: dict[str, Any], keyword: str) -> dict[str, Any]:
    return {
        "kind": "etf",
        "keyword": keyword,
        "code": str(row.get("trdCode") or row.get("originalTrdCode") or "").strip(),
        "original_code": str(row.get("originalTrdCode") or "").strip(),
        "name": strip_html(row.get("fundSht")),
        "raw_name": str(row.get("fundSht") or ""),
        "fund_name": strip_html(row.get("fundName")),
        "manager": strip_html(row.get("manager")),
        "theme_hits": extract_theme_hits(strip_html(row.get("fundSht")), strip_html(row.get("fundName"))),
    }


def normalize_index_candidate(row: dict[str, Any], keyword: str) -> dict[str, Any]:
    return {
        "kind": "index",
        "keyword": keyword,
        "code": str(row.get("originalTrdCode") or row.get("trdCode") or "").strip(),
        "display_code": str(row.get("trdCode") or "").strip(),
        "name": strip_html(row.get("indexSht")),
        "raw_name": str(row.get("indexSht") or ""),
        "index_name": strip_html(row.get("indexName")),
        "theme_hits": extract_theme_hits(strip_html(row.get("indexSht")), strip_html(row.get("indexName"))),
    }


def collect_candidates_for_keyword(keyword: str) -> dict[str, Any]:
    payload = search_all(keyword)
    data = payload.get("data") or {}
    etf_rows = data.get("etfFundList", {}).get("data") or []
    index_rows = data.get("indexList", {}).get("data") or []
    out_rows = data.get("outIndexFundList", {}).get("data") or []
    return {
        "keyword": keyword,
        "success": bool(payload.get("success")),
        "message": str(payload.get("message") or ""),
        "etf_candidates": [
            normalize_etf_candidate(row, keyword) for row in etf_rows if isinstance(row, dict)
        ],
        "index_candidates": [
            normalize_index_candidate(row, keyword) for row in index_rows if isinstance(row, dict)
        ],
        "out_index_debug": [
            {
                "code": str(row.get("trdCode") or row.get("originalTrdCode") or "").strip(),
                "name": strip_html(row.get("fundSht")),
            }
            for row in out_rows
            if isinstance(row, dict)
        ],
    }


def build_target_phrases(label: str, search_keywords: list[str]) -> list[str]:
    return dedupe_keep_order([label, *search_keywords])


def extract_target_theme_hits(theme_hits: list[str], target_phrases: list[str]) -> list[str]:
    matched_hits: list[str] = []
    for hit in theme_hits:
        if any(hit == phrase or hit in phrase or phrase in hit for phrase in target_phrases if phrase):
            matched_hits.append(hit)
    return dedupe_keep_order(matched_hits)


def is_focused_index_name(name: str, target_phrases: list[str]) -> bool:
    for phrase in target_phrases:
        if name in {phrase, f"{phrase}指数"}:
            return True
    return False


def is_label_aligned_candidate(candidate: dict[str, Any], label: str) -> bool:
    kind = str(candidate.get("kind") or "")
    name = str(candidate.get("name") or "")
    if "ETF" in label:
        return kind == "etf" and "ETF" in name
    return kind == "index" and is_focused_index_name(
        name,
        build_target_phrases(label, [label]),
    )


def score_candidate(candidate: dict[str, Any], label: str, search_keywords: list[str]) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    name = str(candidate.get("name") or "")
    secondary_name = str(candidate.get("fund_name") or candidate.get("index_name") or "")
    haystack = " ".join([name, secondary_name])
    target_phrases = build_target_phrases(label, search_keywords)

    if name == label:
        score += 100
        reasons.append("exact_label_match")

    for keyword in search_keywords:
        if name == keyword:
            score += 90
            reasons.append(f"exact_keyword_match:{keyword}")
        elif keyword in haystack and keyword not in {"ETF", "指数"}:
            score += 30
            reasons.append(f"keyword_contains:{keyword}")

    theme_hits = candidate.get("theme_hits") or []
    target_theme_hits = extract_target_theme_hits(theme_hits, target_phrases)
    if target_theme_hits:
        score += 20 * len(target_theme_hits)
        reasons.append("target_theme_hits:" + ",".join(target_theme_hits))

    if "ETF" in label and candidate.get("kind") == "etf":
        score += 15
        reasons.append("etf_label_bonus")
    if "ETF" not in label and candidate.get("kind") == "index":
        score += 15
        reasons.append("index_label_bonus")
    if is_label_aligned_candidate(candidate, label):
        score += 25
        reasons.append("label_aligned_kind_bonus")

    if candidate.get("kind") == "etf" and "ETF" in name and any(
        keyword in name for keyword in search_keywords if keyword not in {"ETF", "指数"}
    ):
        score += 10
        reasons.append("focused_etf_name_bonus")

    if candidate.get("kind") == "index" and any(
        keyword in name for keyword in search_keywords if keyword not in {"ETF", "指数"}
    ):
        if not is_focused_index_name(name, target_phrases):
            score -= 25
            reasons.append("index_extra_qualifier_penalty")

    if "ETF" in name and not theme_hits and all(
        keyword not in haystack for keyword in search_keywords if keyword not in {"ETF", "指数"}
    ):
        score -= 40
        reasons.append("generic_etf_penalty")

    return score, reasons


def is_credible(score: int, reasons: list[str]) -> bool:
    _ = score
    return any(reason.startswith("exact_") for reason in reasons) or any(
        reason.startswith(prefix)
        for prefix in ("keyword_contains:", "target_theme_hits:")
        for reason in reasons
    )


def pick_best_candidate(
    candidates: list[dict[str, Any]], label: str, search_keywords: list[str]
) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    for candidate in candidates:
        score, reasons = score_candidate(candidate, label, search_keywords)
        enriched = dict(candidate)
        enriched["score"] = score
        enriched["score_reasons"] = reasons
        enriched["credible"] = is_credible(score, reasons)
        if best is None or enriched["score"] > best["score"]:
            best = enriched
    return best


def select_primary(
    label: str, etf_candidate: dict[str, Any] | None, index_candidate: dict[str, Any] | None
) -> dict[str, Any] | None:
    if etf_candidate and etf_candidate.get("credible") and "ETF" in label:
        return {
            "kind": etf_candidate["kind"],
            "code": etf_candidate["code"],
            "name": etf_candidate["name"],
            "reason": "preferred_kind_candidate",
            "score": etf_candidate["score"],
        }
    if (
        index_candidate
        and index_candidate.get("credible")
        and "ETF" not in label
        and is_label_aligned_candidate(index_candidate, label)
    ):
        return {
            "kind": index_candidate["kind"],
            "code": index_candidate["code"],
            "name": index_candidate["name"],
            "reason": "preferred_kind_candidate",
            "score": index_candidate["score"],
        }
    credible_candidates = [
        candidate for candidate in [etf_candidate, index_candidate] if candidate and candidate.get("credible")
    ]
    if credible_candidates:
        winner = max(credible_candidates, key=lambda item: int(item["score"]))
        return {
            "kind": winner["kind"],
            "code": winner["code"],
            "name": winner["name"],
            "reason": "fallback_kind_candidate",
            "score": winner["score"],
        }
    return None


def resolve_target(target: dict[str, Any]) -> dict[str, Any]:
    label = target["label"]
    search_keywords = target["search_keywords"]
    search_attempts: list[dict[str, Any]] = []
    best_etf: dict[str, Any] | None = None
    best_index: dict[str, Any] | None = None
    had_exception = False

    for keyword in search_keywords:
        log("INFO", f"search keyword={keyword}")
        try:
            attempt = collect_candidates_for_keyword(keyword)
            search_attempts.append(attempt)
            current_best_etf = pick_best_candidate(attempt["etf_candidates"], label, search_keywords)
            current_best_index = pick_best_candidate(
                attempt["index_candidates"], label, search_keywords
            )
            if current_best_etf and (best_etf is None or current_best_etf["score"] > best_etf["score"]):
                best_etf = current_best_etf
            if current_best_index and (
                best_index is None or current_best_index["score"] > best_index["score"]
            ):
                best_index = current_best_index
            if (best_etf and best_etf["credible"]) or (best_index and best_index["credible"]):
                break
        except Exception as exc:
            had_exception = True
            search_attempts.append({"keyword": keyword, "error": str(exc)})

    selected_primary = select_primary(label, best_etf, best_index)

    if selected_primary:
        status = "ok"
    elif search_attempts and all("error" in attempt for attempt in search_attempts) and had_exception:
        status = "search_failed"
    else:
        status = "unresolved"

    if status == "search_failed":
        error_text = "; ".join(
            str(attempt["error"]) for attempt in search_attempts if isinstance(attempt, dict) and "error" in attempt
        )
        log("ERROR", f"search failed label={label} reason={error_text}")
    if status == "unresolved":
        log("WARN", f"unresolved label={label}")

    return {
        "label": label,
        "search_keywords": search_keywords,
        "search_attempts": search_attempts,
        "etf_candidate": best_etf,
        "index_candidate": best_index,
        "selected_primary": selected_primary,
        "status": status,
    }


def normalize_series_frame(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped_by_date: dict[str, dict[str, Any]] = {}
    for row in records:
        date_text = str(row.get("date") or "").strip()
        close_value = row.get("close")
        if not date_text or close_value in {None, ""}:
            continue
        try:
            numeric_close = float(close_value)
        except (TypeError, ValueError):
            continue
        deduped_by_date[date_text] = {"date": date_text, "close": numeric_close}
    return [deduped_by_date[key] for key in sorted(deduped_by_date.keys())]


def load_etf_series(code: str) -> list[dict[str, Any]]:
    rows = etf_analysis.load_nav_rows(code)
    return normalize_series_frame(
        [
            {"date": str(row.get("trdDt") or "").strip(), "close": row.get("adjUnitNav")}
            for row in rows
            if isinstance(row, dict)
        ]
    )


def load_index_series(code: str) -> list[dict[str, Any]]:
    source_url = md.build_index_eod_price_url(code)
    rows = md.fetch_json_response("index_eod_price", source_url)
    frame = md.parse_index_eod_price_rows(rows)
    if frame.empty:
        return []
    records = frame.to_dict(orient="records")
    return normalize_series_frame(
        [
            {
                "date": record["date"].strftime("%Y-%m-%d"),
                "close": record["close"],
            }
            for record in records
        ]
    )


def fetch_selected_series(selected_primary: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    kind = selected_primary["kind"]
    code = selected_primary["code"]
    if kind == "etf":
        series = load_etf_series(code)
    elif kind == "index":
        series = load_index_series(code)
    else:
        raise ValueError(f"unsupported kind: {kind}")

    if not series:
        raise RuntimeError(f"empty ETF.com.cn series for {kind}:{code}")

    summary = {
        "status": "ok",
        "selected_kind": kind,
        "selected_code": code,
        "rows": len(series),
        "date_start": series[0]["date"],
        "date_end": series[-1]["date"],
        "latest_close": series[-1]["close"],
    }
    return series, summary


def materialize_kline(result: dict[str, Any]) -> dict[str, Any]:
    selected_primary = result.get("selected_primary")
    if not selected_primary:
        return {
            "label": result["label"],
            "status": result["status"],
            "selected_primary": None,
        }

    try:
        series, summary = fetch_selected_series(selected_primary)
        filename = f"{selected_primary['kind']}_{selected_primary['code']}.json"
        series_path = SERIES_DIR / filename
        write_json(series_path, series)
        return {
            "label": result["label"],
            "status": "ok",
            "selected_primary": selected_primary,
            "kline": summary,
            "series_file": str(series_path.as_posix()),
        }
    except Exception as exc:
        log("ERROR", f"kline failed label={result['label']} reason={exc}")
        return {
            "label": result["label"],
            "status": "kline_failed",
            "selected_primary": selected_primary,
            "error": str(exc),
        }


def materialize_trend_analysis(kline_result: dict[str, Any]) -> dict[str, Any]:
    selected_primary = kline_result.get("selected_primary")
    if kline_result.get("status") != "ok" or not selected_primary:
        return {
            "label": kline_result["label"],
            "status": kline_result["status"],
            "selected_primary": selected_primary,
        }

    try:
        series_path = Path(str(kline_result["series_file"]))
        series_records = read_json(series_path)
        analysis = trend_analysis.analyze_trend_series(series_records)
        latest_snapshot = trend_analysis.build_latest_trend_snapshot(analysis)
        analysis_filename = f"{selected_primary['kind']}_{selected_primary['code']}_analysis.json"
        analysis_path = SERIES_ANALYSIS_DIR / analysis_filename
        write_json(analysis_path, analysis)
        return {
            "label": kline_result["label"],
            "status": "ok",
            "selected_primary": selected_primary,
            "analysis_file": str(analysis_path.as_posix()),
            "latest_snapshot": latest_snapshot,
        }
    except Exception as exc:
        log("ERROR", f"trend analysis failed label={kline_result['label']} reason={exc}")
        return {
            "label": kline_result["label"],
            "status": "trend_failed",
            "selected_primary": selected_primary,
            "error": str(exc),
        }


def load_manual_trend_benchmarks(
    path: Path | None = None,
) -> list[dict[str, Any]]:
    resolved_path = MANUAL_TREND_BENCHMARKS_PATH if path is None else path
    if not resolved_path.exists():
        return []
    payload = read_json(resolved_path)
    if not isinstance(payload, list):
        raise ValueError(f"manual trend benchmarks must be a list: {resolved_path}")
    return [item for item in payload if isinstance(item, dict)]


def build_trend_benchmark_diffs(
    snapshots: list[dict[str, Any]], benchmarks: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    snapshot_by_label = {
        str(item.get("label") or "").strip(): item
        for item in snapshots
        if str(item.get("label") or "").strip()
    }
    diffs: list[dict[str, Any]] = []
    for benchmark in benchmarks:
        label = str(benchmark.get("label") or "").strip()
        snapshot = snapshot_by_label.get(label)
        if not snapshot:
            continue

        actual_bias20 = snapshot.get("bias20")
        expected_bias20 = benchmark.get("expected_bias20")
        bias20_diff = None
        if actual_bias20 is not None and expected_bias20 is not None:
            bias20_diff = round(float(actual_bias20) - float(expected_bias20), 4)

        actual_trend_state = snapshot.get("trend_state")
        expected_trend_state = benchmark.get("expected_trend_state")
        actual_transition_date = snapshot.get("latest_transition_date")
        expected_transition_date = benchmark.get("expected_transition_date")

        diffs.append(
            {
                "label": label,
                "as_of_date": benchmark.get("as_of_date") or snapshot.get("latest_date"),
                "actual_bias20": actual_bias20,
                "expected_bias20": expected_bias20,
                "bias20_diff": bias20_diff,
                "actual_trend_state": actual_trend_state,
                "expected_trend_state": expected_trend_state,
                "trend_state_match": actual_trend_state == expected_trend_state,
                "actual_transition_date": actual_transition_date,
                "expected_transition_date": expected_transition_date,
                "transition_date_match": actual_transition_date == expected_transition_date,
            }
        )
    return diffs


def build_summary(
    resolved: list[dict[str, Any]],
    kline_results: list[dict[str, Any]],
    trend_results: list[dict[str, Any]],
) -> str:
    ok_count = sum(1 for item in trend_results if item["status"] == "ok")
    unresolved_count = sum(1 for item in resolved if item["status"] == "unresolved")
    search_failed_count = sum(1 for item in resolved if item["status"] == "search_failed")
    kline_failed_count = sum(1 for item in kline_results if item["status"] == "kline_failed")
    trend_failed_count = sum(1 for item in trend_results if item["status"] == "trend_failed")

    lines = [
        "# ETF Trend Source Inspection",
        "",
        f"- total targets: {len(resolved)}",
        f"- ok: {ok_count}",
        f"- unresolved: {unresolved_count}",
        f"- search_failed: {search_failed_count}",
        f"- kline_failed: {kline_failed_count}",
        f"- trend_failed: {trend_failed_count}",
        "",
        "## Per Target",
        "",
    ]

    kline_by_label = {item["label"]: item for item in kline_results}
    trend_by_label = {item["label"]: item for item in trend_results}
    for item in resolved:
        label = item["label"]
        kline = kline_by_label.get(label, {})
        trend = trend_by_label.get(label, {})
        selected = item.get("selected_primary")
        selected_text = (
            f"{selected['kind']}:{selected['code']} {selected['name']}" if selected else "none"
        )
        latest_snapshot = trend.get("latest_snapshot") or {}
        lines.append(
            f"- {label}: resolve={item['status']} kline={kline.get('status', 'unknown')} "
            f"trend={latest_snapshot.get('trend_state') or 'n/a'} "
            f"bias20={format_optional_float(latest_snapshot.get('bias20'))} "
            f"transition={latest_snapshot.get('latest_transition_date') or 'n/a'} "
            f"selected={selected_text}"
        )

    return "\n".join(lines) + "\n"


def run() -> None:
    ensure_output_dirs()
    _ = today_range_strings()
    targets = normalize_targets(DEFAULT_TARGETS)
    write_json(OUTPUT_ROOT / "targets.json", targets)

    resolved_results = [resolve_target(target) for target in targets]
    candidate_payload = [
        {
            "label": item["label"],
            "search_keywords": item["search_keywords"],
            "search_attempts": item["search_attempts"],
        }
        for item in resolved_results
    ]
    write_json(OUTPUT_ROOT / "candidate_matches.json", candidate_payload)

    resolved_payload = [
        {
            "label": item["label"],
            "status": item["status"],
            "etf_candidate": item["etf_candidate"],
            "index_candidate": item["index_candidate"],
            "selected_primary": item["selected_primary"],
        }
        for item in resolved_results
    ]
    write_json(OUTPUT_ROOT / "resolved_instruments.json", resolved_payload)

    kline_results = [materialize_kline(item) for item in resolved_results]
    write_json(OUTPUT_ROOT / "kline_samples.json", kline_results)

    trend_results = [materialize_trend_analysis(item) for item in kline_results]
    write_json(OUTPUT_ROOT / "trend_analysis_results.json", trend_results)

    trend_metrics_summary = [
        {
            "label": item["label"],
            "selected_primary": item.get("selected_primary"),
            **(item.get("latest_snapshot") or {}),
        }
        for item in trend_results
        if item.get("status") == "ok"
    ]
    write_json(TREND_METRICS_SUMMARY_PATH, trend_metrics_summary)

    remove_file_if_exists(TREND_BENCHMARK_DIFF_PATH)
    try:
        benchmarks = load_manual_trend_benchmarks()
    except Exception as exc:
        log("WARN", f"skip trend benchmark diff reason={exc}")
        benchmarks = []
    if benchmarks:
        write_json(
            TREND_BENCHMARK_DIFF_PATH,
            build_trend_benchmark_diffs(trend_metrics_summary, benchmarks),
        )

    summary_text = build_summary(resolved_results, kline_results, trend_results)
    (OUTPUT_ROOT / "summary.md").write_text(summary_text, encoding="utf-8")
    log("INFO", f"artifacts written to {OUTPUT_ROOT}")


if __name__ == "__main__":
    run()
