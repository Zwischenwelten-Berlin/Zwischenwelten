"""Search-engine metadata that spans more than one page: hreflang links
between a post and its translations, and sitemap.xml.

Both are derived from the post registry (assets/blog/posts.json). A
translation points at its original through `original_slug`; the original and
everything pointing at it form one hreflang group.

Nothing here touches a page's body, so locked (hand-built) posts are handled
like any other.
"""
import glob
import os
import re
from xml.sax.saxutils import escape

SITE = "https://zwischenwelten.berlin"
LANG_ORDER = ["de", "en", "tr", "ru", "uk", "ar", "ku", "fa"]

HREFLANG_START = "<!-- hreflang:start -->"
HREFLANG_END = "<!-- hreflang:end -->"
_BLOCK_RE = re.compile(re.escape(HREFLANG_START) + r".*?" + re.escape(HREFLANG_END), re.S)


def post_url(slug):
    return f"{SITE}/aktuelles/{slug}"


def _root(slug, posts):
    return (posts.get(slug) or {}).get("original_slug") or slug


def group_of(slug, posts):
    """[(lang, slug), …] for slug's original and all its translations, in the
    site's language order. The same list whichever member you start from."""
    root = _root(slug, posts)
    members = [s for s, e in posts.items() if s == root or e.get("original_slug") == root]

    def order(s):
        lang = posts[s].get("lang")
        return (LANG_ORDER.index(lang) if lang in LANG_ORDER else len(LANG_ORDER), s)

    return [(posts[s].get("lang"), s) for s in sorted(members, key=order)]


def _alternates(slug, posts):
    """[(hreflang, url), …] — empty for a post that exists in one language."""
    group = group_of(slug, posts)
    if len(group) < 2:
        return []
    return ([(lang, post_url(s)) for lang, s in group]
            + [("x-default", post_url(_root(slug, posts)))])


def hreflang_block(slug, posts):
    lines = [f'  <link rel="alternate" hreflang="{lang}" href="{url}">'
             for lang, url in _alternates(slug, posts)]
    return "\n".join([HREFLANG_START] + lines + ["  " + HREFLANG_END])


def set_hreflang(page_html, block):
    """Replace the page's hreflang block, or add one ahead of the first
    stylesheet when the page has none yet."""
    if _BLOCK_RE.search(page_html):
        return _BLOCK_RE.sub(lambda _m: block, page_html, count=1)
    anchor = re.search(r'^[ \t]*<link rel="stylesheet"', page_html, re.M)
    if not anchor:
        anchor = re.search(r"^[ \t]*</head>", page_html, re.M)
    if not anchor:
        return page_html
    return page_html[:anchor.start()] + "  " + block + "\n\n" + page_html[anchor.start():]


def sync_hreflang(slug, posts, posts_dir):
    """Bring the hreflang block of every page in slug's group up to date.
    Returns the paths actually rewritten."""
    changed = []
    for _lang, member in group_of(slug, posts):
        path = os.path.join(posts_dir, member + ".html")
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as fh:
            old = fh.read()
        new = set_hreflang(old, hreflang_block(member, posts))
        if new != old:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(new)
            changed.append(path)
    return changed


# --------------------------------------------------------------------------
# sitemap.xml
# --------------------------------------------------------------------------
_HIDDEN_RE = re.compile(r'<meta\s+name="robots"\s+content="[^"]*noindex|http-equiv="refresh"', re.I)


def static_pages(root):
    """[(path, clean URL), …] of every hand-written page that may be indexed,
    sorted by URL. Redirect stubs and noindex pages (404, moved posts) leave
    themselves out."""
    pages = {}
    paths = (glob.glob(os.path.join(root, "*.html"))
             + glob.glob(os.path.join(root, "aktuelles", "index.html"))
             + glob.glob(os.path.join(root, "journalistennetzwerk", "*.html")))
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            if _HIDDEN_RE.search(fh.read(4096)):
                continue
        rel = os.path.relpath(path, root).replace(os.sep, "/")[:-len(".html")]
        if rel == "index":
            rel = ""
        elif rel.endswith("/index"):
            rel = rel[:-len("/index")]
        pages[f"{SITE}/{rel}"] = path
    return [(pages[url], url) for url in sorted(pages)]


def write_sitemap(root, posts):
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"',
           '        xmlns:xhtml="http://www.w3.org/1999/xhtml">']
    for _path, url in static_pages(root):
        out.append(f"  <url><loc>{escape(url)}</loc></url>")
    newest_first = sorted(posts, key=lambda s: (posts[s].get("date") or "", s), reverse=True)
    for slug in newest_first:
        out.append("  <url>")
        out.append(f"    <loc>{escape(post_url(slug))}</loc>")
        if posts[slug].get("date"):
            out.append(f"    <lastmod>{posts[slug]['date']}</lastmod>")
        for lang, url in _alternates(slug, posts):
            out.append(f'    <xhtml:link rel="alternate" hreflang="{lang}" href="{escape(url)}"/>')
        out.append("  </url>")
    out.append("</urlset>")
    path = os.path.join(root, "sitemap.xml")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")
    return path
