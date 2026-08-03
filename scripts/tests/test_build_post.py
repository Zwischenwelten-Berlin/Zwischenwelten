import base64
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import publish_post

COVER_PNG = base64.b64decode(
    b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGBgAAAABQABh6FO1AAAAABJRU5ErkJggg=="
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
