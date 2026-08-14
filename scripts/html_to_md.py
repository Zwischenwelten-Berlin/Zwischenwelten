#!/usr/bin/env python3
"""Reverse converter: generated post page HTML -> manuscript markdown.

Only ever needs to understand markup that publish_post.build_post emits.
Used by the backfill CLI and the app's rich-text endpoints.
"""

import html
import re

from manuscript_import import _MDBuilder


class _PageMDBuilder(_MDBuilder):
    """Extends the docx HTML->MD builder with the page's <cite> attribution.

    build_post renders a quote attribution as
    <cite><strong>Name</strong>role</cite>. We emit '> — **Name** — role'
    because split_attribution() parses that back into (Name, role), which
    regenerates the identical <cite>.
    """

    def __init__(self):
        super().__init__()
        self.cite = None          # [name_parts, role_parts] while inside <cite>
        self.cite_strong = False
        # Depth counter for a <div> that build_post never emits (hand-built
        # markup). Its content is not part of the known vocabulary, so it is
        # dropped rather than absorbed as prose — a page containing one can
        # never be reconstructed word-for-word and must come back "locked".
        self.foreign_div_depth = 0

    def handle_starttag(self, tag, attrs):
        if self.foreign_div_depth:
            if tag == "div":
                self.foreign_div_depth += 1
            return
        if tag == "div" and dict(attrs).get("class") != "table-wrap":
            self.foreign_div_depth = 1
        elif tag == "cite":
            self.cite = ([], [])
        elif self.cite is not None and tag in ("strong", "b"):
            self.cite_strong = True
        elif self.cite is None:
            super().handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if self.foreign_div_depth:
            if tag == "div":
                self.foreign_div_depth -= 1
            return
        if tag == "cite":
            name = re.sub(r"\s+", " ", "".join(self.cite[0])).strip()
            role = re.sub(r"\s+", " ", "".join(self.cite[1])).strip(" ,–—-")
            line = f"> — **{name}**" if name else ""
            if role:
                line += f" — {role}"
            if line:
                self.quote_paras.append(line)
            self.cite = None
        elif self.cite is not None and tag in ("strong", "b"):
            self.cite_strong = False
        elif self.cite is None:
            super().handle_endtag(tag)

    def handle_data(self, data):
        if self.foreign_div_depth:
            return
        if self.cite is not None:
            self.cite[0 if self.cite_strong else 1].append(data)
        else:
            super().handle_data(data)


def fragment_to_md(html_text):
    """Body-level HTML fragment -> markdown (h1 -> '# ', em-para -> *…*)."""
    b = _PageMDBuilder()
    b.feed(html_text)
    b.close()
    md, _warnings = b.result()
    return md


def _first(pattern, html, flags=re.S):
    m = re.search(pattern, html, flags)
    return m.group(1).strip() if m else None


def _text(s):
    if not s:
        return None
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s)).strip())


def page_to_md(page_html):
    """Generated post page -> {'md': manuscript, ...metadata}. """
    lang = _first(r'<html lang="([a-z]{2})">', page_html) or "de"
    date = _first(r'<time datetime="(\d{4}-\d{2}-\d{2})">', page_html)
    tag = _text(_first(r'<span class="article-tag">(.*?)</span>', page_html))
    title_html = _first(r'<h1 class="article-title"[^>]*>(.*?)</h1>', page_html)
    title = _text(title_html)
    highlight = _text(_first(r"<em>(.*?)</em>", title_html or "", re.S))
    subtitle = _text(_first(r'<p class="article-subtitle">(.*?)</p>', page_html))
    author = _text(_first(
        r'<p class="article-author">[^<]*<strong>(.*?)</strong>', page_html))
    cover = _first(r'<section class="article-cover">.*?<img src="[^"]*" alt="([^"]*)"',
                   page_html)
    cover = html.unescape(cover) if cover else None
    alt = cover if cover and cover != title else None
    caption = _text(_first(r"<figcaption>(.*?)</figcaption>", page_html))

    body_html = _first(
        r'<div class="article-prose">(.*?)<div class="article-back">', page_html)
    body_md = fragment_to_md(body_html or "")

    parts = [f"# {title}"]
    if subtitle:
        parts.append(f"*{subtitle}*")
    if author:
        parts.append(f"Author: {author}")
    if body_md:
        parts.append(body_md)
    return {
        "md": "\n\n".join(parts) + "\n",
        "title": title, "subtitle": subtitle, "lang": lang, "date": date,
        "author": author, "tag": tag, "highlight": highlight,
        "alt": alt, "caption": caption,
    }
