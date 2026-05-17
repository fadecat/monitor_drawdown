from email.message import EmailMessage

import monitor_cctda_coal_daily as coal


LIST_HTML = """
<div class="news_list">
  <ul>
    <li>
      <el-link href="https://www.cctda.org.cn/index.php?m=content&c=index&a=show&catid=75&id=5759">
        煤炭运销日报(2026-5-15)
      </el-link>
      <span class="rt">2026-05-15</span>
    </li>
    <li>
      <el-link href="https://www.cctda.org.cn/index.php?m=content&c=index&a=show&catid=75&id=5758">
        煤炭运销日报(2026-5-14)
      </el-link>
      <span class="rt">2026-05-15</span>
    </li>
  </ul>
</div>
"""


DETAIL_IMAGE_HTML = """
<div class="title">
  <h1>煤炭运销日报(2026-5-15)<br />
    <span>2026-05-15 16:44:46&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;来源：中国煤炭运销协会</span>
  </h1>
</div>
<div id="article-content">
  <p>
    <img src="/uploadfile/2026/0515/01.png" alt="01"/>
    <img src="/uploadfile/2026/0515/02.png" alt="02"/>
    <img src="/uploadfile/2026/0515/03.png" alt="03"/>
  </p>
</div>
"""


DETAIL_PDF_HTML = """
<div class="title">
  <h1>煤炭运销日报(2026-5-14)<br />
    <span>2026-05-14 17:00:00&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;来源：中国煤炭运销协会</span>
  </h1>
</div>
<div id="article-content">
  <p><a href="/uploadfile/2026/0514/report.pdf">点击下载</a></p>
</div>
"""


class FakeBinaryResponse:
    def __init__(self, content: bytes):
        self.content = content

    def raise_for_status(self) -> None:
        return None


def test_parse_latest_article_from_list_uses_first_row():
    result = coal.parse_latest_article_from_list(LIST_HTML, coal.CCTDA_LIST_URL)

    assert result == {
        "article_title": "煤炭运销日报(2026-5-15)",
        "article_url": "https://www.cctda.org.cn/index.php?m=content&c=index&a=show&catid=75&id=5759",
        "list_date": "2026-05-15",
    }


def test_parse_detail_content_extracts_all_images():
    result = coal.parse_detail_content(
        DETAIL_IMAGE_HTML,
        "https://www.cctda.org.cn/index.php?m=content&c=index&a=show&catid=75&id=5759",
    )

    assert result["article_title"] == "煤炭运销日报(2026-5-15)"
    assert result["published_at"] == "2026-05-15 16:44:46"
    assert result["content_type"] == "images"
    assert result["image_urls"] == [
        "https://www.cctda.org.cn/uploadfile/2026/0515/01.png",
        "https://www.cctda.org.cn/uploadfile/2026/0515/02.png",
        "https://www.cctda.org.cn/uploadfile/2026/0515/03.png",
    ]


def test_parse_detail_content_extracts_pdf_link_when_no_images():
    result = coal.parse_detail_content(
        DETAIL_PDF_HTML,
        "https://www.cctda.org.cn/index.php?m=content&c=index&a=show&catid=75&id=5758",
    )

    assert result["article_title"] == "煤炭运销日报(2026-5-14)"
    assert result["published_at"] == "2026-05-14 17:00:00"
    assert result["content_type"] == "pdf"
    assert result["pdf_url"] == "https://www.cctda.org.cn/uploadfile/2026/0514/report.pdf"


def test_should_skip_article_when_url_matches_saved_state():
    latest = {
        "article_title": "煤炭运销日报(2026-5-15)",
        "article_url": "https://www.cctda.org.cn/index.php?m=content&c=index&a=show&catid=75&id=5759",
        "list_date": "2026-05-15",
    }
    saved = {
        "article_url": "https://www.cctda.org.cn/index.php?m=content&c=index&a=show&catid=75&id=5759",
        "article_title": "煤炭运销日报(2026-5-15)",
    }

    assert coal.should_skip_article(latest, saved) is True


def test_load_and_save_state_round_trip(tmp_path):
    state_path = tmp_path / "data_state" / "cctda_coal_daily.json"
    state = {
        "article_url": "https://www.cctda.org.cn/index.php?m=content&c=index&a=show&catid=75&id=5759",
        "article_title": "煤炭运销日报(2026-5-15)",
        "published_at": "2026-05-15 16:44:46",
        "content_type": "images",
        "image_count": 3,
        "content_hash": "sha256:test",
        "sent_at": "2026-05-17T15:00:12+08:00",
    }

    coal.save_state(state_path, state)
    loaded = coal.load_state(state_path)

    assert loaded == state


def test_download_report_images_saves_files_in_order(monkeypatch, tmp_path):
    payloads = {
        "https://www.cctda.org.cn/uploadfile/2026/0515/01.png": b"image-1",
        "https://www.cctda.org.cn/uploadfile/2026/0515/02.png": b"image-2",
    }

    monkeypatch.setattr(
        coal.requests,
        "get",
        lambda url, headers, timeout: FakeBinaryResponse(payloads[url]),
    )

    paths = coal.download_report_images(list(payloads.keys()), tmp_path)

    assert [path.name for path in paths] == ["page_01.png", "page_02.png"]
    assert paths[0].read_bytes() == b"image-1"
    assert paths[1].read_bytes() == b"image-2"


def test_build_report_email_uses_detail_title_and_embeds_all_images(tmp_path):
    image_one = tmp_path / "page_01.png"
    image_two = tmp_path / "page_02.png"
    image_one.write_bytes(b"image-1")
    image_two.write_bytes(b"image-2")

    message = coal.build_report_email(
        sender="sender@qq.com",
        recipients=["alice@example.com"],
        subject="煤炭运销日报(2026-5-15)",
        article_url="https://www.cctda.org.cn/index.php?m=content&c=index&a=show&catid=75&id=5759",
        fetched_at="2026-05-17 15:00:12",
        image_paths=[image_one, image_two],
    )

    assert message["Subject"] == "煤炭运销日报(2026-5-15)"
    html_part = message.get_body(preferencelist=("html",))
    html_content = html_part.get_content()
    assert "https://www.cctda.org.cn/index.php?m=content&c=index&a=show&catid=75&id=5759" in html_content
    assert html_content.count("cid:report_page_") == 2


def test_render_pdf_to_pngs_creates_one_png_per_page(tmp_path):
    pdf_path = tmp_path / "report.pdf"
    document = coal.fitz.open()
    document.new_page(width=200, height=100)
    document.new_page(width=200, height=100)
    document.save(pdf_path)
    document.close()

    output_paths = coal.render_pdf_to_pngs(pdf_path, tmp_path / "png")

    assert [path.name for path in output_paths] == ["page_01.png", "page_02.png"]
    assert all(path.exists() for path in output_paths)


def test_materialize_report_pages_downloads_pdf_and_renders_pngs(monkeypatch, tmp_path):
    pdf_path = tmp_path / "downloaded.pdf"
    pdf_doc = coal.fitz.open()
    pdf_doc.new_page(width=100, height=100)
    pdf_doc.save(pdf_path)
    pdf_doc.close()
    pdf_bytes = pdf_path.read_bytes()

    monkeypatch.setattr(
        coal.requests,
        "get",
        lambda url, headers, timeout: FakeBinaryResponse(pdf_bytes),
    )

    detail = {
        "article_title": "煤炭运销日报(2026-5-14)",
        "published_at": "2026-05-14 17:00:00",
        "content_type": "pdf",
        "pdf_url": "https://www.cctda.org.cn/uploadfile/2026/0514/report.pdf",
    }

    image_paths, content_hash = coal.materialize_report_pages(detail, tmp_path)

    assert len(image_paths) == 1
    assert image_paths[0].name == "page_01.png"
    assert content_hash.startswith("sha256:")


def test_main_saves_pdf_state_after_success(monkeypatch, tmp_path):
    state_path = tmp_path / "data_state" / "cctda_coal_daily.json"
    monkeypatch.setenv("RECEIVER_EMAIL", "alice@example.com")
    monkeypatch.setenv("SMTP_USER", "sender@qq.com")
    monkeypatch.setenv("SMTP_PASS", "auth-code")
    monkeypatch.setenv("CCTDA_STATE_PATH", str(state_path))

    monkeypatch.setattr(coal.local_env, "load_local_env", lambda path: {})
    monkeypatch.setattr(
        coal,
        "fetch_html",
        lambda url: LIST_HTML if url == coal.CCTDA_LIST_URL else DETAIL_PDF_HTML,
    )

    def fake_materialize(detail, workspace_dir):
        page = workspace_dir / "page_01.png"
        page.write_bytes(b"png")
        return [page], "sha256:pdf"

    monkeypatch.setattr(coal, "materialize_report_pages", fake_materialize)
    monkeypatch.setattr(
        coal,
        "build_report_email",
        lambda **kwargs: EmailMessage(),
    )
    monkeypatch.setattr(coal, "send_report_email", lambda config, message: None)

    result = coal.main()
    saved = coal.load_state(state_path)

    assert result == 0
    assert saved["content_type"] == "pdf"
    assert saved["content_hash"] == "sha256:pdf"
    assert saved["image_count"] == 1
