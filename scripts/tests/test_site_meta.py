import os
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import site_meta

POSTS = {
    "keine-panik": {"lang": "tr", "date": "2026-08-17", "original_slug": None},
    "keine-panik-de": {"lang": "de", "date": "2026-08-17", "original_slug": "keine-panik"},
    "keine-panik-fa": {"lang": "fa", "date": "2026-08-20", "original_slug": "keine-panik"},
    "allein": {"lang": "de", "date": "2026-07-01", "original_slug": None},
}


def test_group_is_the_same_from_any_member_and_in_language_order():
    expected = [("de", "keine-panik-de"), ("tr", "keine-panik"), ("fa", "keine-panik-fa")]
    assert site_meta.group_of("keine-panik", POSTS) == expected
    assert site_meta.group_of("keine-panik-fa", POSTS) == expected


def test_block_lists_every_language_plus_x_default_to_the_original():
    block = site_meta.hreflang_block("keine-panik-de", POSTS)
    assert block.startswith(site_meta.HREFLANG_START)
    assert block.endswith(site_meta.HREFLANG_END)
    assert ('<link rel="alternate" hreflang="de" '
            'href="https://zwischenwelten.berlin/aktuelles/keine-panik-de">') in block
    assert ('<link rel="alternate" hreflang="fa" '
            'href="https://zwischenwelten.berlin/aktuelles/keine-panik-fa">') in block
    assert ('<link rel="alternate" hreflang="x-default" '
            'href="https://zwischenwelten.berlin/aktuelles/keine-panik">') in block
    assert block.count("<link") == 4


def test_block_is_empty_for_a_post_without_translations():
    block = site_meta.hreflang_block("allein", POSTS)
    assert "<link" not in block
    assert site_meta.HREFLANG_START in block and site_meta.HREFLANG_END in block


PAGE = """<html><head>
  <meta property="og:image" content="x">

  <link rel="stylesheet" href="/assets/fonts.css">
</head><body>hreflang im Text bleibt</body></html>"""


def test_set_hreflang_inserts_once_then_replaces():
    first = site_meta.set_hreflang(PAGE, site_meta.hreflang_block("keine-panik", POSTS))
    assert first.count(site_meta.HREFLANG_START) == 1
    assert first.index(site_meta.HREFLANG_START) < first.index('<link rel="stylesheet"')
    assert "hreflang im Text bleibt" in first

    fewer = {k: v for k, v in POSTS.items() if k != "keine-panik-fa"}
    second = site_meta.set_hreflang(first, site_meta.hreflang_block("keine-panik", fewer))
    assert second.count(site_meta.HREFLANG_START) == 1
    assert "keine-panik-fa" not in second
    assert "keine-panik-de" in second


def test_sync_hreflang_rewrites_only_pages_that_change(tmp_path):
    for slug in POSTS:
        (tmp_path / f"{slug}.html").write_text(PAGE, encoding="utf-8")

    changed = site_meta.sync_hreflang("keine-panik-fa", POSTS, str(tmp_path))
    assert sorted(os.path.basename(p) for p in changed) == [
        "keine-panik-de.html", "keine-panik-fa.html", "keine-panik.html"]
    assert "hreflang" not in (tmp_path / "allein.html").read_text(encoding="utf-8").split("<body>")[0]

    assert site_meta.sync_hreflang("keine-panik", POSTS, str(tmp_path)) == []


def test_sync_hreflang_skips_missing_pages(tmp_path):
    (tmp_path / "keine-panik.html").write_text(PAGE, encoding="utf-8")
    changed = site_meta.sync_hreflang("keine-panik", POSTS, str(tmp_path))
    assert [os.path.basename(p) for p in changed] == ["keine-panik.html"]


# ---- sitemap ---------------------------------------------------------------
NS = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9",
      "x": "http://www.w3.org/1999/xhtml"}


def make_site(root):
    ok = "<html><head><title>x</title></head><body></body></html>"
    hidden = '<html><head><meta name="robots" content="noindex"></head></html>'
    for rel, text in {
        "index.html": ok, "kontakt.html": ok, "404.html": hidden,
        "alt-umgezogen.html": hidden,
        "aktuelles/index.html": ok,
        "journalistennetzwerk.html": ok,
        "journalistennetzwerk/index.html": hidden,
        "journalistennetzwerk/hayko-bagdat.html": ok,
        "scripts/publish_app.html": ok,
    }.items():
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)


def test_sitemap_lists_indexable_pages_and_posts(tmp_path):
    make_site(str(tmp_path))
    path = site_meta.write_sitemap(str(tmp_path), POSTS)
    assert path == os.path.join(str(tmp_path), "sitemap.xml")

    tree = ET.parse(path)
    locs = [u.find("s:loc", NS).text for u in tree.getroot().findall("s:url", NS)]
    base = "https://zwischenwelten.berlin"
    assert locs[0] == base + "/"
    assert set(locs) == {
        base + "/", base + "/kontakt", base + "/aktuelles",
        base + "/journalistennetzwerk", base + "/journalistennetzwerk/hayko-bagdat",
        base + "/aktuelles/keine-panik", base + "/aktuelles/keine-panik-de",
        base + "/aktuelles/keine-panik-fa", base + "/aktuelles/allein",
    }
    assert len(locs) == len(set(locs))


def test_sitemap_posts_carry_lastmod_and_language_alternates(tmp_path):
    make_site(str(tmp_path))
    tree = ET.parse(site_meta.write_sitemap(str(tmp_path), POSTS))
    urls = {u.find("s:loc", NS).text.rsplit("/", 1)[-1]: u
            for u in tree.getroot().findall("s:url", NS)}

    de = urls["keine-panik-de"]
    assert de.find("s:lastmod", NS).text == "2026-08-17"
    alts = {a.get("hreflang"): a.get("href") for a in de.findall("x:link", NS)}
    assert set(alts) == {"de", "tr", "fa", "x-default"}
    assert alts["x-default"].endswith("/aktuelles/keine-panik")

    assert urls["allein"].findall("x:link", NS) == []
    assert urls["kontakt"].find("s:lastmod", NS) is None


def test_sitemap_is_stable_when_nothing_changed(tmp_path):
    make_site(str(tmp_path))
    first = open(site_meta.write_sitemap(str(tmp_path), POSTS), encoding="utf-8").read()
    second = open(site_meta.write_sitemap(str(tmp_path), POSTS), encoding="utf-8").read()
    assert first == second
