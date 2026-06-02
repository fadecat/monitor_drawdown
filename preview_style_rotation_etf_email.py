from __future__ import annotations

from pathlib import Path
from typing import Any

import preview_style_rotation_email as base_preview
import prototype_style_rotation_chart as chart
import style_rotation_preview as analysis


DEFAULT_OUTPUT_DIR = Path(".test_artifacts/style_rotation_etf_email")


def resolve_as_of_label(payload: dict[str, Any]) -> str:
    return base_preview.resolve_as_of_label(payload)


def png_to_data_uri(path: Path) -> str:
    return base_preview.png_to_data_uri(path)


def build_style_rotation_email_html(*, payload: dict[str, Any], chart_cid: str, as_of_label: str) -> str:
    return base_preview.build_style_rotation_email_html(
        payload=payload,
        chart_cid=chart_cid,
        as_of_label=as_of_label,
    )


def collect_style_rotation_etf_email_payloads(
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> dict[str, Any]:
    payload = analysis.collect_etf_style_rotation_preview_payload()
    chart_path = chart.generate_style_rotation_chart(payload, output_dir)
    return {
        "payload": payload,
        "chart_path": chart_path,
        "as_of_label": resolve_as_of_label(payload),
    }


def write_preview_html(html: str, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "preview_style_rotation_etf_email.html"
    output_path.write_text(html, encoding="utf-8")
    return output_path


def main() -> int:
    payloads = collect_style_rotation_etf_email_payloads(output_dir=DEFAULT_OUTPUT_DIR)
    chart_data_uri = png_to_data_uri(Path(payloads["chart_path"]))
    html = build_style_rotation_email_html(
        payload=dict(payloads["payload"]),
        chart_cid=chart_data_uri,
        as_of_label=str(payloads["as_of_label"]),
    )
    output_path = write_preview_html(html, DEFAULT_OUTPUT_DIR)
    print(f"[INFO] ETF 风格轮动邮件预览已生成: {output_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
