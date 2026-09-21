import base64
import json
import os
import re
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


@pytest.fixture
def big_cover(tmp_path):
    from PIL import Image
    p = tmp_path / "gross.png"
    Image.new("RGB", (3200, 1600), (20, 60, 120)).save(p)
    return str(p)


def cover_names(repo, slug):
    import cover_images
    return [os.path.basename(p) for p in
            cover_images.all_files(slug, str(repo / "assets" / "blog"))]


INDEX_MIN = """<html><body>
            <button type="button" class="lang-chip" data-lang="de" aria-pressed="false">Deutsch</button>
<div class="posts-grid" id="posts-grid">
</div>
<script>var langs = ['de'];</script>
</body></html>"""


NETWORK_MIN = """<html><body>
          <div class="card-grid">
            <article class="info-card">
              <h3>Süleyman Bağ</h3>
              <p class="info-role">Journalist</p>
              <a class="info-more" href="/journalistennetzwerk/suleyman-bag">Mehr erfahren &amp; Beiträge →</a>
            </article>

            <article class="info-card">
              <h3>Ayşe Örnek</h3>
              <p class="info-role">Journalistin</p>
            </article>
          </div>
</body></html>"""


@pytest.fixture
def repo(tmp_path, monkeypatch):
    (tmp_path / "aktuelles").mkdir()
    (tmp_path / "assets" / "blog").mkdir(parents=True)
    (tmp_path / "journalistennetzwerk").mkdir()
    (tmp_path / "aktuelles" / "index.html").write_text(INDEX_MIN, encoding="utf-8")
    (tmp_path / "journalistennetzwerk.html").write_text(NETWORK_MIN, encoding="utf-8")
    shutil.copyfile(publish_post.AUTHORS, tmp_path / "assets" / "blog" / "authors.json")
    monkeypatch.setattr(publish_post, "ROOT", str(tmp_path))
    monkeypatch.setattr(publish_post, "POSTS_DIR", str(tmp_path / "aktuelles"))
    monkeypatch.setattr(publish_post, "INDEX", str(tmp_path / "aktuelles" / "index.html"))
    monkeypatch.setattr(publish_post, "IMG_DIR", str(tmp_path / "assets" / "blog"))
    monkeypatch.setattr(publish_post, "AUTHORS", str(tmp_path / "assets" / "blog" / "authors.json"))
    monkeypatch.setattr(publish_post, "MANUSCRIPTS_DIR", str(tmp_path / "assets" / "blog" / "manuscripts"))
    monkeypatch.setattr(publish_post, "POSTS_JSON", str(tmp_path / "assets" / "blog" / "posts.json"))
    monkeypatch.setattr(publish_post, "AUTHOR_PAGES_DIR", str(tmp_path / "journalistennetzwerk"))
    monkeypatch.setattr(publish_post, "NETWORK_PAGE", str(tmp_path / "journalistennetzwerk.html"))
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
    assert r["cover_rel"] == "/assets/blog/ein-test-cover.jpg"
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


def test_desk_byline_is_an_organization(repo, cover):
    r = publish_post.build_post(MD, cover, lang="de", date="2026-08-03",
                                author="Redaktion", write=False)
    assert r["author"] == "Redaktion"
    assert '"@type":"Organization",\n      "name":"Redaktion"' in r["page_html"]
    # the desk has no author page, so nothing is linked in the network
    assert r["author_page"] is None


def test_desk_byline_keeps_german_name_in_every_language(repo, cover):
    for lang in ("tr", "ru", "ar", "fa"):
        r = publish_post.build_post(MD, cover, lang=lang, date="2026-08-03",
                                    author="Redaktion", write=False)
        assert r["author"] == "Redaktion", lang


def test_person_byline_stays_a_person(repo, cover):
    r = publish_post.build_post(MD, cover, lang="de", date="2026-08-03", write=False)
    # only the author block may change type; the publisher stays an Organization
    author_block = re.search(r'"author":\{.*?\}', r["page_html"], re.S).group(0)
    assert '"@type":"Person"' in author_block
    assert "Organization" not in author_block
    assert '"publisher":{\n      "@type":"Organization"' in r["page_html"]


def test_translation_gets_author_page_card(repo, cover, author_page):
    r = publish_post.build_post(MD, cover, lang="tr", date="2026-08-03",
                                slug="ein-test-tr", original_slug="ein-test", write=True)
    html = author_page.read_text(encoding="utf-8")
    assert '/aktuelles/ein-test-tr"' in html
    assert r["author_page"] == "journalistennetzwerk/suleyman-bag.html"
    # a translation carries both its language badge and the Übersetzung marker
    card = re.search(r'<a class="post-card" href="/aktuelles/ein-test-tr".*?</a>',
                     html, re.S).group(0)
    assert '>Türkçe</span>' in card
    assert '<span class="post-translation-badge">Übersetzung</span>' in card


def test_translation_is_grouped_under_its_original(repo, cover, author_page):
    publish_post.build_post(MD, cover, lang="de", date="2026-08-03", write=True)
    publish_post.build_post(MD, cover, lang="tr", date="2026-08-04",
                            slug="ein-test-tr", original_slug="ein-test", write=True)
    publish_post.build_post(MD, cover, lang="ru", date="2026-08-05",
                            slug="ein-test-ru", original_slug="ein-test", write=True)
    # a later, unrelated original still lands on top of the grid
    publish_post.build_post(MD.replace("# Ein Test", "# Zweiter Test"), cover,
                            lang="de", date="2026-08-06", write=True)
    html = author_page.read_text(encoding="utf-8")
    order = re.findall(r'<a class="post-card" href="/aktuelles/([^"]+)"', html)
    assert order == ["zweiter-test", "ein-test", "ein-test-tr", "ein-test-ru",
                     "alter-beitrag"]


def test_regrouping_an_edited_translation_keeps_its_place(repo, cover, author_page):
    publish_post.build_post(MD, cover, lang="de", date="2026-08-03", write=True)
    publish_post.build_post(MD, cover, lang="tr", date="2026-08-04",
                            slug="ein-test-tr", original_slug="ein-test", write=True)
    publish_post.build_post(MD, cover, lang="ru", date="2026-08-05",
                            slug="ein-test-ru", original_slug="ein-test", write=True)
    changed = MD.replace("Erster Absatz", "Geänderter Absatz")
    publish_post.build_post(changed, None, lang="tr", date="2026-08-04",
                            slug="ein-test-tr", original_slug="ein-test",
                            update=True, write=True)
    html = author_page.read_text(encoding="utf-8")
    order = re.findall(r'<a class="post-card" href="/aktuelles/([^"]+)"', html)
    assert order == ["ein-test", "ein-test-tr", "ein-test-ru", "alter-beitrag"]
    assert html.count('href="/aktuelles/ein-test-tr"') == 1


def test_original_has_no_translation_badge(repo, cover, author_page):
    publish_post.build_post(MD, cover, lang="de", date="2026-08-03", write=True)
    html = author_page.read_text(encoding="utf-8")
    card = re.search(r'<a class="post-card" href="/aktuelles/ein-test".*?</a>',
                     html, re.S).group(0)
    assert '>Deutsch</span>' in card
    assert "post-translation-badge" not in card


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
    assert r["cover_rel"] == "/assets/blog/ein-test-cover.jpg"  # kept


def test_update_with_new_cover_replaces_file(repo, cover, big_cover):
    publish_post.build_post(MD, cover, lang="de", date="2026-08-03", write=True)
    assert (repo / "assets" / "blog" / "ein-test-cover-1.webp").exists()
    r = publish_post.build_post(MD, big_cover, lang="de", date="2026-08-03",
                                slug="ein-test", update=True, write=True)
    assert r["cover_rel"] == "/assets/blog/ein-test-cover.jpg"
    assert cover_names(repo, "ein-test") == [
        "ein-test-cover-1600.webp", "ein-test-cover-800.webp", "ein-test-cover.jpg"]
    assert "assets/blog/ein-test-cover-1.webp" in r["files"]  # staged deletion


def test_update_with_image_path_same_as_existing_cover_does_not_raise(repo, big_cover):
    # Regression for C1: passing the repo's own cover file back in as
    # image_path (as the app's edit-publish path can do) must not blow up
    # mid-write — and must not re-encode the JPEG a second time.
    publish_post.build_post(MD, big_cover, lang="de", date="2026-08-03", write=True)
    existing_cover = repo / "assets" / "blog" / "ein-test-cover.jpg"
    before = existing_cover.read_bytes()
    changed = MD.replace("Erster Absatz", "Geänderter Absatz")
    r = publish_post.build_post(changed, str(existing_cover), lang="de", date="2026-08-03",
                                slug="ein-test", update=True, write=True)
    page = (repo / "aktuelles" / "ein-test.html").read_text(encoding="utf-8")
    assert "Geänderter Absatz" in page
    assert existing_cover.read_bytes() == before
    assert r["cover_rel"] == "/assets/blog/ein-test-cover.jpg"


def test_update_converts_a_legacy_cover_in_place(repo, cover, big_cover):
    # Posts published before covers were optimised carry a lone .png.
    publish_post.build_post(MD, cover, lang="de", date="2026-08-03", write=True)
    blog = repo / "assets" / "blog"
    for name in cover_names(repo, "ein-test"):
        os.remove(blog / name)
    shutil.copyfile(big_cover, blog / "ein-test-cover.png")

    r = publish_post.build_post(MD, None, lang="de", date="2026-08-03",
                                slug="ein-test", update=True, write=True)

    assert cover_names(repo, "ein-test") == [
        "ein-test-cover-1600.webp", "ein-test-cover-800.webp", "ein-test-cover.jpg"]
    assert "assets/blog/ein-test-cover.png" in r["files"]      # staged deletion
    page = (repo / "aktuelles" / "ein-test.html").read_text(encoding="utf-8")
    assert 'src="/assets/blog/ein-test-cover.jpg"' in page


def test_update_requires_existing_post(repo, cover):
    with pytest.raises(publish_post.PublishError):
        publish_post.build_post(MD, cover, lang="de", date="2026-08-03",
                                slug="gibt-es-nicht", update=True, write=True)


def test_new_post_still_refuses_existing_slug(repo, cover):
    publish_post.build_post(MD, cover, lang="de", date="2026-08-03", write=True)
    with pytest.raises(publish_post.PublishError):
        publish_post.build_post(MD, cover, lang="de", date="2026-08-03", write=True)


def test_render_author_page(repo):
    html = publish_post.render_author_page(
        "Ayşe Örnek", "Journalistin", ["Absatz eins.", "Absatz zwei."],
        "/assets/autoren/ayse-ornek.png")
    assert "Ayşe Örnek" in html
    assert "<p>Absatz eins.</p>" in html
    assert '<div class="posts-grid">' in html
    assert "Süleyman" not in html
    # no leftover Süleyman-specific photo crop — every new author gets a
    # normal headshot, not a zoomed-in TV-still crop.
    assert "transform:scale(2.6)" not in html
    # the generated grid must accept cards
    card = publish_post.AUTHOR_CARD.format(
        slug="x", lang="de", cover="/c.png", dims="", srcset="", alt="", lang_label="Deutsch",
        translation_badge="", iso_date="2026-01-01",
        date_label="1. Januar 2026", title_plain="X", excerpt="", read_more="Weiterlesen")
    assert "/aktuelles/x" in publish_post.upsert_author_card(html, card, "x")
    # the template must carry the badge CSS the cards rely on
    assert ".post-badges{" in html
    assert ".post-translation-badge{" in html


def test_render_author_page_escapes_quotes_in_attributes(repo):
    html = publish_post.render_author_page(
        'Foo "Bar" Baz', "Journalist", ["Bio."], "/assets/autoren/x.png")
    assert 'alt="Foo &quot;Bar&quot; Baz"' in html
    assert '"Bar"' not in html


def member_card(html, name):
    m = re.search(
        rf'<article class="info-card">\s*<h3>{name}</h3>.*?</article>', html, re.S)
    return m.group(0) if m else None


def test_link_network_member_adds_link_to_existing_card():
    html, changed = publish_post.link_network_member(
        NETWORK_MIN, "Ayşe Örnek", "Journalistin", "ayse-ornek")
    assert changed
    card = member_card(html, "Ayşe Örnek")
    assert ('<a class="info-more" href="/journalistennetzwerk/ayse-ornek">'
            "Mehr erfahren &amp; Beiträge →</a>") in card
    # the neighbouring card keeps exactly one link
    assert member_card(html, "Süleyman Bağ").count("info-more") == 1


def test_link_network_member_leaves_already_linked_card_alone():
    html, changed = publish_post.link_network_member(
        NETWORK_MIN, "Süleyman Bağ", "Journalist", "suleyman-bag")
    assert not changed
    assert html == NETWORK_MIN


def test_link_network_member_appends_card_for_unknown_name():
    html, changed = publish_post.link_network_member(
        NETWORK_MIN, "Neue Person", "Neue Rolle", "neue-person")
    assert changed
    card = member_card(html, "Neue Person")
    assert '<p class="info-role">Neue Rolle</p>' in card
    assert 'href="/journalistennetzwerk/neue-person"' in card
    # the new card sits inside the grid, before its closing </div>
    assert html.index(card) < html.index("</div>")


def test_link_network_member_without_grid_raises():
    with pytest.raises(publish_post.PublishError):
        publish_post.link_network_member("<html></html>", "X", "Rolle", "x")


# --------------------------------------------------------------------------
# delete_post
# --------------------------------------------------------------------------
def test_delete_post_removes_page_cover_manuscript_and_registry_entry(repo, cover):
    publish_post.build_post(MD, cover, lang="de", date="2026-08-03", write=True)
    publish_post.delete_post("ein-test")
    assert not os.path.exists(repo / "aktuelles" / "ein-test.html")
    assert cover_names(repo, "ein-test") == []
    assert not os.path.exists(repo / "assets" / "blog" / "manuscripts" / "ein-test.md")
    reg = json.loads((repo / "assets" / "blog" / "posts.json").read_text())
    assert "ein-test" not in reg["posts"]


def test_delete_post_returns_title_and_removed_files(repo, cover):
    publish_post.build_post(MD, cover, lang="de", date="2026-08-03", write=True)
    r = publish_post.delete_post("ein-test")
    assert r["title"] == "Ein Test"
    assert "aktuelles/ein-test.html" in r["files"]
    assert "assets/blog/ein-test-cover.jpg" in r["files"]
    assert "assets/blog/ein-test-cover-1.webp" in r["files"]
    assert "assets/blog/manuscripts/ein-test.md" in r["files"]
    assert "assets/blog/posts.json" in r["files"]
    assert "aktuelles/index.html" in r["files"]


def test_delete_post_removes_card_from_index(repo, cover):
    publish_post.build_post(MD, cover, lang="de", date="2026-08-03", write=True)
    publish_post.delete_post("ein-test")
    index = (repo / "aktuelles" / "index.html").read_text(encoding="utf-8")
    assert "/aktuelles/ein-test" not in index


def test_delete_post_leaves_other_posts_cards_intact(repo, cover):
    publish_post.build_post(MD, cover, lang="de", date="2026-08-03", write=True)
    publish_post.build_post(MD.replace("Ein Test", "Zweiter Test"), cover,
                            lang="de", date="2026-08-04", write=True)
    publish_post.delete_post("ein-test")
    index = (repo / "aktuelles" / "index.html").read_text(encoding="utf-8")
    assert "/aktuelles/ein-test" not in index
    assert "/aktuelles/zweiter-test" in index
    assert os.path.exists(repo / "aktuelles" / "zweiter-test.html")


def test_delete_post_removes_card_from_author_page(repo, cover, author_page):
    publish_post.build_post(MD, cover, lang="de", date="2026-08-03", write=True)
    assert "/aktuelles/ein-test" in author_page.read_text(encoding="utf-8")
    r = publish_post.delete_post("ein-test")
    page = author_page.read_text(encoding="utf-8")
    assert "/aktuelles/ein-test" not in page
    # the author's pre-existing card is untouched
    assert "/aktuelles/alter-beitrag" in page
    assert "journalistennetzwerk/suleyman-bag.html" in r["files"]


def test_delete_post_refuses_unknown_slug(repo):
    with pytest.raises(publish_post.PublishError):
        publish_post.delete_post("gibt-es-nicht")


def test_delete_post_refuses_locked_post(repo, cover):
    publish_post.build_post(MD, cover, lang="de", date="2026-08-03", write=True)
    reg = json.loads((repo / "assets" / "blog" / "posts.json").read_text())
    reg["posts"]["ein-test"]["locked"] = True
    (repo / "assets" / "blog" / "posts.json").write_text(
        json.dumps(reg, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(publish_post.PublishError):
        publish_post.delete_post("ein-test")
    assert os.path.exists(repo / "aktuelles" / "ein-test.html")


def test_delete_post_refuses_original_that_still_has_translations(repo, cover):
    publish_post.build_post(MD, cover, lang="de", date="2026-08-03", write=True)
    publish_post.build_post(MD, cover, lang="tr", date="2026-08-03",
                            slug="ein-test-tr", original_slug="ein-test", write=True)
    with pytest.raises(publish_post.PublishError) as exc:
        publish_post.delete_post("ein-test")
    assert "ein-test-tr" in str(exc.value)
    assert os.path.exists(repo / "aktuelles" / "ein-test.html")


def test_delete_post_allows_translation_itself(repo, cover):
    publish_post.build_post(MD, cover, lang="de", date="2026-08-03", write=True)
    publish_post.build_post(MD, cover, lang="tr", date="2026-08-03",
                            slug="ein-test-tr", original_slug="ein-test", write=True)
    publish_post.delete_post("ein-test-tr")
    reg = json.loads((repo / "assets" / "blog" / "posts.json").read_text())
    assert "ein-test-tr" not in reg["posts"]
    assert "ein-test" in reg["posts"]


def test_delete_post_removes_language_chip_when_it_was_the_last_of_its_language(repo, cover):
    publish_post.build_post(MD, cover, lang="de", date="2026-08-03", write=True)
    publish_post.build_post(MD, cover, lang="tr", date="2026-08-03",
                            slug="ein-test-tr", original_slug="ein-test", write=True)
    assert 'data-lang="tr"' in (repo / "aktuelles" / "index.html").read_text(encoding="utf-8")
    publish_post.delete_post("ein-test-tr")
    index = (repo / "aktuelles" / "index.html").read_text(encoding="utf-8")
    assert 'data-lang="tr"' not in index
    assert "'tr'" not in re.search(r"var langs = \[(.*?)\];", index).group(1)
    # the language that still has a post keeps its chip
    assert 'data-lang="de"' in index


def test_delete_post_keeps_language_chip_while_another_post_uses_it(repo, cover):
    publish_post.build_post(MD, cover, lang="de", date="2026-08-03", write=True)
    publish_post.build_post(MD.replace("Ein Test", "Zweiter Test"), cover,
                            lang="de", date="2026-08-04", write=True)
    publish_post.delete_post("ein-test")
    index = (repo / "aktuelles" / "index.html").read_text(encoding="utf-8")
    assert 'data-lang="de"' in index
    assert "'de'" in re.search(r"var langs = \[(.*?)\];", index).group(1)


def test_delete_post_without_cover_on_disk_still_succeeds(repo, cover):
    publish_post.build_post(MD, cover, lang="de", date="2026-08-03", write=True)
    for name in cover_names(repo, "ein-test"):
        os.remove(repo / "assets" / "blog" / name)
    r = publish_post.delete_post("ein-test")
    assert not any("ein-test-cover" in f for f in r["files"])
    reg = json.loads((repo / "assets" / "blog" / "posts.json").read_text())
    assert "ein-test" not in reg["posts"]


def test_byline_links_to_existing_author_page(repo, cover, author_page):
    r = publish_post.build_post(MD, cover, lang="de", date="2026-08-03", write=False)
    assert ('<p class="article-author">Autor: <strong>'
            '<a href="/journalistennetzwerk/suleyman-bag">Süleyman Bağ</a></strong>'
            ) in r["page_html"]


def test_byline_without_author_page_stays_plain(repo, cover):
    r = publish_post.build_post(MD, cover, lang="de", date="2026-08-03", write=False)
    assert '<p class="article-author">Autor: <strong>Süleyman Bağ</strong>' in r["page_html"]


def test_link_author_bylines_links_posts_that_predate_the_page(repo, cover):
    publish_post.build_post(MD, cover, lang="de", date="2026-08-03", write=True)
    (repo / "journalistennetzwerk" / "suleyman-bag.html").write_text("<html>", encoding="utf-8")
    assert publish_post.link_author_bylines("suleyman-bag") == [
        os.path.join("aktuelles", "ein-test.html")]
    html = (repo / "aktuelles" / "ein-test.html").read_text(encoding="utf-8")
    assert '<strong><a href="/journalistennetzwerk/suleyman-bag">Süleyman Bağ</a></strong>' in html
    # a second run finds nothing left to link
    assert publish_post.link_author_bylines("suleyman-bag") == []


def test_link_author_bylines_leaves_other_authors_posts_alone(repo, cover):
    publish_post.build_post(MD, cover, lang="de", date="2026-08-03", write=True)
    (repo / "journalistennetzwerk" / "dominique-hensel.html").write_text("<html>", encoding="utf-8")
    assert publish_post.link_author_bylines("dominique-hensel") == []
    assert publish_post.link_author_bylines("andrei-schnell") == []  # no page at all


# ---- SEO head, responsive covers, hreflang, sitemap ------------------------
MD_TR = MD.replace("# Ein Test", "# Bir Deneme")


def test_page_head_has_canonical_og_url_and_twitter_card(cover):
    html = publish_post.build_post(MD, cover, lang="de", date="2026-08-03",
                                   write=False)["page_html"]
    assert '<link rel="canonical" href="https://zwischenwelten.berlin/aktuelles/ein-test">' in html
    assert '<meta property="og:url" content="https://zwischenwelten.berlin/aktuelles/ein-test">' in html
    assert '<meta name="twitter:card" content="summary_large_image">' in html
    assert '<meta name="twitter:title" content="Ein Test">' in html
    assert ('<meta name="twitter:image" '
            'content="https://zwischenwelten.berlin/assets/blog/ein-test-cover.jpg">') in html


def test_write_stores_optimised_cover_set_and_lists_it(repo, big_cover):
    r = publish_post.build_post(MD, big_cover, lang="de", date="2026-08-03", write=True)
    assert cover_names(repo, "ein-test") == [
        "ein-test-cover-1600.webp", "ein-test-cover-800.webp", "ein-test-cover.jpg"]
    for name in cover_names(repo, "ein-test"):
        assert f"assets/blog/{name}" in r["files"]


def test_page_and_card_images_carry_srcset_and_real_dimensions(repo, big_cover):
    r = publish_post.build_post(MD, big_cover, lang="de", date="2026-08-03", write=True)
    srcset = ('srcset="/assets/blog/ein-test-cover-800.webp 800w, '
              '/assets/blog/ein-test-cover-1600.webp 1600w"')
    for html in (r["page_html"], r["card_html"]):
        assert 'src="/assets/blog/ein-test-cover.jpg"' in html
        assert srcset in html
        assert 'sizes="' in html
        assert 'width="1600" height="800"' in html


def test_unreadable_cover_is_a_publish_error(repo, tmp_path):
    bad = tmp_path / "kaputt.png"
    bad.write_bytes(b"kein bild")
    with pytest.raises(publish_post.PublishError):
        publish_post.build_post(MD, str(bad), lang="de", date="2026-08-03", write=True)
    assert not (repo / "aktuelles" / "ein-test.html").exists()


def test_post_without_translations_has_empty_hreflang_block(repo, cover):
    html = publish_post.build_post(MD, cover, lang="de", date="2026-08-03",
                                   write=True)["page_html"]
    assert "<!-- hreflang:start -->" in html
    assert 'rel="alternate"' not in html


def test_translation_links_both_pages_and_stages_the_original(repo, cover):
    publish_post.build_post(MD, cover, lang="de", date="2026-08-03", write=True)
    r = publish_post.build_post(MD_TR, cover, lang="tr", date="2026-08-04",
                                slug="ein-test-tr", original_slug="ein-test", write=True)

    for slug in ("ein-test", "ein-test-tr"):
        page = (repo / "aktuelles" / f"{slug}.html").read_text(encoding="utf-8")
        assert 'hreflang="de" href="https://zwischenwelten.berlin/aktuelles/ein-test"' in page
        assert 'hreflang="tr" href="https://zwischenwelten.berlin/aktuelles/ein-test-tr"' in page
        assert 'hreflang="x-default" href="https://zwischenwelten.berlin/aktuelles/ein-test"' in page
    assert "aktuelles/ein-test.html" in r["files"]


def test_translation_preview_already_shows_its_hreflang_links(repo, cover):
    publish_post.build_post(MD, cover, lang="de", date="2026-08-03", write=True)
    r = publish_post.build_post(MD_TR, cover, lang="tr", date="2026-08-04",
                                slug="ein-test-tr", original_slug="ein-test", write=False)
    assert 'hreflang="tr"' in r["page_html"]
    assert 'hreflang="de"' in r["page_html"]
    original = (repo / "aktuelles" / "ein-test.html").read_text(encoding="utf-8")
    assert 'hreflang="tr"' not in original          # preview writes nothing


def test_publish_writes_sitemap_and_stages_it(repo, cover):
    r = publish_post.build_post(MD, cover, lang="de", date="2026-08-03", write=True)
    sitemap = (repo / "sitemap.xml").read_text(encoding="utf-8")
    assert "<loc>https://zwischenwelten.berlin/aktuelles/ein-test</loc>" in sitemap
    assert "sitemap.xml" in r["files"]


def test_delete_translation_unlinks_the_original_and_updates_sitemap(repo, cover):
    publish_post.build_post(MD, cover, lang="de", date="2026-08-03", write=True)
    publish_post.build_post(MD_TR, cover, lang="tr", date="2026-08-04",
                            slug="ein-test-tr", original_slug="ein-test", write=True)

    r = publish_post.delete_post("ein-test-tr")

    original = (repo / "aktuelles" / "ein-test.html").read_text(encoding="utf-8")
    assert 'rel="alternate"' not in original
    assert "ein-test-tr" not in (repo / "sitemap.xml").read_text(encoding="utf-8")
    assert "aktuelles/ein-test.html" in r["files"]
    assert "sitemap.xml" in r["files"]
    assert cover_names(repo, "ein-test-tr") == []
    assert len(cover_names(repo, "ein-test")) == 2      # the original keeps its cover


def test_author_page_gets_a_canonical_url(repo):
    html = publish_post.render_author_page("Ayşe Örnek", "Journalistin", ["Bio."],
                                           "/assets/autoren/ayse-ornek.png",
                                           author_id="ayse-ornek")
    assert ('<link rel="canonical" '
            'href="https://zwischenwelten.berlin/journalistennetzwerk/ayse-ornek">') in html
    assert "__CANONICAL__" not in publish_post.render_author_page(
        "Ayşe Örnek", "Journalistin", ["Bio."], "/assets/autoren/ayse-ornek.png")
