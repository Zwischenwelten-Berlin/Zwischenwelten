import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import html_to_md
import publish_post

MD = """# Ein Test mit Glanz

*Der Untertitel*

Author: Süleyman Bağ

Erster Absatz mit **wichtig** und einem [Link](https://example.org/a).

## Zwischentitel

- eins
- zwei

> Ein schönes Zitat.
>
> — **Jemand**, Rolle

| Spalte A | Spalte B |
| --- | --- |
| 1 | 2 |
"""


def build_page(md=MD, **kw):
    args = dict(lang="de", date="2026-08-03", slug="ein-test",
                tag="Medienpreis", highlight="Glanz",
                alt="Ein Bild", caption="Die Unterschrift", write=False)
    args.update(kw)
    import base64, tempfile
    png = base64.b64decode(
        b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGBgAAAABQABh6FO1AAAAABJRU5ErkJggg==")
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as fh:
        fh.write(png)
    return publish_post.build_post(md, fh.name, **args)


def test_metadata_recovered():
    page = build_page()["page_html"]
    r = html_to_md.page_to_md(page)
    assert r["title"] == "Ein Test mit Glanz"
    assert r["subtitle"] == "Der Untertitel"
    assert r["lang"] == "de"
    assert r["date"] == "2026-08-03"
    assert r["author"] == "Süleyman Bağ"
    assert r["tag"] == "Medienpreis"
    assert r["highlight"] == "Glanz"
    assert r["alt"] == "Ein Bild"
    assert r["caption"] == "Die Unterschrift"


def test_round_trip_is_word_identical():
    first = build_page()
    r = html_to_md.page_to_md(first["page_html"])
    second = build_page(md=r["md"])
    # Recovered manuscript must regenerate a page word-identical to the original.
    _, _, diffs = publish_post.check_fidelity(r["md"], first["page_html"])
    assert diffs == []
    _, _, diffs = publish_post.check_fidelity(r["md"], second["page_html"])
    assert diffs == []


def test_quote_attribution_survives_round_trip():
    first = build_page()
    r = html_to_md.page_to_md(first["page_html"])
    second = build_page(md=r["md"])
    # <cite> must keep name bold and role unbolded after regeneration.
    assert "<cite><strong>Jemand</strong>" in second["page_html"]


def test_no_tag_no_caption():
    page = build_page(tag=None, highlight=None, caption=None)["page_html"]
    r = html_to_md.page_to_md(page)
    assert r["tag"] is None and r["highlight"] is None and r["caption"] is None


AMP_MD = """# Kunst & Kultur

*Stimmen & Perspektiven*

Author: A & B

Ein Absatz mit einem & Zeichen.
"""


def test_metadata_with_ampersand_round_trips():
    first = build_page(
        md=AMP_MD, tag="Tag & Co", highlight=None,
        alt="Alt & Text", caption="Bild & Text", new_author=True)
    r = html_to_md.page_to_md(first["page_html"])
    assert r["title"] == "Kunst & Kultur"
    assert r["subtitle"] == "Stimmen & Perspektiven"
    assert r["author"] == "A & B"
    assert r["tag"] == "Tag & Co"
    assert r["alt"] == "Alt & Text"
    assert r["caption"] == "Bild & Text"
    _, _, diffs = publish_post.check_fidelity(r["md"], first["page_html"])
    assert diffs == []


def test_fragment_to_md_headings_and_bold():
    md = html_to_md.fragment_to_md(
        "<h1>Titel</h1><p><em>Unter</em></p><h2>Kapitel</h2>"
        "<p>Text mit <strong>fett</strong>.</p><ul><li>a</li></ul>")
    assert md.startswith("# Titel")
    assert "*Unter*" in md
    assert "## Kapitel" in md
    assert "**fett**" in md
    assert "- a" in md
