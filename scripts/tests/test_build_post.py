import base64
import json
import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import publish_post

COVER_PNG = base64.b64decode(
    b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGBgAAAABQABh6FO1AAAAABJRU5ErkJggg=="
)

# 1x1 valid JPEG, used to exercise the update-with-new-extension path.
COVER_JPG = base64.b64decode(
    b"/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0"
    b"Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIy"
    b"MjL/wAARCAABAAEDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQID"
    b"AAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlq"
    b"c3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3"
    b"+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEI"
    b"FEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImK"
    b"kpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDi"
    b"6KKK+ZP3E//Z"
)

MD = """# Ein Test

*Der Untertitel*

Author: Süleyman Bağ

Erster Absatz mit **wichtig**.

## Zwischentitel

- eins
- zwei

> Ein schönes Zitat.
"""


@pytest.fixture
def cover(tmp_path):
    p = tmp_path / "cover.png"
    p.write_bytes(COVER_PNG)
    return str(p)


INDEX_MIN = """<html><body>
            <button type="button" class="lang-chip" data-lang="de" aria-pressed="false">Deutsch</button>
<div class="posts-grid" id="posts-grid">
</div>
<script>var langs = ['de'];</script>
</body></html>"""


@pytest.fixture
def repo(tmp_path, monkeypatch):
    (tmp_path / "aktuelles").mkdir()
    (tmp_path / "assets" / "blog").mkdir(parents=True)
    (tmp_path / "journalistennetzwerk").mkdir()
    (tmp_path / "aktuelles" / "index.html").write_text(INDEX_MIN, encoding="utf-8")
    shutil.copyfile(publish_post.AUTHORS, tmp_path / "assets" / "blog" / "authors.json")
    monkeypatch.setattr(publish_post, "ROOT", str(tmp_path))
    monkeypatch.setattr(publish_post, "POSTS_DIR", str(tmp_path / "aktuelles"))
    monkeypatch.setattr(publish_post, "INDEX", str(tmp_path / "aktuelles" / "index.html"))
    monkeypatch.setattr(publish_post, "IMG_DIR", str(tmp_path / "assets" / "blog"))
    monkeypatch.setattr(publish_post, "AUTHORS", str(tmp_path / "assets" / "blog" / "authors.json"))
    monkeypatch.setattr(publish_post, "MANUSCRIPTS_DIR", str(tmp_path / "assets" / "blog" / "manuscripts"))
    monkeypatch.setattr(publish_post, "POSTS_JSON", str(tmp_path / "assets" / "blog" / "posts.json"))
    monkeypatch.setattr(publish_post, "AUTHOR_PAGES_DIR", str(tmp_path / "journalistennetzwerk"))
    return tmp_path


def test_build_post_renders_without_writing(cover):
    r = publish_post.build_post(MD, cover, lang="de", date="2026-08-03", write=False)
    assert r["slug"] == "ein-test"
    assert r["title"] == "Ein Test"
    assert r["subtitle"] == "Der Untertitel"
    assert r["author"] == "Süleyman Bağ"
    assert r["author_canonical"] == "Süleyman Bağ"
    assert not r["author_new"]
    assert "<h2>Zwischentitel</h2>" in r["page_html"]
    assert '<blockquote class="pull-quote">' in r["page_html"]
    assert r["cover_rel"] == "/assets/blog/ein-test-cover.png"
    assert "aktuelles/ein-test.html" in r["files"]
    # write=False must not touch the repo
    assert not os.path.exists(os.path.join(publish_post.ROOT, "aktuelles", "ein-test.html"))


def test_unknown_author_raises(cover):
    md = MD.replace("Süleyman Bağ", "Gänzlich Unbekannt")
    with pytest.raises(publish_post.PublishError):
        publish_post.build_post(md, cover, lang="de", date="2026-08-03", write=False)


def test_missing_title_raises(cover):
    with pytest.raises(publish_post.PublishError):
        publish_post.build_post("Nur Text ohne Titel.\n\nAuthor: Süleyman Bağ",
                                cover, lang="de", date="2026-08-03", write=False)


def test_highlight_must_occur_in_title(cover):
    with pytest.raises(publish_post.PublishError):
        publish_post.build_post(MD, cover, lang="de", date="2026-08-03",
                                highlight="fehlt", write=False)


def test_write_stores_manuscript_and_registry(repo, cover):
    publish_post.build_post(MD, cover, lang="de", date="2026-08-03", write=True)
    ms = repo / "assets" / "blog" / "manuscripts" / "ein-test.md"
    assert ms.read_text(encoding="utf-8") == MD
    reg = json.loads((repo / "assets" / "blog" / "posts.json").read_text())
    entry = reg["posts"]["ein-test"]
    assert entry["title"] == "Ein Test"
    assert entry["lang"] == "de"
    assert entry["date"] == "2026-08-03"
    assert entry["author"] == "Süleyman Bağ"
    assert entry["original_slug"] is None
    assert entry["locked"] is False


def test_files_include_manuscript_and_registry(repo, cover):
    r = publish_post.build_post(MD, cover, lang="de", date="2026-08-03", write=True)
    assert "assets/blog/manuscripts/ein-test.md" in r["files"]
    assert "assets/blog/posts.json" in r["files"]


def test_original_slug_recorded(repo, cover):
    r = publish_post.build_post(MD, cover, lang="tr", date="2026-08-03",
                                slug="ein-test-tr", original_slug="ein-test", write=True)
    reg = json.loads((repo / "assets" / "blog" / "posts.json").read_text())
    assert reg["posts"]["ein-test-tr"]["original_slug"] == "ein-test"


AUTHOR_PAGE_MIN = """<html><body>
          <div class="posts-grid">

            <a class="post-card" href="/aktuelles/alter-beitrag">
              <div class="post-info"><h3 class="post-title">Alt</h3></div>
            </a>

          </div>
</body></html>"""


@pytest.fixture
def author_page(repo):
    p = repo / "journalistennetzwerk" / "suleyman-bag.html"
    p.write_text(AUTHOR_PAGE_MIN, encoding="utf-8")
    return p


def test_publish_adds_card_to_author_page(repo, cover, author_page):
    r = publish_post.build_post(MD, cover, lang="de", date="2026-08-03", write=True)
    html = author_page.read_text(encoding="utf-8")
    assert '/aktuelles/ein-test"' in html
    assert html.index("ein-test") < html.index("alter-beitrag")  # newest first
    assert '<h3 class="post-title">Ein Test</h3>' in html
    assert "journalistennetzwerk/suleyman-bag.html" in r["files"]
    assert r["author_page"] == "journalistennetzwerk/suleyman-bag.html"


def test_translation_skips_author_page(repo, cover, author_page):
    before = author_page.read_text(encoding="utf-8")
    r = publish_post.build_post(MD, cover, lang="tr", date="2026-08-03",
                                slug="ein-test-tr", original_slug="ein-test", write=True)
    assert author_page.read_text(encoding="utf-8") == before
    assert r["author_page"] is None


def test_no_author_page_is_fine(repo, cover):
    r = publish_post.build_post(MD, cover, lang="de", date="2026-08-03", write=True)
    assert r["author_page"] is None


def test_update_replaces_page_and_card(repo, cover, author_page):
    publish_post.build_post(MD, cover, lang="de", date="2026-08-03", write=True)
    changed = MD.replace("Erster Absatz", "Geänderter Absatz")
    r = publish_post.build_post(changed, None, lang="de", date="2026-08-03",
                                slug="ein-test", update=True, write=True)
    page = (repo / "aktuelles" / "ein-test.html").read_text(encoding="utf-8")
    assert "Geänderter Absatz" in page
    index = (repo / "aktuelles" / "index.html").read_text(encoding="utf-8")
    assert index.count('href="/aktuelles/ein-test"') == 1
    author_html = author_page.read_text(encoding="utf-8")
    assert author_html.count('href="/aktuelles/ein-test"') == 1
    ms = (repo / "assets" / "blog" / "manuscripts" / "ein-test.md").read_text(encoding="utf-8")
    assert "Geänderter Absatz" in ms
    assert r["cover_rel"] == "/assets/blog/ein-test-cover.png"  # kept


def test_update_with_new_cover_replaces_file(repo, cover, tmp_path):
    publish_post.build_post(MD, cover, lang="de", date="2026-08-03", write=True)
    jpg = tmp_path / "neu.jpg"
    jpg.write_bytes(COVER_JPG)
    r = publish_post.build_post(MD, str(jpg), lang="de", date="2026-08-03",
                                slug="ein-test", update=True, write=True)
    assert r["cover_rel"] == "/assets/blog/ein-test-cover.jpg"
    assert not (repo / "assets" / "blog" / "ein-test-cover.png").exists()
    assert "assets/blog/ein-test-cover.png" in r["files"]  # staged deletion


def test_update_requires_existing_post(repo, cover):
    with pytest.raises(publish_post.PublishError):
        publish_post.build_post(MD, cover, lang="de", date="2026-08-03",
                                slug="gibt-es-nicht", update=True, write=True)


def test_new_post_still_refuses_existing_slug(repo, cover):
    publish_post.build_post(MD, cover, lang="de", date="2026-08-03", write=True)
    with pytest.raises(publish_post.PublishError):
        publish_post.build_post(MD, cover, lang="de", date="2026-08-03", write=True)
