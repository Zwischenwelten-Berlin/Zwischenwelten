#!/usr/bin/env python3
"""One-time migration: bring every page published before 2026-09 up to the
SEO and image standard that publish_post.build_post now produces.

    python3 scripts/backfill_seo.py --dry-run     # report only
    python3 scripts/backfill_seo.py               # rewrite files

What it does, all of it idempotent:

  * every cover in assets/blog/ becomes <slug>-cover.jpg + WebP variants
    (cover_images.write_set); the old .png is removed
  * every reference to a cover — og:image, JSON-LD, <img> on post pages, the
    overview and author pages — follows, and each <img> gets srcset/sizes and
    the real dimensions
  * post pages gain canonical, og:url, a Twitter card and hreflang links
  * hand-written pages gain a canonical URL
  * sitemap.xml is written

Only <head> metadata and <img> attributes change, never article text, so
locked (hand-built) posts are migrated like any other.
"""
import argparse
import glob
import os
import re

import cover_images
import publish_post
import site_meta

ICON_RE = re.compile(r'^[ \t]*<link rel="icon"', re.M)
OG_IMAGE_RE = re.compile(r'^[ \t]*<meta property="og:image" content="([^"]*)">[ \t]*\n', re.M)


def _meta(page_html, attr, name):
    m = re.search(rf'<meta {attr}="{re.escape(name)}" content="([^"]*)">', page_html)
    return m.group(1) if m else ""


def add_canonical(page_html, url):
    if 'rel="canonical"' in page_html:
        return page_html
    m = ICON_RE.search(page_html) or re.search(r"^[ \t]*</head>", page_html, re.M)
    if not m:
        return page_html
    return (page_html[:m.start()] + f'  <link rel="canonical" href="{url}">\n'
            + page_html[m.start():])


def upsert_post_head(page_html, slug):
    """canonical, og:url and a Twitter card for a post page. Title, description
    and image are copied from the page's own Open Graph tags as they stand
    (they are already attribute-escaped)."""
    url = site_meta.post_url(slug)
    page_html = add_canonical(page_html, url)
    og_image = OG_IMAGE_RE.search(page_html)
    if not og_image:
        return page_html
    if 'property="og:url"' not in page_html:
        page_html = (page_html[:og_image.start()]
                     + f'  <meta property="og:url" content="{url}">\n'
                     + page_html[og_image.start():])
        og_image = OG_IMAGE_RE.search(page_html)
    if 'name="twitter:card"' not in page_html:
        title = _meta(page_html, "property", "og:title")
        description = (_meta(page_html, "property", "og:description")
                       or _meta(page_html, "name", "description"))
        card = ('\n  <meta name="twitter:card" content="summary_large_image">\n'
                f'  <meta name="twitter:title" content="{title}">\n'
                f'  <meta name="twitter:description" content="{description}">\n'
                f'  <meta name="twitter:image" content="{og_image.group(1)}">\n')
        page_html = page_html[:og_image.end()] + card + page_html[og_image.end():]
    return page_html


def upgrade_cover_refs(page_html, cover_slug, cover, sizes):
    """Point every reference to cover_slug's cover at the .jpg, and give its
    <img> tags srcset/sizes and the dimensions of the optimised file."""
    ref = re.compile(r"(/assets/blog/" + re.escape(cover_slug) + r"-cover)\.(?:png|jpe?g)\b")
    page_html = ref.sub(r"\1.jpg", page_html)

    attrs = cover_images.img_attrs(cover_slug, cover["widths"], sizes)
    dims = f'width="{cover["width"]}" height="{cover["height"]}"'

    def fix(m):
        tag = re.sub(r'\s(?:srcset|sizes)="[^"]*"', "", m.group(0))
        if re.search(r'width="\d+" height="\d+"', tag):
            tag = re.sub(r'width="\d+" height="\d+"', dims, tag)
        else:
            tag = tag[:-1] + " " + dims + ">"
        return tag[:-1] + attrs + ">"

    img = re.compile(r'<img src="/assets/blog/' + re.escape(cover_slug) + r'-cover\.jpg"[^>]*>')
    return img.sub(fix, page_html)


def _rewrite(path, transform, dry_run, changed):
    with open(path, encoding="utf-8") as fh:
        old = fh.read()
    new = transform(old)
    if new != old:
        changed.append(os.path.relpath(path, publish_post.ROOT))
        if not dry_run:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(new)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="report only, write nothing")
    args = ap.parse_args()

    root, img_dir, posts_dir = publish_post.ROOT, publish_post.IMG_DIR, publish_post.POSTS_DIR
    posts = publish_post.load_posts()["posts"]
    changed = []

    # ---- covers -----------------------------------------------------------
    covers = {}                                   # cover slug -> plan / existing set
    before = after = 0
    for path in sorted(glob.glob(os.path.join(img_dir, "*-cover.*"))):
        slug = os.path.basename(path).rsplit("-cover.", 1)[0]
        current = cover_images.existing(slug, img_dir)
        if current:
            covers[slug] = current
            continue
        before += os.path.getsize(path)
        if args.dry_run:
            covers[slug] = cover_images.plan(path)
            print(f"[dry run] optimise {os.path.basename(path)} "
                  f"({os.path.getsize(path) // 1024} KB)")
            continue
        written = cover_images.write_set(path, slug, img_dir)
        covers[slug] = cover_images.existing(slug, img_dir)
        size = sum(os.path.getsize(p) for p in written)
        after += size
        print(f"cover  {os.path.basename(path)}: {os.path.getsize(written[0]) // 1024} KB jpg, "
              + ", ".join(f"{os.path.getsize(p) // 1024} KB {os.path.basename(p).rsplit('-', 1)[1]}"
                          for p in written[1:]))

    # ---- pages ------------------------------------------------------------
    def refs(sizes):
        def transform(page_html):
            for slug, cover in covers.items():
                page_html = upgrade_cover_refs(page_html, slug, cover, sizes)
            return page_html
        return transform

    for slug in posts:
        path = os.path.join(posts_dir, slug + ".html")
        article = refs(publish_post.SIZES_ARTICLE)
        _rewrite(path, lambda h, s=slug: upsert_post_head(article(h), s), args.dry_run, changed)
    card_pages = [publish_post.INDEX] + sorted(
        glob.glob(os.path.join(publish_post.AUTHOR_PAGES_DIR, "*.html")))
    for path in card_pages + [os.path.join(root, "index.html")]:
        _rewrite(path, refs(publish_post.SIZES_CARD), args.dry_run, changed)

    for path, url in site_meta.static_pages(root):
        _rewrite(path, lambda h, u=url: add_canonical(h, u), args.dry_run, changed)

    if not args.dry_run:
        for slug in posts:
            changed += [os.path.relpath(p, root)
                        for p in site_meta.sync_hreflang(slug, posts, posts_dir)]
        site_meta.write_sitemap(root, posts)

    prefix = "[dry run] would change" if args.dry_run else "changed"
    for rel in sorted(set(changed)):
        print(f"{prefix} {rel}")
    if after:
        print(f"\ncovers: {before // 1024} KB → {after // 1024} KB")


if __name__ == "__main__":
    main()
