import argparse
from datetime import timedelta

import monitor_drawdown as md


def load_jisilu_credentials() -> tuple[str, str]:
    username = md.os.getenv("JISILU_USERNAME", "").strip()
    password = md.os.getenv("JISILU_PASSWORD", "").strip()
    if username and password:
        return username, password

    try:
        import jisilu_login as jl

        return jl.JISILU_USERNAME.strip(), jl.JISILU_PASSWORD.strip()
    except Exception:
        return "", ""


def build_targets_from_args(args: argparse.Namespace) -> list[dict]:
    if args.index_code:
        return [
            {
                "name": args.index_name or args.index_code,
                "code": args.index_code,
                "type": "index",
            }
        ]

    return md.load_config(args.config)


def main() -> int:
    parser = argparse.ArgumentParser(description="测试集思录 ETF 行情与指数拼接")
    parser.add_argument("--config", default="./config.yaml", help="配置文件路径，默认 ./config.yaml")
    parser.add_argument("--index-code", help="单独测试的指数代码，例如 000300")
    parser.add_argument("--index-name", help="单独测试的指数名称，仅用于输出展示")
    parser.add_argument("--days", type=int, default=365, help="历史拉取天数，默认 365")
    args = parser.parse_args()

    targets = build_targets_from_args(args)
    if not targets:
        print("[WARN] 配置中没有可测试标的。")
        print("[INFO] 可用方式: python .\\test_jisilu_index_patch.py")
        print("[INFO] 或单独测试指数: python .\\test_jisilu_index_patch.py --index-code 000300 --index-name 沪深300")
        return 1

    username, password = load_jisilu_credentials()
    if not username or not password:
        raise RuntimeError("缺少集思录账号密码，请设置环境变量或在 jisilu_login.py 中填写")

    current_time = md.now_in_beijing()
    start = current_time.date() - timedelta(days=args.days)
    start_str = start.strftime("%Y%m%d")
    end_str = current_time.date().strftime("%Y%m%d")

    print(f"[INFO] 当前北京时间: {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"[INFO] 拉取数据区间: {start_str} - {end_str}")

    rows = md.fetch_jisilu_etf_rows(username, password)
    print(f"[INFO] 已加载集思录 ETF 列表，共 {len(rows)} 条。")

    for target in targets:
        name = str(target.get("name", "")).strip()
        code = str(target.get("code", "")).strip()
        target_type = str(target.get("type", "")).strip().lower()
        threshold = float(target.get("threshold", 0.08))
        lookback_days = int(target.get("lookback_days", 120))

        print("")
        print(
            f"[INFO] 开始测试: {name} ({code}), type={target_type}, "
            f"threshold={threshold:.2%}, lookback={lookback_days}"
        )

        if target_type == "etf":
            raw_df = md.fetch_etf_data(code, start_str, end_str)
            raw_result = md.compute_drawdown(raw_df, lookback_days)
            raw_last = raw_df.sort_values("date").iloc[-1]

            print(
                f"[INFO] 原始 ETF 最后一条: 日期 {raw_result['current_date']}, "
                f"价格 {raw_result['current_price']:.4f}, 回撤 {raw_result['drawdown']:.2%}, "
                f"窗口高点 {raw_result['peak_price']:.4f} ({raw_result['peak_date']})"
            )

            patched_df, patch = md.patch_etf_dataframe_with_jisilu(
                raw_df,
                code,
                rows,
                current_time=current_time,
            )

            if not patch:
                print("[WARN] 未用集思录补齐 ETF 当日价格，保持原始结果。")
                continue

            patched_result = md.compute_drawdown(patched_df, lookback_days)
            print(
                f"[INFO] 集思录补丁: {patch['fund_nm']} ({patch['fund_id']}), "
                f"现价 {patch['close']:.4f}, 昨收 {md.format_number(patch['pre_close'] or 0, 4)}, "
                f"涨跌 {md.format_percent(patch['increase_rt'] or 0, 2)}%, 时间 {patch['last_time']}"
            )
            print(
                f"[INFO] 补齐后 ETF 最后一条: 日期 {patched_result['current_date']}, "
                f"价格 {patched_result['current_price']:.4f}, 回撤 {patched_result['drawdown']:.2%}, "
                f"窗口高点 {patched_result['peak_price']:.4f} ({patched_result['peak_date']})"
            )
            if patched_result["drawdown"] >= threshold:
                print(f"[ALERT] 触发阈值: {patched_result['drawdown']:.2%} >= {threshold:.2%}")
            else:
                print(f"[INFO] 未触发阈值: {patched_result['drawdown']:.2%} < {threshold:.2%}")
            print("[INFO] 补齐后最后 3 条数据:")
            print(patched_df.tail(3).to_string(index=False))
            continue

        if target_type != "index":
            print("[WARN] 暂不支持的类型，已跳过。")
            continue

        raw_df = md.fetch_index_data(code, start_str, end_str)
        raw_result = md.compute_drawdown(raw_df, lookback_days)
        print(
            f"[INFO] 原始指数最后一条: 日期 {raw_result['current_date']}, "
            f"收盘 {raw_result['current_price']:.4f}, 回撤 {raw_result['drawdown']:.2%}, "
            f"窗口高点 {raw_result['peak_price']:.4f} ({raw_result['peak_date']})"
        )

        candidates = md.find_jisilu_index_etf_candidates(rows, code)
        print(f"[INFO] 匹配到 {len(candidates)} 只指数 ETF。")

        patched_df, patch = md.patch_index_dataframe_with_jisilu(
            raw_df,
            code,
            rows,
            current_time=current_time,
        )

        if not patch:
            print("[WARN] 未找到可用于补齐当日价格的集思录 ETF。")
            continue

        patched_result = md.compute_drawdown(patched_df, lookback_days)
        print(
            f"[INFO] 选中 ETF: {patch['fund_nm']} ({patch['fund_id']}), "
            f"ETF 现价 {patch['etf_price']:.4f}, 昨收 {patch['etf_pre_close']:.4f}, "
            f"涨跌 {patch['etf_return']:.2%}"
        )
        print(
            f"[INFO] 拼接后指数最后一条: 日期 {patched_result['current_date']}, "
            f"收盘 {patched_result['current_price']:.4f}, 回撤 {patched_result['drawdown']:.2%}, "
            f"窗口高点 {patched_result['peak_price']:.4f} ({patched_result['peak_date']})"
        )
        if patched_result["drawdown"] >= threshold:
            print(f"[ALERT] 触发阈值: {patched_result['drawdown']:.2%} >= {threshold:.2%}")
        else:
            print(f"[INFO] 未触发阈值: {patched_result['drawdown']:.2%} < {threshold:.2%}")
        print("[INFO] 拼接后最后 3 条数据:")
        print(patched_df.tail(3).to_string(index=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
