from __future__ import annotations

import argparse
from pathlib import Path

import backtest_etf_rotation_v4_1_strategy as backtest
import run_etf_rotation_v2_strategy as runner


STOP_LOSS_PCTS = [0.05, 0.08, 0.10]
DEFAULT_OUTPUT_ROOT = Path(".test_artifacts/etf_rotation_v4_1_backtest")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run ETF rotation V4.1 trailing stop backtest.")
    parser.add_argument("--config-path", default=str(runner.DEFAULT_CONFIG_PATH))
    parser.add_argument("--source-output-root", default=str(runner.SOURCE_OUTPUT_ROOT))
    parser.add_argument("--output-root", default="")
    parser.add_argument("--stop-loss-pct", type=float, choices=STOP_LOSS_PCTS, required=True)
    return parser


def run(
    config_path: str | Path = runner.DEFAULT_CONFIG_PATH,
    source_output_root: str | Path = runner.SOURCE_OUTPUT_ROOT,
    output_root: str | Path | None = None,
    stop_loss_pct: float = 0.08,
) -> dict:
    resolved_output_root = (
        Path(output_root)
        if output_root
        else DEFAULT_OUTPUT_ROOT / f"stop_loss_{float(stop_loss_pct):.2f}"
    )
    return backtest.run_backtest(
        config_path=config_path,
        source_output_root=source_output_root,
        output_root=resolved_output_root,
        stop_loss_pct=stop_loss_pct,
    )


def main() -> None:
    args = build_parser().parse_args()
    result = run(
        config_path=args.config_path,
        source_output_root=args.source_output_root,
        output_root=args.output_root or None,
        stop_loss_pct=args.stop_loss_pct,
    )
    summary = result["summary"]
    print(
        "stop_loss_pct={:.2f} final_nav={:.6f} annualized_return={:.6f} "
        "max_drawdown={:.6f} trailing_stop_count={}".format(
            float(args.stop_loss_pct),
            float(summary["final_nav"]),
            float(summary["annualized_return"]),
            float(summary["max_drawdown"]),
            int(summary["trailing_stop_count"]),
        )
    )


if __name__ == "__main__":
    main()

