from __future__ import annotations

import json
import os

import requests

import cb_index_history as history


REFRESH_WEBHOOK_ENV = "CB_INDEX_REFRESH_WEBHOOK_URL"


def build_refresh_webhook_payload(
    *,
    stats: dict[str, int],
    changed: bool,
    latest_date: str | None,
) -> dict[str, object]:
    status_text = "已更新" if changed else "无变化"
    latest_text = latest_date or "--"
    content = "\n".join(
        [
            "## 转债等权历史归档完成",
            f"- status: `{status_text}`",
            f"- history: `{stats['history']}`",
            f"- updated: `{stats['updated']}`",
            f"- added: `{stats['added']}`",
            f"- latest: `{latest_text}`",
        ]
    )
    return {
        "msgtype": "markdown",
        "markdown": {"content": content},
    }


def notify_refresh_webhook(
    *,
    stats: dict[str, int],
    changed: bool,
    latest_date: str | None,
) -> None:
    webhook_url = os.getenv(REFRESH_WEBHOOK_ENV, "").strip()
    if not webhook_url:
        print(f"[INFO] 未配置 {REFRESH_WEBHOOK_ENV}，跳过 webhook 通知")
        return

    payload = build_refresh_webhook_payload(
        stats=stats,
        changed=changed,
        latest_date=latest_date,
    )
    response = requests.post(webhook_url, json=payload, timeout=15)
    response.raise_for_status()
    print("[INFO] 企业微信 webhook 通知已发送")


def main() -> int:
    print(f"[INFO] 开始刷新转债等权历史: {history.MARKET_TEMPERATURE_HISTORY_JSON}")
    if history.MARKET_TEMPERATURE_HISTORY_JSON.exists():
        previous_text = history.MARKET_TEMPERATURE_HISTORY_JSON.read_text(encoding="utf-8")
    else:
        previous_text = ""
    merged, stats = history.build_merged_history()
    next_text = json.dumps(merged, ensure_ascii=False, indent=2) + "\n"

    print(
        "[INFO] merge stats: "
        f"history={stats['history']} updated={stats['updated']} added={stats['added']}"
    )
    latest_date = str(merged[-1].get("date")) if merged else None

    if next_text == previous_text:
        print("[INFO] 无变化，跳过写盘")
        notify_refresh_webhook(stats=stats, changed=False, latest_date=latest_date)
        return 0

    history.MARKET_TEMPERATURE_HISTORY_JSON.write_text(next_text, encoding="utf-8")
    print(f"[INFO] 归档已更新: {history.MARKET_TEMPERATURE_HISTORY_JSON}")
    notify_refresh_webhook(stats=stats, changed=True, latest_date=latest_date)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
