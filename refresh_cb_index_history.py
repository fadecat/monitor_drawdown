from __future__ import annotations

import json

import cb_index_history as history


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

    if next_text == previous_text:
        print("[INFO] 无变化，跳过写盘")
        return 0

    history.MARKET_TEMPERATURE_HISTORY_JSON.write_text(next_text, encoding="utf-8")
    print(f"[INFO] 归档已更新: {history.MARKET_TEMPERATURE_HISTORY_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
