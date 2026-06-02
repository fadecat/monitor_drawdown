from __future__ import annotations

from pathlib import Path

import prototype_style_rotation_chart
import style_rotation_preview


DEFAULT_OUTPUT_DIR = Path(".test_artifacts/style_rotation_etf_preview")


def main() -> int:
    payload = style_rotation_preview.collect_etf_style_rotation_preview_payload()
    output_path = prototype_style_rotation_chart.generate_style_rotation_chart(
        payload,
        DEFAULT_OUTPUT_DIR,
    )
    print(f"[INFO] ETF 风格轮动预览图已生成: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
