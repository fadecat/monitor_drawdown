import json
import sys
from pathlib import Path
from datetime import timedelta

import monitor_drawdown as md


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    config_path = md.os.getenv("CONFIG_PATH", "./config.yaml")
    print(f"[INFO] 使用配置文件: {config_path}")

    targets = md.load_config(config_path)
    if not targets:
        print("[WARN] 未配置任何监控标的，退出。")
        return 1

    current_time = md.now_in_beijing()
    end = current_time.date()
    start = end - timedelta(days=365)
    start_str = start.strftime("%Y%m%d")
    end_str = end.strftime("%Y%m%d")
    print(f"[INFO] 当前北京时间: {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"[INFO] 拉取数据区间: {start_str} - {end_str}")

    triggered: list[dict] = []
    has_patch_targets = any(str(target.get("type", "")).strip().lower() in {"etf", "index"} for target in targets)
    jisilu_rows = None

    if has_patch_targets:
        jisilu_username = md.os.getenv("JISILU_USERNAME", "").strip()
        jisilu_password = md.os.getenv("JISILU_PASSWORD", "").strip()
        if jisilu_username and jisilu_password:
            try:
                jisilu_rows = md.fetch_jisilu_etf_rows(jisilu_username, jisilu_password)
                print(f"[INFO] 已加载集思录 ETF 列表，共 {len(jisilu_rows)} 条。")
            except Exception as exc:  # noqa: BLE001
                print(f"[WARN] 集思录 ETF 列表加载失败，预览将不补当日价格: {exc}")
        else:
            print("[WARN] 未配置 JISILU_USERNAME/JISILU_PASSWORD，预览将不补当日价格。")

    for target in targets:
        name = str(target.get("name", "")).strip()
        code = str(target.get("code", "")).strip()
        target_type = str(target.get("type", "")).strip().lower()
        threshold = float(target.get("threshold", 0.08))
        lookback_days = int(target.get("lookback_days", 120))

        if not name or not code or target_type not in {"etf", "index"}:
            print(f"[ERROR] 配置不完整或类型非法，已跳过: {target}")
            continue

        print(f"[INFO] 开始预览: {name} ({code}), type={target_type}, threshold={threshold:.2%}, lookback={lookback_days}")
        try:
            if target_type == "etf":
                df = md.fetch_etf_data(code, start_str, end_str)
                if jisilu_rows:
                    df, patch = md.patch_etf_dataframe_with_jisilu(df, code, jisilu_rows, current_time=current_time)
                    if patch:
                        print(
                            f"[INFO] 已用集思录补齐 ETF: {patch['fund_nm']}({patch['fund_id']}) "
                            f"-> {patch['close']:.4f}"
                        )
            else:
                df = md.fetch_index_data(code, start_str, end_str)
                if jisilu_rows:
                    df, patch = md.patch_index_dataframe_with_jisilu(df, code, jisilu_rows, current_time=current_time)
                    if patch:
                        print(
                            f"[INFO] 已用集思录 ETF 补齐指数: {patch['fund_nm']}({patch['fund_id']}) "
                            f"-> {patch['close']:.4f}"
                        )

            if df.empty:
                print(f"[WARN] {name} ({code}) 未获取到有效数据，跳过。")
                continue

            result = md.compute_drawdown(df, lookback_days)
            drawdown = result["drawdown"]
            print(
                f"[INFO] 预览结果: {name} ({code}) 最新日期 {result['current_date']}，"
                f"当前价格 {result['current_price']:.4f}，回撤 {drawdown:.2%}"
            )

            if drawdown >= threshold:
                triggered.append(
                    {
                        "name": name,
                        "code": code,
                        "drawdown": drawdown,
                        "current_price": result["current_price"],
                        "peak_price": result["peak_price"],
                        "peak_date": result["peak_date"],
                    }
                )
        except Exception as exc:  # noqa: BLE001
            print(f"[ERROR] 预览 {name} ({code}) 失败: {exc}")
            continue

    if not triggered:
        print("[INFO] 当前无触发项，不会推送消息。")
        return 0

    payload = md.build_webhook_payload(triggered, current_time=current_time)
    payload_path = Path("preview_webhook_payload.json")
    markdown_path = Path("preview_webhook_message.md")
    payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(payload["markdown"]["content"], encoding="utf-8")

    print(f"[INFO] 共有 {len(triggered)} 个触发项，下面是将要推送的 payload:")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print("")
    print("[INFO] Markdown 正文预览:")
    print(payload["markdown"]["content"])
    print("")
    print(f"[INFO] 已写入文件: {payload_path}")
    print(f"[INFO] 已写入文件: {markdown_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
