#!/usr/bin/env python3
"""One-time recovery of manuscripts + registry for pre-v2 posts.

For every aktuelles/<slug>.html (except index): reverse-convert to markdown,
verify the recovered manuscript regenerates the page word-for-word, then
store manuscript + registry entry. Pages that fail verification are recorded
as locked (editable: no, translatable: yes). Idempotent: slugs already in
posts.json are skipped unless --force.
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import publish_post
from html_to_md import page_to_md


def backfill(force=False):
    registry = publish_post.load_posts()
    results = []
    slugs = sorted(
        f[:-5] for f in os.listdir(publish_post.POSTS_DIR)
        if f.endswith(".html") and f != "index.html")
    for slug in slugs:
        if slug in registry["posts"] and not force:
            results.append((slug, "skipped"))
            continue
        page = open(os.path.join(publish_post.POSTS_DIR, slug + ".html"),
                    encoding="utf-8").read()
        r = page_to_md(page)
        entry_meta, _ = publish_post.match_author(
            r["author"] or "", publish_post.load_authors())
        base = re.sub(r"-([a-z]{2})$", "", slug)
        original = base if (base != slug and base in slugs
                            and slug[-2:] in publish_post.LANGS) else None
        entry = {
            "title": r["title"], "lang": r["lang"], "date": r["date"],
            "author": entry_meta["canonical"] if entry_meta else r["author"],
            "tag": r["tag"], "highlight": r["highlight"],
            "alt": r["alt"], "caption": r["caption"],
            "original_slug": original, "locked": False,
        }
        _, _, diffs = publish_post.check_fidelity(r["md"], page)
        if diffs:
            entry["locked"] = True
            registry["posts"][slug] = entry
            results.append((slug, "locked"))
            # A locked page has no trustworthy manuscript: never leave a
            # stale one behind (e.g. from before the page was hand-edited).
            stale = os.path.join(publish_post.MANUSCRIPTS_DIR, slug + ".md")
            if os.path.exists(stale):
                os.remove(stale)
            continue
        os.makedirs(publish_post.MANUSCRIPTS_DIR, exist_ok=True)
        with open(os.path.join(publish_post.MANUSCRIPTS_DIR, slug + ".md"),
                  "w", encoding="utf-8") as fh:
            fh.write(r["md"])
        registry["posts"][slug] = entry
        results.append((slug, "ok"))
    publish_post.save_posts(registry)
    return results


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true",
                    help="re-run even for slugs already in posts.json")
    for slug, status in backfill(force=ap.parse_args().force):
        print(f"  {status:8} {slug}")
