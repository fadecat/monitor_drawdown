"""
本地预览脚本：用真实数据生成邮件 HTML + Webhook Markdown，不实际发送。

输出文件:
  email_preview.html          — 邮件 HTML 预览
  preview_webhook_payload.json — Webhook payload
  preview_webhook_message.md  — Webhook Markdown 正文
  preview_webhook_run.log     — 完整运行日志

用法:
  python preview_webhook_message.py
  python preview_webhook_message.py --simulate-missing-today  # 模拟 free-api 缺少当日价格
  python preview_webhook_message.py --force-triggered          # 强制所有标的进入告警（忽略阈值）
"""

import argparse
import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from datetime import timedelta
from pathlib import Path
from typing import Dict, List, Optional

import local_env
import monitor_drawdown as md


class TeeStream:
    def __init__(self, *streams) -> None:
        self.streams = streams

    def write(self, data: str) -> int:
        for stream in self.streams:
            stream.write(data)
        return len(data)

    def flush(self) -> None:
        for stream in self.streams:
            stream.flush()

    def isatty(self) -> bool:
        return any(getattr(s, "isatty", lambda: False)() for s in self.streams)


def drop_current_day_row(df, current_time):
    if df is None or df.empty:
        return df, 0
    trimmed = df.copy()
    trimmed["date"] = md.pd.to_datetime(trimmed["date"], errors="coerce")
    current_date = md.pd.Timestamp(current_time.date())
    mask = trimmed["date"].dt.normalize() == current_date
    return trimmed.loc[~mask].reset_index(drop=True), int(mask.sum())


def run_preview(simulate_missing_today: bool = False, force_triggered: bool = False) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    env_path = Path(".env.local")
    local_values = local_env.load_local_env(str(env_path))
    config_path = local_env.get_env_value("CONFIG_PATH", local_values, "./config.yaml")

    if env_path.exists():
        print(f"[INFO] 已加载本地配置文件: {env_path}")
    else:
        print(f"[INFO] 未找到本地配置文件: {env_path}，仅使用系统环境变量。")

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

    # 10年期国债收益率（全局一次）
    cn_10y_yield: Optional[float] = None
    cn_10y_bond_history = None
    try:
        cn_10y_yield = md.fetch_cn_10y_bond_yield()
        if cn_10y_yield is not None:
            print(f"[INFO] 10年期国债收益率: {cn_10y_yield:.4f}%")
        else:
            print("[WARN] 10年期国债收益率获取为空，股债收益差将不显示")
        cn_10y_bond_history = md.fetch_cn_10y_bond_history()
        print(f"[INFO] 10年期国债历史数据: {len(cn_10y_bond_history)} 条")
    except Exception as exc:
        print(f"[WARN] 10年期国债数据获取失败: {exc}")

    # 集思录（etf/index 类型需要）
    jisilu_rows = None
    has_patch_targets = any(
        str(t.get("type", "")).strip().lower() in {"etf", "index"} for t in targets
    )
    if has_patch_targets:
        jisilu_username = local_env.get_env_value("JISILU_USERNAME", local_values)
        jisilu_password = local_env.get_env_value("JISILU_PASSWORD", local_values)
        if jisilu_username and jisilu_password:
            try:
                jisilu_rows = md.fetch_jisilu_etf_rows(jisilu_username, jisilu_password)
                print(f"[INFO] 已加载集思录 ETF 列表，共 {len(jisilu_rows)} 条。")
            except Exception as exc:
                print(f"[WARN] 集思录 ETF 列表加载失败，预览将不补当日价格: {exc}")
        else:
            print("[WARN] 未配置 JISILU_USERNAME/JISILU_PASSWORD，预览将不补当日价格。")

    triggered: List[Dict] = []
    valuation_items: List[Dict] = []

    for target in targets:
        name = str(target.get("name", "")).strip()
        code = str(target.get("code", "")).strip()
        target_type = str(target.get("type", "")).strip().lower()
        threshold = float(target.get("threshold", 0.08))
        lookback_days = int(target.get("lookback_days", 120))

        if not name or not code or target_type not in {"etf", "index", "valuation"}:
            print(f"[ERROR] 配置不完整或类型非法，已跳过: {target}")
            continue

        # --- valuation only ---
        if target_type == "valuation":
            print(f"[INFO] 估值概览: {name} ({code})")
            try:
                metrics = md.fetch_target_index_metrics(target)
                if metrics:
                    item: Dict = {"name": name, "code": code}
                    item.update(metrics)
                    if cn_10y_yield is not None:
                        md.attach_equity_bond_ratio(item, cn_10y_yield)
                    if cn_10y_bond_history is not None:
                        md.attach_equity_bond_spread(item, cn_10y_bond_history)
                    valuation_items.append(item)
                    print(f"[INFO] {name} ({code}) 股息率={metrics.get('index_dividend_yield')}, "
                          f"估值日期={metrics.get('index_valuation_date')}")
                else:
                    print(f"[WARN] {name} ({code}) 估值指标为空，跳过")
            except Exception as exc:
                print(f"[ERROR] {name} ({code}) 估值指标获取失败: {exc}")
            continue

        # --- etf / index ---
        print(f"[INFO] 开始预览: {name} ({code}), type={target_type}, "
              f"threshold={threshold:.2%}, lookback={lookback_days}")
        try:
            if target_type == "etf":
                df = md.fetch_etf_data(code, start_str, end_str)
                if simulate_missing_today:
                    df, n = drop_current_day_row(df, current_time)
                    print(f"[INFO] 模拟缺少当日: 移除 {n} 条")
                if jisilu_rows:
                    df, patch = md.patch_etf_dataframe_with_jisilu(df, code, jisilu_rows, current_time=current_time)
                    if patch:
                        print(f"[INFO] 集思录补齐 ETF: {patch['fund_nm']}({patch['fund_id']}) -> {patch['close']:.4f}")
            else:
                df = md.fetch_index_data(code, start_str, end_str)
                if simulate_missing_today:
                    df, n = drop_current_day_row(df, current_time)
                    print(f"[INFO] 模拟缺少当日: 移除 {n} 条")
                if jisilu_rows:
                    jisilu_etf_code = str(target.get("jisilu_etf_code") or "").strip() or None
                    df, patch = md.patch_index_dataframe_with_jisilu(
                        df, code, jisilu_rows, current_time=current_time, fallback_etf_code=jisilu_etf_code
                    )
                    if patch:
                        print(f"[INFO] 集思录补齐指数: {patch['fund_nm']}({patch['fund_id']}) "
                              f"ETF涨跌={patch['etf_return']:.2%}")

            if df.empty:
                print(f"[WARN] {name} ({code}) 无有效数据，跳过")
                continue

            dividend_yield_info: Optional[Dict] = None
            if md.resolve_target_index_code(target):
                try:
                    dividend_yield_info = md.fetch_target_index_dividend_yield(target)
                    if dividend_yield_info:
                        print(f"[INFO] {name} 股息率={dividend_yield_info.get('index_dividend_yield')}, "
                              f"估值日期={dividend_yield_info.get('index_valuation_date')}")
                except Exception as exc:
                    print(f"[WARN] {name} 指数指标获取失败: {exc}")

            result = md.compute_drawdown(df, lookback_days)
            drawdown = result["drawdown"]
            print(f"[INFO] {name} ({code}) 最新={result['current_date']}, "
                  f"价格={result['current_price']:.4f}, 回撤={drawdown:.2%}")

            if force_triggered or drawdown >= threshold:
                triggered_item: Dict = {
                    "name": name, "code": code,
                    "drawdown": drawdown,
                    "current_price": result["current_price"],
                    "peak_price": result["peak_price"],
                    "peak_date": result["peak_date"],
                }
                if dividend_yield_info:
                    triggered_item.update(dividend_yield_info)
                if cn_10y_yield is not None:
                    md.attach_equity_bond_ratio(triggered_item, cn_10y_yield)
                if cn_10y_bond_history is not None:
                    md.attach_equity_bond_spread(triggered_item, cn_10y_bond_history)
                triggered.append(triggered_item)
                print(f"[ALERT] {'(强制)' if force_triggered else ''}触发: {name} 回撤 {drawdown:.2%}")
            else:
                print(f"[INFO] 未触发: {name} 回撤 {drawdown:.2%} < {threshold:.2%}")

        except Exception as exc:
            print(f"[ERROR] 预览 {name} ({code}) 失败: {exc}")
            continue

    # --- 写出文件 ---
    email_html_path = Path("email_preview.html")
    email_html = md.build_email_html_content(
        triggered, valuation_items=valuation_items, current_time=current_time
    )
    email_html_path.write_text(email_html, encoding="utf-8")
    print(f"\n[INFO] 邮件预览已写入: {email_html_path}")

    if triggered:
        payload = md.build_webhook_payload(triggered, current_time=current_time)
        payload_path = Path("preview_webhook_payload.json")
        markdown_path = Path("preview_webhook_message.md")
        payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        markdown_path.write_text(payload["markdown"]["content"], encoding="utf-8")
        print(f"[INFO] Webhook payload 已写入: {payload_path}")
        print(f"[INFO] Webhook Markdown 已写入: {markdown_path}")
        print(f"\n[INFO] 共 {len(triggered)} 个告警标的，{len(valuation_items)} 个估值概览标的")
    else:
        print(f"\n[INFO] 当前无回撤告警触发（估值概览标的 {len(valuation_items)} 个）。")
        print("[INFO] 使用 --force-triggered 可强制所有标的进入告警以预览完整邮件。")

    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="本地预览邮件和 Webhook，不实际发送")
    parser.add_argument("--simulate-missing-today", action="store_true",
                        help="模拟 free-api 缺少当日数据，再用集思录补齐")
    parser.add_argument("--force-triggered", action="store_true",
                        help="强制所有 etf/index 标的进入告警（忽略回撤阈值）")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    log_path = Path("preview_webhook_run.log")
    with log_path.open("w", encoding="utf-8") as log_file:
        tee = TeeStream(sys.stdout, log_file)
        tee_err = TeeStream(sys.stderr, log_file)
        with redirect_stdout(tee), redirect_stderr(tee_err):
            return run_preview(
                simulate_missing_today=args.simulate_missing_today,
                force_triggered=args.force_triggered,
            )


if __name__ == "__main__":
    raise SystemExit(main())
