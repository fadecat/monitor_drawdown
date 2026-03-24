import argparse
from datetime import timedelta
from typing import Dict, List, Optional, Tuple

import local_env
import monitor_drawdown as md


def load_jisilu_credentials() -> Tuple[str, str]:
    local_values = local_env.load_local_env(".env.local")
    username = local_env.get_env_value("JISILU_USERNAME", local_values)
    password = local_env.get_env_value("JISILU_PASSWORD", local_values)
    return username, password


def build_targets_from_args(args: argparse.Namespace) -> List[Dict]:
    if args.code:
        return [
            {
                "name": args.name or args.code,
                "code": args.code,
                "type": args.type,
                "threshold": args.threshold,
                "lookback_days": args.lookback_days,
            }
        ]

    return md.load_config(args.config)


def fetch_target_dataframe(target_type: str, code: str, start_str: str, end_str: str):
    if target_type == "etf":
        return md.fetch_etf_data(code, start_str, end_str)
    if target_type == "index":
        return md.fetch_index_data(code, start_str, end_str)
    raise ValueError(f"不支持的标的类型: {target_type}")


def patch_target_dataframe(
    target_type: str,
    df,
    code: str,
    rows: List[Dict],
    current_time,
):
    if target_type == "etf":
        return md.patch_etf_dataframe_with_jisilu(df, code, rows, current_time=current_time)
    if target_type == "index":
        return md.patch_index_dataframe_with_jisilu(df, code, rows, current_time=current_time)
    raise ValueError(f"不支持的标的类型: {target_type}")


def summarize_result(result: Dict) -> str:
    return (
        f"最新日期 {result['current_date']}, "
        f"现价 {result['current_price']:.4f}, "
        f"窗口高点 {result['peak_price']:.4f} ({result['peak_date']}), "
        f"回撤 {result['drawdown']:.2%}"
    )


def build_patch_summary(target_type: str, patch: Optional[Dict]) -> str:
    if not patch:
        return "未应用集思录补价。"

    patch_date = md.pd.to_datetime(patch["date"]).strftime("%Y-%m-%d")
    if target_type == "etf":
        increase_rt = patch.get("increase_rt")
        increase_text = "-" if increase_rt is None else f"{increase_rt:.2f}%"
        return (
            f"已补 ETF {patch['fund_nm']}({patch['fund_id']}), "
            f"补齐日期 {patch_date}, "
            f"现价 {patch['close']:.4f}, "
            f"涨跌 {increase_text}, "
            f"时间 {patch.get('last_time', '') or '-'}"
        )

    etf_return = patch.get("etf_return")
    etf_return_text = "-" if etf_return is None else f"{etf_return:.2%}"
    return (
        f"已补指数映射 ETF {patch['fund_nm']}({patch['fund_id']}), "
        f"补齐日期 {patch_date}, "
        f"推算收盘 {patch['close']:.4f}, "
        f"ETF 涨跌 {etf_return_text}, "
        f"时间 {patch.get('last_time', '') or '-'}"
    )


def build_comparison_lines(report: Dict) -> List[str]:
    base = report["base_result"]
    patched = report["patched_result"]
    drawdown_delta = patched["drawdown"] - base["drawdown"]
    price_delta = patched["current_price"] - base["current_price"]
    row_delta = report["patched_rows"] - report["base_rows"]
    patch_status = "是" if report["patch_applied"] else "否"
    drawdown_sign = "+" if drawdown_delta >= 0 else ""
    price_sign = "+" if price_delta >= 0 else ""

    threshold = report["threshold"]
    base_triggered = base["drawdown"] >= threshold
    patched_triggered = patched["drawdown"] >= threshold

    return [
        "",
        (
            f"[INFO] 标的: {report['name']} ({report['code']}), "
            f"type={report['type']}, threshold={threshold:.2%}, "
            f"lookback={report['lookback_days']}"
        ),
        f"[INFO] 原始结果: {summarize_result(base)}",
        f"[INFO] 集思录结果: {summarize_result(patched)}",
        (
            "[INFO] 差异: "
            f"是否补价 {patch_status}, "
            f"新增行数 {row_delta}, "
            f"现价变化 {price_sign}{price_delta:.4f}, "
            f"回撤变化 {drawdown_sign}{drawdown_delta:.2%}"
        ),
        (
            "[INFO] 阈值判断: "
            f"原始 {'触发' if base_triggered else '未触发'}, "
            f"集思录 {'触发' if patched_triggered else '未触发'}"
        ),
        f"[INFO] 补丁明细: {build_patch_summary(report['type'], report['patch'])}",
    ]


def compare_target(
    target: Dict,
    rows: List[Dict],
    current_time,
    start_str: str,
    end_str: str,
) -> Dict:
    name = str(target.get("name", "")).strip()
    code = str(target.get("code", "")).strip()
    target_type = str(target.get("type", "")).strip().lower()
    threshold = float(target.get("threshold", 0.08))
    lookback_days = int(target.get("lookback_days", 120))

    if not name or not code or target_type not in {"etf", "index"}:
        raise ValueError(f"配置不完整或类型非法: {target}")

    base_df = fetch_target_dataframe(target_type, code, start_str, end_str)
    patched_df, patch = patch_target_dataframe(target_type, base_df, code, rows, current_time)

    return {
        "name": name,
        "code": code,
        "type": target_type,
        "threshold": threshold,
        "lookback_days": lookback_days,
        "base_rows": len(base_df),
        "patched_rows": len(patched_df),
        "base_result": md.compute_drawdown(base_df, lookback_days),
        "patched_result": md.compute_drawdown(patched_df, lookback_days),
        "patch_applied": patch is not None,
        "patch": patch,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="对比使用和不使用集思录补价时的回撤结果")
    parser.add_argument("--config", default="./config.yaml", help="配置文件路径，默认 ./config.yaml")
    parser.add_argument("--code", help="单独测试的代码，例如 159307 或 000300")
    parser.add_argument("--type", choices=["etf", "index"], help="单独测试时的标的类型")
    parser.add_argument("--name", help="单独测试时的展示名称")
    parser.add_argument("--threshold", type=float, default=0.08, help="单独测试时的阈值，默认 0.08")
    parser.add_argument("--lookback-days", type=int, default=120, help="单独测试时的回看天数，默认 120")
    parser.add_argument("--days", type=int, default=365, help="历史拉取天数，默认 365")
    args = parser.parse_args()

    if args.code and not args.type:
        raise SystemExit("使用 --code 时必须同时提供 --type")

    targets = build_targets_from_args(args)
    if not targets:
        print("[WARN] 没有可对比的标的。")
        return 1

    username, password = load_jisilu_credentials()
    if not username or not password:
        raise RuntimeError("缺少 JISILU_USERNAME/JISILU_PASSWORD，无法对比集思录补价结果")

    current_time = md.now_in_beijing()
    start = current_time.date() - timedelta(days=args.days)
    start_str = start.strftime("%Y%m%d")
    end_str = current_time.date().strftime("%Y%m%d")

    print(f"[INFO] 当前北京时间: {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"[INFO] 拉取数据区间: {start_str} - {end_str}")

    rows = md.fetch_jisilu_etf_rows(username, password)
    print(f"[INFO] 已加载集思录 ETF 列表，共 {len(rows)} 条。")

    for target in targets:
        try:
            report = compare_target(target, rows, current_time, start_str, end_str)
        except Exception as exc:  # noqa: BLE001
            print(f"[ERROR] 对比失败: {target} -> {exc}")
            continue

        for line in build_comparison_lines(report):
            print(line)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
