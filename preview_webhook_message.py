import argparse
import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from datetime import timedelta

import local_env
import monitor_drawdown as md


class PreviewLogger:
    def emit(self, message: str = "") -> None:
        print(message)


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
        return any(getattr(stream, "isatty", lambda: False)() for stream in self.streams)


def drop_current_day_row(df, current_time):
    if df is None or df.empty:
        return df, 0

    trimmed_df = df.copy()
    trimmed_df["date"] = md.pd.to_datetime(trimmed_df["date"], errors="coerce")
    current_date = md.pd.Timestamp(current_time.date())
    mask = trimmed_df["date"].dt.normalize() == current_date
    removed_count = int(mask.sum())
    return trimmed_df.loc[~mask].reset_index(drop=True), removed_count


def run_preview(simulate_missing_today: bool = False) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    logger = PreviewLogger()
    env_path = Path(".env.local")
    local_values = local_env.load_local_env(str(env_path))
    config_path = local_env.get_env_value("CONFIG_PATH", local_values, "./config.yaml")
    log_path = Path("preview_webhook_run.log")

    if env_path.exists():
        logger.emit(f"[INFO] 已加载本地配置文件: {env_path}")
    else:
        logger.emit(f"[INFO] 未找到本地配置文件: {env_path}，仅使用系统环境变量。")

    logger.emit(f"[INFO] 使用配置文件: {config_path}")

    targets = md.load_config(config_path)
    if not targets:
        logger.emit("[WARN] 未配置任何监控标的，退出。")
        logger.emit(f"[INFO] 已写入日志文件: {log_path}")
        return 1

    current_time = md.now_in_beijing()
    end = current_time.date()
    start = end - timedelta(days=365)
    start_str = start.strftime("%Y%m%d")
    end_str = end.strftime("%Y%m%d")
    logger.emit(f"[INFO] 当前北京时间: {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.emit(f"[INFO] 拉取数据区间: {start_str} - {end_str}")

    triggered: list[dict] = []
    has_patch_targets = any(str(target.get("type", "")).strip().lower() in {"etf", "index"} for target in targets)
    jisilu_rows = None

    if has_patch_targets:
        jisilu_username = local_env.get_env_value("JISILU_USERNAME", local_values)
        jisilu_password = local_env.get_env_value("JISILU_PASSWORD", local_values)
        if jisilu_username and jisilu_password:
            try:
                jisilu_rows = md.fetch_jisilu_etf_rows(jisilu_username, jisilu_password)
                logger.emit(f"[INFO] 已加载集思录 ETF 列表，共 {len(jisilu_rows)} 条。")
            except Exception as exc:  # noqa: BLE001
                logger.emit(f"[WARN] 集思录 ETF 列表加载失败，预览将不补当日价格: {exc}")
        else:
            logger.emit("[WARN] 未配置 JISILU_USERNAME/JISILU_PASSWORD，预览将不补当日价格。")

    for target in targets:
        name = str(target.get("name", "")).strip()
        code = str(target.get("code", "")).strip()
        target_type = str(target.get("type", "")).strip().lower()
        threshold = float(target.get("threshold", 0.08))
        lookback_days = int(target.get("lookback_days", 120))

        if not name or not code or target_type not in {"etf", "index"}:
            logger.emit(f"[ERROR] 配置不完整或类型非法，已跳过: {target}")
            continue

        logger.emit(
            f"[INFO] 开始预览: {name} ({code}), type={target_type}, threshold={threshold:.2%}, lookback={lookback_days}"
        )
        try:
            if target_type == "etf":
                df = md.fetch_etf_data(code, start_str, end_str)
                if simulate_missing_today:
                    df, removed_count = drop_current_day_row(df, current_time)
                    logger.emit(
                        f"[INFO] 模拟 free-api 缺少当日价格: 移除 {current_time.strftime('%Y-%m-%d')} 原始 ETF 行 {removed_count} 条。"
                    )
                if jisilu_rows:
                    df, patch = md.patch_etf_dataframe_with_jisilu(df, code, jisilu_rows, current_time=current_time)
                    if patch:
                        logger.emit(
                            f"[INFO] 已用集思录补齐 ETF: {patch['fund_nm']}({patch['fund_id']}) "
                            f"-> {patch['close']:.4f}"
                        )
            else:
                df = md.fetch_index_data(code, start_str, end_str)
                if simulate_missing_today:
                    df, removed_count = drop_current_day_row(df, current_time)
                    logger.emit(
                        f"[INFO] 模拟 free-api 缺少当日价格: 移除 {current_time.strftime('%Y-%m-%d')} 原始指数行 {removed_count} 条。"
                    )
                if jisilu_rows:
                    df, patch = md.patch_index_dataframe_with_jisilu(df, code, jisilu_rows, current_time=current_time)
                    if patch:
                        logger.emit(
                            f"[INFO] 已用集思录 ETF 补齐指数: {patch['fund_nm']}({patch['fund_id']}) "
                            f"-> {patch['close']:.4f}"
                        )

            if df.empty:
                logger.emit(f"[WARN] {name} ({code}) 未获取到有效数据，跳过。")
                continue

            result = md.compute_drawdown(df, lookback_days)
            drawdown = result["drawdown"]
            logger.emit(
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
            logger.emit(f"[ERROR] 预览 {name} ({code}) 失败: {exc}")
            continue

    if not triggered:
        logger.emit("[INFO] 当前无触发项，不会推送消息。")
        logger.emit(f"[INFO] 已写入日志文件: {log_path}")
        return 0

    payload = md.build_webhook_payload(triggered, current_time=current_time)
    payload_path = Path("preview_webhook_payload.json")
    markdown_path = Path("preview_webhook_message.md")
    payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(payload["markdown"]["content"], encoding="utf-8")

    logger.emit(f"[INFO] 共有 {len(triggered)} 个触发项，下面是将要推送的 payload:")
    logger.emit(json.dumps(payload, ensure_ascii=False, indent=2))
    logger.emit("")
    logger.emit("[INFO] Markdown 正文预览:")
    logger.emit(payload["markdown"]["content"])
    logger.emit("")
    logger.emit(f"[INFO] 已写入文件: {payload_path}")
    logger.emit(f"[INFO] 已写入文件: {markdown_path}")
    logger.emit(f"[INFO] 已写入日志文件: {log_path}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="本地预览日志和 webhook Markdown，不实际发送消息")
    parser.add_argument(
        "--simulate-missing-today",
        action="store_true",
        help="模拟行情源未返回当天数据，再尝试用集思录补齐当日价格",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    log_path = Path("preview_webhook_run.log")
    with log_path.open("w", encoding="utf-8") as log_file:
        tee_stdout = TeeStream(sys.stdout, log_file)
        tee_stderr = TeeStream(sys.stderr, log_file)
        with redirect_stdout(tee_stdout), redirect_stderr(tee_stderr):
            return run_preview(simulate_missing_today=args.simulate_missing_today)


if __name__ == "__main__":
    raise SystemExit(main())
