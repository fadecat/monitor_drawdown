from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import smtplib
import tempfile
from datetime import datetime
from email.message import EmailMessage
from html import escape
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import fitz
import requests
from bs4 import BeautifulSoup

import local_env


CCTDA_LIST_URL = "https://www.cctda.org.cn/index.php?m=content&c=index&a=lists&catid=75"
DEFAULT_STATE_PATH = Path("data_state") / "cctda_coal_daily.json"
DEFAULT_EMAIL_SMTP_HOST = "smtp.qq.com"
DEFAULT_EMAIL_SMTP_PORT = 465
BEIJING_TZ = ZoneInfo("Asia/Shanghai")
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0 Safari/537.36"
    )
}


def now_in_beijing() -> datetime:
    return datetime.now(BEIJING_TZ)


def split_email_recipients(value: str) -> List[str]:
    recipients: List[str] = []
    for chunk in value.replace(";", ",").split(","):
        candidate = chunk.strip()
        if candidate and candidate not in recipients:
            recipients.append(candidate)
    return recipients


def load_email_config(local_values: Optional[Dict[str, str]] = None) -> Dict[str, object]:
    recipients = split_email_recipients(
        local_env.get_env_value("RECEIVER_EMAIL", local_values, "")
        or local_env.get_env_value("EMAIL_TO", local_values, "")
    )
    username = (
        local_env.get_env_value("SMTP_USER", local_values, "")
        or local_env.get_env_value("EMAIL_USER", local_values, "")
    ).strip()
    password = (
        local_env.get_env_value("SMTP_PASS", local_values, "")
        or local_env.get_env_value("EMAIL_PASSWORD", local_values, "")
    ).strip()
    if not recipients or not username or not password:
        raise RuntimeError("邮件配置不完整，需要 RECEIVER_EMAIL/SMTP_USER/SMTP_PASS")

    smtp_host = local_env.get_env_value("EMAIL_SMTP_HOST", local_values, DEFAULT_EMAIL_SMTP_HOST).strip()
    smtp_port_text = local_env.get_env_value("EMAIL_SMTP_PORT", local_values, str(DEFAULT_EMAIL_SMTP_PORT)).strip()
    sender = local_env.get_env_value("EMAIL_FROM", local_values, username).strip() or username
    return {
        "smtp_host": smtp_host or DEFAULT_EMAIL_SMTP_HOST,
        "smtp_port": int(smtp_port_text or str(DEFAULT_EMAIL_SMTP_PORT)),
        "username": username,
        "password": password,
        "sender": sender,
        "recipients": recipients,
    }


def fetch_html(url: str) -> str:
    response = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding or "utf-8"
    return response.text


def parse_latest_article_from_list(html: str, base_url: str) -> Dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    first_row = soup.select_one(".news_list ul li")
    if first_row is None:
        raise RuntimeError("未找到最新日报列表项")

    link = first_row.select_one("a[href], el-link[href]")
    if link is None:
        raise RuntimeError("未找到最新日报链接")

    article_title = link.get_text(" ", strip=True)
    article_url = urljoin(base_url, link.get("href", "").strip())
    list_date_node = first_row.select_one(".rt")
    list_date = list_date_node.get_text(" ", strip=True) if list_date_node else ""
    if not article_title or not article_url:
        raise RuntimeError("最新日报标题或链接为空")

    return {
        "article_title": article_title,
        "article_url": article_url,
        "list_date": list_date,
    }


def _extract_published_at(title_node) -> str:
    title_text = title_node.get_text(" ", strip=True)
    match = re.search(r"(20\d{2}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})", title_text)
    return match.group(1) if match else ""


def parse_detail_content(html: str, base_url: str) -> Dict[str, object]:
    soup = BeautifulSoup(html, "html.parser")
    title_node = soup.select_one(".news_nr .title h1") or soup.select_one(".title h1")
    article_node = soup.select_one("#article-content")
    if title_node is None or article_node is None:
        raise RuntimeError("详情页缺少标题或正文")

    article_title = title_node.get_text("\n", strip=True).split("\n", 1)[0].strip()
    published_at = _extract_published_at(title_node)

    image_urls = [
        urljoin(base_url, node.get("src", "").strip())
        for node in article_node.select("img[src]")
        if node.get("src", "").strip()
    ]
    if image_urls:
        return {
            "article_title": article_title,
            "published_at": published_at,
            "content_type": "images",
            "image_urls": image_urls,
        }

    for link in article_node.select("a[href]"):
        href = link.get("href", "").strip()
        if href.lower().endswith(".pdf"):
            return {
                "article_title": article_title,
                "published_at": published_at,
                "content_type": "pdf",
                "pdf_url": urljoin(base_url, href),
            }

    raise RuntimeError("详情页既没有图片也没有 PDF")


def load_state(path: Path = DEFAULT_STATE_PATH) -> Dict[str, object]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"状态文件格式错误: {path}")
    return payload


def save_state(path: Path, state: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def should_skip_article(latest: Dict[str, str], saved_state: Dict[str, object]) -> bool:
    return str(saved_state.get("article_url", "")).strip() == latest["article_url"].strip()


def compute_content_hash(values: List[str]) -> str:
    payload = "\n".join(values).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def compute_file_hash(paths: List[Path]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.read_bytes())
    return "sha256:" + digest.hexdigest()


def download_report_images(image_urls: List[str], output_dir: Path) -> List[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    saved_paths: List[Path] = []
    for index, image_url in enumerate(image_urls, start=1):
        response = requests.get(image_url, headers=REQUEST_HEADERS, timeout=30)
        response.raise_for_status()
        output_path = output_dir / f"page_{index:02d}.png"
        output_path.write_bytes(response.content)
        saved_paths.append(output_path)
    return saved_paths


def download_pdf(pdf_url: str, output_path: Path) -> Path:
    response = requests.get(pdf_url, headers=REQUEST_HEADERS, timeout=60)
    response.raise_for_status()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(response.content)
    return output_path


def render_pdf_to_pngs(pdf_path: Path, output_dir: Path) -> List[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    document = fitz.open(pdf_path)
    saved_paths: List[Path] = []
    try:
        for index in range(document.page_count):
            page = document.load_page(index)
            pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            output_path = output_dir / f"page_{index + 1:02d}.png"
            pixmap.save(output_path)
            saved_paths.append(output_path)
    finally:
        document.close()
    return saved_paths


def materialize_report_pages(detail: Dict[str, object], workspace_dir: Path) -> Tuple[List[Path], str]:
    content_type = str(detail["content_type"])
    if content_type == "images":
        image_urls = [str(url) for url in detail["image_urls"]]
        image_paths = download_report_images(image_urls, workspace_dir / "images")
        return image_paths, compute_content_hash(image_urls)
    if content_type == "pdf":
        pdf_path = download_pdf(str(detail["pdf_url"]), workspace_dir / "report.pdf")
        image_paths = render_pdf_to_pngs(pdf_path, workspace_dir / "images")
        return image_paths, compute_file_hash(image_paths)
    raise RuntimeError(f"不支持的内容类型: {content_type}")


def build_report_email(
    sender: str,
    recipients: List[str],
    subject: str,
    article_url: str,
    fetched_at: str,
    image_paths: List[Path],
) -> EmailMessage:
    message = EmailMessage()
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    message["Subject"] = subject
    message.set_content(
        "\n".join(
            [
                subject,
                f"详情链接: {article_url}",
                f"抓取时间: {fetched_at}",
                "请在 HTML 邮件视图中查看日报图片。",
            ]
        )
    )

    html = build_report_html_body(
        subject=subject,
        article_url=article_url,
        fetched_at=fetched_at,
        image_sources=[f"cid:report_page_{index}" for index in range(1, len(image_paths) + 1)],
    )
    message.add_alternative(html, subtype="html")

    html_part = message.get_payload()[-1]
    for index, image_path in enumerate(image_paths, start=1):
        html_part.add_related(
            image_path.read_bytes(),
            maintype="image",
            subtype="png",
            cid=f"<report_page_{index}>",
        )
    return message


def build_report_html_body(
    subject: str,
    article_url: str,
    fetched_at: str,
    image_sources: List[str],
) -> str:
    image_blocks: List[str] = []
    for index, image_src in enumerate(image_sources, start=1):
        image_blocks.append(
            f'<div style="margin:0 0 18px 0">'
            f'<img src="{escape(image_src)}" alt="report-page-{index}" '
            f'style="display:block;width:100%;max-width:960px;height:auto;border:0">'
            f"</div>"
        )

    return (
        "<!doctype html><html><head><meta charset=\"utf-8\"></head><body "
        "style=\"margin:0;padding:24px;background:#f5f5f7;font-family:Arial,'Microsoft YaHei',sans-serif\">"
        "<div style=\"max-width:980px;margin:0 auto;background:#ffffff;padding:24px;border-radius:12px\">"
        f"<h1 style=\"margin:0 0 8px 0;font-size:24px\">{escape(subject)}</h1>"
        f"<p style=\"margin:0 0 6px 0\">详情链接: <a href=\"{escape(article_url)}\">{escape(article_url)}</a></p>"
        f"<p style=\"margin:0 0 18px 0\">抓取时间: {escape(fetched_at)}</p>"
        + "".join(image_blocks)
        + "</div></body></html>"
    )


def build_report_preview_html(
    sender: str,
    subject: str,
    article_url: str,
    fetched_at: str,
    image_paths: List[Path],
) -> str:
    del sender
    image_sources: List[str] = []
    for image_path in image_paths:
        encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
        image_sources.append(f"data:image/png;base64,{encoded}")
    return build_report_html_body(
        subject=subject,
        article_url=article_url,
        fetched_at=fetched_at,
        image_sources=image_sources,
    )


def send_report_email(config: Dict[str, object], message: EmailMessage) -> None:
    with smtplib.SMTP_SSL(str(config["smtp_host"]), int(config["smtp_port"]), timeout=20) as smtp:
        smtp.login(str(config["username"]), str(config["password"]))
        smtp.send_message(message)
    print(f"[INFO] 邮件发送成功，收件人: {', '.join(config['recipients'])}")


def main() -> int:
    local_values = local_env.load_local_env(".env.local")
    state_path = Path(local_env.get_env_value("CCTDA_STATE_PATH", local_values, str(DEFAULT_STATE_PATH)))
    email_config = load_email_config(local_values)

    print(f"[INFO] 拉取列表页: {CCTDA_LIST_URL}")
    latest = parse_latest_article_from_list(fetch_html(CCTDA_LIST_URL), CCTDA_LIST_URL)
    print(f"[INFO] 最新日报: {latest['article_title']} -> {latest['article_url']}")

    saved_state = load_state(state_path)
    if should_skip_article(latest, saved_state):
        print(f"[INFO] 最新日报已发送，跳过: {latest['article_url']}")
        return 0

    detail = parse_detail_content(fetch_html(latest["article_url"]), latest["article_url"])
    print(f"[INFO] 内容类型: {detail['content_type']}")

    with tempfile.TemporaryDirectory(prefix="cctda_coal_daily_") as temp_dir:
        temp_root = Path(temp_dir)
        image_paths, content_hash = materialize_report_pages(detail, temp_root)
        fetched_at = now_in_beijing().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[INFO] 图片数量: {len(image_paths)}")
        message = build_report_email(
            sender=str(email_config["sender"]),
            recipients=list(email_config["recipients"]),
            subject=str(detail["article_title"]),
            article_url=latest["article_url"],
            fetched_at=fetched_at,
            image_paths=image_paths,
        )
        send_report_email(email_config, message)
        save_state(
            state_path,
            {
                "article_url": latest["article_url"],
                "article_title": str(detail["article_title"]),
                "published_at": str(detail.get("published_at", "")),
                "content_type": str(detail["content_type"]),
                "image_count": len(image_paths),
                "content_hash": content_hash,
                "sent_at": fetched_at,
            },
        )
        print(f"[INFO] 状态文件已更新: {state_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
