from __future__ import annotations

import tempfile
from pathlib import Path

import local_env
import monitor_cctda_coal_daily as coal


def main() -> int:
    local_values = local_env.load_local_env(".env.local")
    output_path = Path(
        local_env.get_env_value(
            "CCTDA_PREVIEW_HTML_PATH",
            local_values,
            "cctda_coal_daily_email_preview.html",
        )
    )

    latest = coal.parse_latest_article_from_list(coal.fetch_html(coal.CCTDA_LIST_URL), coal.CCTDA_LIST_URL)
    detail = coal.parse_detail_content(coal.fetch_html(latest["article_url"]), latest["article_url"])
    fetched_at = coal.now_in_beijing().strftime("%Y-%m-%d %H:%M:%S")

    with tempfile.TemporaryDirectory(prefix="cctda_coal_daily_preview_") as temp_dir:
        image_paths, _content_hash = coal.materialize_report_pages(detail, Path(temp_dir))
        html = coal.build_report_preview_html(
            sender="preview@example.com",
            subject=str(detail["article_title"]),
            article_url=latest["article_url"],
            fetched_at=fetched_at,
            image_paths=image_paths,
        )
        output_path.write_text(html, encoding="utf-8")

    print(f"[INFO] 预览文件已生成: {output_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
