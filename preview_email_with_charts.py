import base64
from pathlib import Path
from typing import Dict, List, Optional

import local_env
import monitor_drawdown as md


def png_to_data_uri(path: Path) -> str:
    png_bytes = path.read_bytes()
    encoded = base64.b64encode(png_bytes).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def build_valuation_items(config_path: str) -> List[Dict]:
    targets = md.load_config(config_path)
    valuation_targets = [
        target for target in targets
        if str(target.get("type", "")).strip().lower() == "valuation"
    ]
    if not valuation_targets:
        print("[WARN] config.yaml 中未找到 valuation 标的。")
        return []

    cn_10y_yield: Optional[float] = None
    cn_10y_bond_history = None
    try:
        cn_10y_yield = md.fetch_cn_10y_bond_yield()
        cn_10y_bond_history = md.fetch_cn_10y_bond_history()
    except Exception as exc:  # noqa: BLE001
        print(f"[WARN] 国债数据获取失败，估值卡片中股债指标可能为空: {exc}")

    valuation_items: List[Dict] = []
    for target in valuation_targets:
        name = str(target.get("name", "")).strip()
        code = str(target.get("code", "")).strip()
        print(f"[INFO] 拉取估值: {name} ({code})")
        try:
            metrics = md.fetch_target_index_metrics(target)
            if not metrics:
                print(f"[WARN] {name} ({code}) 估值为空，跳过")
                continue
            item: Dict = {"name": name, "code": code}
            item.update(metrics)
            if cn_10y_yield is not None:
                md.attach_equity_bond_ratio(item, cn_10y_yield)
            if cn_10y_bond_history is not None:
                md.attach_equity_bond_spread(item, cn_10y_bond_history)
            valuation_items.append(item)
        except Exception as exc:  # noqa: BLE001
            print(f"[WARN] {name} ({code}) 拉取失败: {exc}")
    return valuation_items


def generate_chart_paths(valuation_items: List[Dict]) -> Dict[str, Path]:
    from prototype_valuation_percentile_chart import generate_valuation_percentile_chart

    output_dir = Path(".email_chart_cache")
    chart_paths: Dict[str, Path] = {}
    for item in valuation_items:
        target = dict(item)
        target.update(
            {
                "type": "valuation",
                "index_valuation_percentile_url": item.get("index_valuation_percentile_source", ""),
                "index_dividend_yield_url": item.get("index_dividend_yield_source", ""),
            }
        )
        png_path = generate_valuation_percentile_chart(target, output_dir)
        if png_path is None:
            continue
        code = str(item.get("index_code") or item.get("code") or "").strip()
        if code:
            chart_paths[code] = png_path
    return chart_paths


def generate_fx_chart_path() -> Optional[Path]:
    from prototype_fx_chart import generate_fx_chart

    output_dir = Path(".email_chart_cache")
    return generate_fx_chart(output_dir)


def main() -> int:
    try:
        import sys
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    env_path = Path(".env.local")
    local_values = local_env.load_local_env(str(env_path))
    config_path = local_env.get_env_value("CONFIG_PATH", local_values, "./config.yaml")

    valuation_items = build_valuation_items(config_path)
    if not valuation_items:
        print("[ERROR] 无可用 valuation 数据，未生成预览。")
        return 1

    chart_paths = generate_chart_paths(valuation_items)
    print(f"[INFO] 邮件图生成: {len(chart_paths)}/{len(valuation_items)}")
    try:
        fx_chart_path = generate_fx_chart_path()
    except Exception as exc:  # noqa: BLE001
        print(f"[WARN] 汇率图生成失败: {exc}")
        fx_chart_path = None
    print(f"[INFO] 外汇图生成: {'OK' if fx_chart_path else 'SKIP'}")

    current_time = md.now_in_beijing()
    html = md.build_email_html_content(
        triggered_items=[],
        valuation_items=valuation_items,
        current_time=current_time,
        chart_paths=chart_paths,
        fx_chart_path=fx_chart_path,
    )
    for code, path in chart_paths.items():
        html = html.replace(f"cid:equity_bond_{code}", png_to_data_uri(path))
    if fx_chart_path is not None:
        html = html.replace("cid:fx_usd_cny_vs_mid_10y", png_to_data_uri(fx_chart_path))

    output_path = Path("email_preview_with_charts.html")
    output_path.write_text(html, encoding="utf-8")
    print(f"[INFO] 预览文件已生成: {output_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
