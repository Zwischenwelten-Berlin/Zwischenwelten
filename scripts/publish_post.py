#!/usr/bin/env python3
"""Publish a markdown manuscript as a ZWISCHENWELTEN blog post.

Converts a .md file into a post that matches the house style (assets/blog.css),
copies the cover image, registers the author, and adds a card to /aktuelles.

The conversion is deliberately verbatim: headings, paragraphs, lists and quotes
change shape, never wording. Before writing anything the script compares the
manuscript against the generated page word by word and refuses to publish when
they differ, so a post can never silently drift from its source.

    python3 scripts/publish_post.py --md post.md --image cover.jpg --lang de

Run with --help for all options.
"""

import argparse
import difflib
import glob
import html as htmllib
import json
import os
import re
import shutil
import struct
import sys
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POSTS_DIR = os.path.join(ROOT, "aktuelles")
INDEX = os.path.join(POSTS_DIR, "index.html")
IMG_DIR = os.path.join(ROOT, "assets", "blog")
AUTHORS = os.path.join(IMG_DIR, "authors.json")
MANUSCRIPTS_DIR = os.path.join(IMG_DIR, "manuscripts")
POSTS_JSON = os.path.join(IMG_DIR, "posts.json")
AUTHOR_PAGES_DIR = os.path.join(ROOT, "journalistennetzwerk")
NETWORK_PAGE = os.path.join(ROOT, "journalistennetzwerk.html")
SITE = "https://zwischenwelten.berlin"


def load_posts():
    if not os.path.exists(POSTS_JSON):
        return {"posts": {}}
    with open(POSTS_JSON, encoding="utf-8") as fh:
        return json.load(fh)


def save_posts(registry):
    with open(POSTS_JSON, "w", encoding="utf-8") as fh:
        json.dump(registry, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


# --------------------------------------------------------------------------
# Language table. Every string here is site chrome, never manuscript content.
# --------------------------------------------------------------------------
MONTHS = {
    "de": "Januar Februar März April Mai Juni Juli August September Oktober November Dezember".split(),
    "en": "January February March April May June July August September October November December".split(),
    "tr": "Ocak Şubat Mart Nisan Mayıs Haziran Temmuz Ağustos Eylül Ekim Kasım Aralık".split(),
    "ru": "января февраля марта апреля мая июня июля августа сентября октября ноября декабря".split(),
    "uk": "січня лютого березня квітня травня червня липня серпня вересня жовтня листопада грудня".split(),
    "ar": "يناير فبراير مارس أبريل مايو يونيو يوليو أغسطس سبتمبر أكتوبر نوفمبر ديسمبر".split(),
    "ku": "Rêbendan Reşemî Adar Avrêl Gulan Pûşper Tîrmeh Gelawêj Rezber Kewçêr Sermawez Berfanbar".split(),
    "fa": "جنوری فبروری مارچ اپریل می جون جولای اگست سپتامبر اکتبر نومبر دسمبر".split(),
}

LANGS = {
    "de": dict(label="Deutsch", locale="de_DE", rtl=False, date="{d}. {m} {y}",
               read_more="Weiterlesen", back="Zurück zu Aktuelles",
               by="Autor", published="Veröffentlicht am", quotes=("„", "“")),
    "en": dict(label="English", locale="en_GB", rtl=False, date="{d} {m} {y}",
               read_more="Read more", back="Back to news",
               by="Author", published="Published", quotes=("“", "”")),
    "tr": dict(label="Türkçe", locale="tr_TR", rtl=False, date="{d} {m} {y}",
               read_more="Devamını oku", back="Haberlere dön",
               by="Yazar", published="tarihinde yayımlandı", quotes=("“", "”")),
    "ru": dict(label="Русский", locale="ru_RU", rtl=False, date="{d} {m} {y}",
               read_more="Читать далее", back="Назад к новостям",
               by="Автор", published="Опубликовано", quotes=("«", "»")),
    "uk": dict(label="Українська", locale="uk_UA", rtl=False, date="{d} {m} {y}",
               read_more="Читати далі", back="Назад до новин",
               by="Автор", published="Опубліковано", quotes=("«", "»")),
    "ar": dict(label="العربية", locale="ar_AR", rtl=True, date="{d} {m} {y}",
               read_more="اقرأ المزيد", back="العودة إلى الأخبار",
               by="الكاتب", published="نُشر في", quotes=("«", "»")),
    "ku": dict(label="Kurdî", locale="ku_TR", rtl=False, date="{d} {m} {y}",
               read_more="Zêdetir bixwîne", back="Vegere nûçeyan",
               by="Nivîskar", published="Hatiye weşandin", quotes=("“", "”")),
    "fa": dict(label="فارسی", locale="fa_IR", rtl=True, date="{d} {m} {y}",
               read_more="ادامه مطلب", back="بازگشت به اخبار",
               by="نویسنده", published="منتشر شده در", quotes=("«", "»")),
}

# Order of chips in the overview filter.
CHIP_ORDER = ["de", "en", "tr", "ru", "uk", "ar", "ku", "fa"]


def die(msg):
    sys.exit(f"\n✗ {msg}\n")


def info(msg):
    print(f"  {msg}")


class PublishError(Exception):
    """Raised by build_post instead of exiting; .diffs carries fidelity diffs."""
    def __init__(self, message, diffs=None):
        super().__init__(message)
        self.diffs = diffs or []


# --------------------------------------------------------------------------
# Author registry
# --------------------------------------------------------------------------
CYR = {
    "а": "a", "б": "b", "в": "v", "г": "g", "ґ": "g", "д": "d", "е": "e", "є": "ye",
    "ж": "zh", "з": "z", "и": "i", "і": "i", "ї": "yi", "й": "y", "к": "k", "л": "l",
    "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y",
    "ь": "", "э": "e", "ю": "yu", "я": "ya", "ё": "e",
}


def fold(name):
    """Reduce a name to a comparable ASCII skeleton (diacritics, Cyrillic, case)."""
    s = name.strip().lower()
    s = "".join(CYR.get(ch, ch) for ch in s)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("ğ", "g").replace("ı", "i").replace("ş", "s").replace("ö", "o")
    s = s.replace("ü", "u").replace("ç", "c").replace("ß", "ss")
    return re.sub(r"[^a-z ]", "", s).strip()


def load_authors():
    with open(AUTHORS, encoding="utf-8") as fh:
        return json.load(fh)


def match_author(name, registry):
    """Return (entry, score) for the closest known author, or (None, best_score)."""
    target = fold(name)
    best, best_score = None, 0.0
    for entry in registry["authors"]:
        candidates = [entry["canonical"], *entry.get("aliases", []), *entry.get("names", {}).values()]
        for cand in candidates:
            score = difflib.SequenceMatcher(None, target, fold(cand)).ratio()
            if score > best_score:
                best, best_score = entry, score
    return (best, best_score) if best_score >= 0.85 else (None, best_score)


BYLINE = re.compile(
    r"^\s*(?:\*{0,3})\s*(?:author|by|autor|autorin|yazar|автор|нивîskar|nivîskar|الكاتب|نویسنده)\s*[::]\s*(.+?)\s*(?:\*{0,3})\s*$",
    re.I | re.M,
)


def find_author_in_md(text):
    """Pull an explicit byline out of the manuscript, if it has one."""
    m = BYLINE.search(text)
    if not m:
        return None
    name = re.sub(r"[*_]", "", m.group(1)).strip().rstrip(".,")
    return name or None


# --------------------------------------------------------------------------
# Markdown -> house-style HTML
# --------------------------------------------------------------------------
def esc(s):
    return htmllib.escape(s, quote=False)


def smart_quotes(text, open_q, close_q):
    """Straight quotes -> paired typographic quotes, decided by context.

    Alternating open/close breaks when a passage already uses typographic marks,
    so each quote is judged by what precedes it instead.
    """
    out = []
    for i, ch in enumerate(text):
        if ch == '"':
            prev = text[i - 1] if i else ""
            out.append(open_q if (not prev or prev in " \t\n([{—–-„«“") else close_q)
        else:
            out.append(ch)
    return "".join(out)


def inline(text, lang):
    """Inline markdown -> HTML. Typography changes; wording does not."""
    open_q, close_q = LANGS[lang]["quotes"]
    text = esc(text)
    # links first so their text is not mangled
    links = []

    def stash(m):
        links.append((m.group(1), m.group(2)))
        return f"\x00{len(links)-1}\x00"

    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", stash, text)
    text = re.sub(r"\*\*\*(.+?)\*\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", text)
    # dashes: --- em, -- en
    text = text.replace("---", "—").replace("--", "–")
    text = smart_quotes(text, open_q, close_q)
    # bare e-mail addresses become links (trailing punctuation stays outside)
    text = re.sub(r"(?<![\w:>@.])([\w.+-]+@[\w-]+(?:\.[\w-]+)+)",
                  r'<a href="mailto:\1">\1</a>', text)
    for i, (label, url) in enumerate(links):
        href = url.strip()
        text = text.replace(f"\x00{i}\x00", f'<a href="{href}">{label}</a>')
    return text


def split_attribution(line):
    """'--- Name, role' / '***Name** — role*' -> (name, role)."""
    s = re.sub(r"[*_]", "", line.strip())          # emphasis first…
    s = re.sub(r"^\s*[—–-]{1,3}\s*", "", s).strip()  # …then the leading dash
    for sep in [",", "،", "—", "–", " - ", "|"]:
        if sep in s:
            name, role = s.split(sep, 1)
            return name.strip(), role.strip()
    return s, ""


def md_to_blocks(md, lang):
    """Convert the manuscript body into the site's article markup."""
    lines = md.split("\n")
    out, i = [], 0
    ind = " " * 16

    while i < len(lines):
        raw = lines[i]
        line = raw.strip()

        if not line:
            i += 1
            continue

        # thematic break
        if re.fullmatch(r"(\*\s*){3,}|(-\s*){3,}|(_\s*){3,}", line):
            i += 1
            continue

        # headings
        m = re.match(r"^(#{2,6})\s+(.*)$", line)
        if m:
            level = min(len(m.group(1)), 3)
            out.append(f"{ind}<h{level}>{inline(m.group(2).strip(), lang)}</h{level}>")
            i += 1
            continue

        # blockquote -> pull quote
        if line.startswith(">"):
            block = []
            while i < len(lines) and (lines[i].strip().startswith(">") or not lines[i].strip()):
                if not lines[i].strip():
                    if i + 1 < len(lines) and lines[i + 1].strip().startswith(">"):
                        block.append("")
                        i += 1
                        continue
                    break
                block.append(re.sub(r"^\s*>\s?", "", lines[i]).rstrip())
                i += 1
            chunks = [c.strip() for c in "\n".join(block).split("\n") if c.strip()]
            if not chunks:
                continue
            attribution = ""
            if len(chunks) > 1 and re.match(r"^\s*(?:[—–-]{1,3}|\*{1,3}\s*[—–-]{1,3})", chunks[-1]):
                attribution = chunks.pop()
            elif len(chunks) > 1 and re.fullmatch(r"\*{2,3}.+\*{2,3}", chunks[-1]):
                attribution = chunks.pop()
            body = " ".join(chunks)
            block = [f'{ind}<blockquote class="pull-quote">',
                     f"{ind}  <p>{inline(body, lang)}</p>"]
            if attribution:
                name, role = split_attribution(attribution)
                cite = f"<strong>{inline(name, lang)}</strong>"
                if role:
                    cite += inline(role, lang)
                block.append(f"{ind}  <cite>{cite}</cite>")
            block.append(f"{ind}</blockquote>")
            out.append("\n".join(block))
            continue

        # table
        if line.startswith("|") and i + 1 < len(lines) and \
                re.fullmatch(r"\|[\s:|-]+\|", lines[i + 1].strip()):
            def cells(row):
                return [c.strip() for c in row.strip().strip("|").split("|")]
            header = cells(lines[i])
            i += 2
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(cells(lines[i]))
                i += 1
            block = [f'{ind}<div class="table-wrap">', f"{ind}  <table>", f"{ind}    <thead>",
                     f"{ind}      <tr>"]
            block += [f"{ind}        <th>{inline(c, lang)}</th>" for c in header]
            block += [f"{ind}      </tr>", f"{ind}    </thead>", f"{ind}    <tbody>"]
            for r in rows:
                block.append(f"{ind}      <tr>")
                block += [f"{ind}        <td>{inline(c, lang)}</td>" for c in r]
                block.append(f"{ind}      </tr>")
            block += [f"{ind}    </tbody>", f"{ind}  </table>", f"{ind}</div>"]
            out.append("\n".join(block))
            continue

        # list
        if re.match(r"^[-*+]\s+", line):
            items = []
            while i < len(lines) and re.match(r"^\s*[-*+]\s+", lines[i]):
                items.append(re.sub(r"^\s*[-*+]\s+", "", lines[i]).strip())
                i += 1
            block = [f"{ind}<ul>"]
            block += [f"{ind}  <li>{inline(it, lang)}</li>" for it in items]
            block.append(f"{ind}</ul>")
            out.append("\n".join(block))
            continue

        # paragraph (join wrapped lines)
        para = []
        while i < len(lines) and lines[i].strip() and not re.match(
                r"^\s*(#{2,6}\s|>|[-*+]\s)", lines[i]):
            para.append(lines[i].strip())
            i += 1
        out.append(f"{ind}<p>{inline(' '.join(para), lang)}</p>")

    return "\n\n".join(out)


def parse_md(text, lang, subtitle_mode="auto"):
    text = text.replace("\r\n", "\n")
    text = BYLINE.sub("", text)  # byline is metadata, not body copy

    m = re.search(r"^#\s+(.*)$", text, re.M)
    if not m:
        raise PublishError("The manuscript has no '# Title' line.")
    title = m.group(1).strip()
    rest = text[m.end():].lstrip("\n")

    subtitle = ""
    if subtitle_mode != "none":
        first = rest.split("\n\n", 1)[0].strip()
        italic = re.fullmatch(r"\*(.+)\*", first) or re.fullmatch(r"_(.+)_", first)
        heading = re.fullmatch(r"##\s+(.*)", first)
        if italic and subtitle_mode in ("auto", "italic"):
            subtitle = italic.group(1).strip()
            rest = rest.split("\n\n", 1)[1] if "\n\n" in rest else ""
        elif heading and subtitle_mode in ("auto", "heading"):
            subtitle = heading.group(1).strip()
            rest = rest.split("\n\n", 1)[1] if "\n\n" in rest else ""

    return title, subtitle, rest


# --------------------------------------------------------------------------
# Fidelity gate — the manuscript and the page must contain the same words
# --------------------------------------------------------------------------
def words(text):
    t = htmllib.unescape(text)
    t = re.sub(r"\S*@\S*\.\w+\S*", " EMAIL ", t)
    t = re.sub(r"^\s*\|[\s:|-]+\|\s*$", " ", t, flags=re.M)   # table rule row
    t = t.replace("|", " ")
    t = t.replace("---", "—").replace("--", "—").replace("–", "—")
    for q in ['"', "„", "“", "”", "«", "»", "‟", "‚", "‘", "’", "'"]:
        t = t.replace(q, "'")
    t = t.replace(" ", " ")
    t = re.sub(r"[*#>`\[\]_]", " ", t)
    t = re.sub(r"^\s*[-•+*]\s*", " ", t, flags=re.M)
    t = re.sub(r"\(mailto:[^)]*\)", " ", t)
    t = re.sub(r"\(https?://[^)]*\)", " ", t)
    t = re.sub(r"[,.;:!?()،؛]", " ", t)
    t = re.sub(r"\s—\s", " ", t)          # attribution dash is styling
    return re.sub(r"\s+", " ", t).strip().lower().split()


def check_fidelity(md_text, page_html):
    src = BYLINE.sub("", md_text)
    body = re.search(r'<div class="article-prose">(.*?)<div class="article-back">',
                     page_html, re.S)
    title = re.search(r'<h1 class="article-title"[^>]*>(.*?)</h1>', page_html, re.S)
    sub = re.search(r'<p class="article-subtitle">(.*?)</p>', page_html, re.S)
    rendered = " ".join(re.sub(r"<[^>]+>", " ", m.group(1)) if m else ""
                        for m in (title, sub, body))
    a, b = words(src), words(rendered)
    diffs = [op for op in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes()
             if op[0] != "equal"]
    return a, b, diffs


# --------------------------------------------------------------------------
# Image
# --------------------------------------------------------------------------
def image_size(path):
    with open(path, "rb") as fh:
        head = fh.read(32)
        if head[:8] == b"\x89PNG\r\n\x1a\n":
            w, h = struct.unpack(">II", head[16:24])
            return w, h
        if head[:2] == b"\xff\xd8":
            fh.seek(2)
            while True:
                b = fh.read(1)
                while b and b != b"\xff":
                    b = fh.read(1)
                marker = fh.read(1)
                if not marker:
                    break
                if marker[0] in range(0xC0, 0xCF) and marker[0] not in (0xC4, 0xC8, 0xCC):
                    fh.read(3)
                    h, w = struct.unpack(">HH", fh.read(4))
                    return w, h
                size = struct.unpack(">H", fh.read(2))[0]
                fh.seek(size - 2, 1)
    return None, None


# --------------------------------------------------------------------------
# Page + card rendering
# --------------------------------------------------------------------------
PAGE = """<!DOCTYPE html>
<html lang="{lang}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title_plain} – ZWISCHENWELTEN</title>
  <meta name="description" content="{description}">
  <meta name="robots" content="index,follow">
  <meta name="theme-color" content="#123f7a">
  <meta name="color-scheme" content="light">

  <link rel="icon" href="/favicon.ico">

  <meta property="og:type" content="article">
  <meta property="og:locale" content="{locale}">
  <meta property="og:site_name" content="ZWISCHENWELTEN">
  <meta property="og:title" content="{title_plain}">
  <meta property="og:description" content="{description}">
  <meta property="og:image" content="{site}{cover}">

  <link rel="stylesheet" href="/assets/fonts.css">
  <link rel="stylesheet" href="/assets/consent.css">

  <link rel="stylesheet" href="/assets/site.css">
  <link rel="stylesheet" href="/assets/blog.css">

  <script type="application/ld+json">
  {{
    "@context":"https://schema.org",
    "@type":"NewsArticle",
    "headline":"{title_plain}",
    "description":"{description}",
    "image":"{site}{cover}",
    "datePublished":"{iso_date}",
    "inLanguage":"{lang}",
    "author":{{
      "@type":"{author_type}",
      "name":"{author}"
    }},
    "publisher":{{
      "@type":"Organization",
      "name":"ZWISCHENWELTEN"
    }}
  }}
  </script>
</head>
<body>
  <a href="#main" class="skip-link">Zum Inhalt springen</a>

  <div class="site-shell">
    <header class="top-nav" aria-label="Kopfbereich">
      <div class="container top-nav-inner">
        <a href="/" class="brand" aria-label="ZWISCHENWELTEN Startseite">
          <img src="/ZW_logo.png" alt="ZWISCHENWELTEN">
        </a>

        <nav aria-label="Hauptnavigation">
          <ul class="nav-links">
            <li><a href="/aktuelles" class="is-current" aria-current="page">Aktuelles</a></li>
            <li><a href="/ueber-uns">Über uns</a></li>
            <li><a href="/journalistennetzwerk">Journalistennetzwerk</a></li>
            <li><a href="/buergerredaktion">Bürgerredaktion</a></li>
            <li><a href="/mitmachen">Mach mit!</a></li>
            <li><a href="/medienpreis">Medienpreis</a></li>
          </ul>
        </nav>

        <div class="nav-actions">
          <a href="/kontakt" class="pill-btn">Kontakt</a>
        </div>
      </div>
    </header>

    <main id="main">

      <!-- ARTICLE HERO -->
      <article aria-labelledby="article-title"{dir_attr}>
        <section class="article-hero">
          <div class="container">
            <div class="article-meta">{tag_html}
              <span class="article-meta-line">
                <time datetime="{iso_date}">{date_label}</time>
                <span class="sep" aria-hidden="true">·</span>
                {author}
                <span class="sep" aria-hidden="true">·</span>
                {lang_label}
              </span>
            </div>
            <h1 class="article-title" id="article-title">{title_html}</h1>{subtitle_html}
          </div>
        </section>

        <!-- COVER -->
        <section class="article-cover">
          <div class="container">
            <figure>
              <img src="{cover}" alt="{alt}"{dims}>{caption_html}
            </figure>
          </div>
        </section>

        <!-- BODY -->
        <section class="article-body">
          <div class="container">
            <div class="article-card">
              <div class="article-prose">
{body}

                <div class="article-back">
                  <p class="article-author">{by}: <strong>{author}</strong> · {published_line}</p>
                  <a href="/aktuelles" class="back-link">← {back}</a>
                </div>
              </div>
            </div>
          </div>
        </section>
      </article>

    </main>

    <footer class="footer" aria-label="Fußbereich">
      <div class="container">
        <div class="partners" aria-label="Projektpartner">
          <span class="partners-label">Unterstützt durch</span>
          <div class="partners-logos">
            <a href="https://www.berlin.de/" class="partner-logo" target="_blank" rel="noopener" aria-label="Land Berlin">
              <img src="/berlin_logo.png" alt="Land Berlin">
            </a>
            <a href="https://www.degewo.de/" class="partner-logo" target="_blank" rel="noopener" aria-label="degewo">
              <img src="/Degewo_Logo.svg.png" alt="degewo">
            </a>
          </div>
        </div>

        <div class="footer-inner">
          <div>ZWISCHENWELTEN · Berlin · Bürgerredaktion · Journalistennetzwerk · Medienwettbewerb 2026</div>
          <div class="footer-links">
            <a href="/ueber-uns">Über uns</a>
            <a href="/kontakt">Kontakt</a>
            <a href="/impressum">Impressum</a>
            <a href="/datenschutz">Datenschutz</a>
          </div>
        </div>
      </div>
    </footer>
  </div>
  <script src="/assets/consent.js" defer></script>
</body>
</html>
"""

CARD = """            <a class="post-card" href="/aktuelles/{slug}" data-lang="{lang}" hreflang="{lang}" lang="{lang}">
              <div class="post-thumb">
                <img src="{cover}" alt="{alt}" loading="lazy"{dims}>
                <span class="post-lang-badge"><span class="dot" aria-hidden="true"></span>{lang_label}</span>
              </div>
              <div class="post-info">
                <p class="post-meta">
                  <time datetime="{iso_date}">{date_label}</time>
                  <span class="sep" aria-hidden="true">·</span>
                  <span>{author}</span>
                </p>
                <h2 class="post-title">{title_plain}</h2>
                <p class="post-excerpt">{excerpt}</p>
                <span class="post-cta">{read_more} →</span>
              </div>
            </a>
"""

AUTHOR_CARD = """            <a class="post-card" href="/aktuelles/{slug}" data-lang="{lang}" hreflang="{lang}" lang="{lang}">
              <div class="post-thumb">
                <img src="{cover}" alt="{alt}" loading="lazy"{dims}>
                <div class="post-badges">
                  <span class="post-lang-badge"><span class="dot" aria-hidden="true"></span>{lang_label}</span>{translation_badge}
                </div>
              </div>
              <div class="post-info">
                <p class="post-meta">
                  <time datetime="{iso_date}">{date_label}</time>
                </p>
                <h3 class="post-title">{title_plain}</h3>
                <p class="post-excerpt">{excerpt}</p>
                <span class="post-cta">{read_more} →</span>
              </div>
            </a>
"""

# Marks a card on the author page as a translation of one of their originals.
# Always German — the author page itself is German, unlike the post it links to.
TRANSLATION_BADGE = (
    '\n                  <span class="post-translation-badge">Übersetzung</span>')


AUTHOR_PAGE_TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "author_page_template.html")


def render_author_page(name, role, bio_paragraphs, photo_rel):
    """Render a new author page from scripts/author_page_template.html.

    Manual placeholder replacement (not str.format) because the template's
    embedded CSS/JS is full of literal braces.
    """
    tpl = open(AUTHOR_PAGE_TEMPLATE, encoding="utf-8").read()
    bio_html = "\n                  ".join(
        f"<p>{esc(p)}</p>" for p in bio_paragraphs if p.strip())
    # __NAME__ lands in the photo's alt="..." (and __DESCRIPTION__ in a
    # meta content="...") as well as in plain text — esc() alone leaves
    # embedded double quotes unescaped (quote=False), which would break
    # those attributes, so both also get the same '"' -> '&quot;' pass
    # build_post's own PAGE template uses for its attribute values.
    for key, val in [
        ("__NAME__", esc(name).replace('"', "&quot;")),
        ("__ROLE__", esc(role)),
        ("__PHOTO__", photo_rel),
        ("__BIO__", bio_html),
        ("__DESCRIPTION__",
         esc(f"{name} – {role}. Porträt und Beiträge auf ZWISCHENWELTEN.")
         .replace('"', "&quot;")),
    ]:
        tpl = tpl.replace(key, val)
    return tpl


def author_page_path(author_id):
    return os.path.join(AUTHOR_PAGES_DIR, f"{author_id}.html")


def link_network_member(page_html, name, role, author_id):
    """Make sure the Journalistennetzwerk members grid links to the author's
    page. Returns (html, changed): an existing card for the name gets the
    "Mehr erfahren" link appended, a missing card is created at the end of
    the grid, and a card that already links stays untouched.
    """
    link = ('              <a class="info-more" href="/journalistennetzwerk/'
            f"{author_id}\">Mehr erfahren &amp; Beiträge →</a>\n")
    card = re.search(
        rf'([ \t]*<article class="info-card">\s*<h3>{re.escape(esc(name))}</h3>.*?)'
        r'([ \t]*</article>)',
        page_html, re.S)
    if card:
        if 'class="info-more"' in card.group(1):
            return page_html, False
        return page_html[:card.end(1)] + link + page_html[card.end(1):], True
    grid = re.search(r'<div class="card-grid">(.*?)\n[ \t]*</div>', page_html, re.S)
    if not grid:
        raise PublishError(
            "journalistennetzwerk.html hat kein card-grid — "
            "Mitgliederkarte kann nicht eingefügt werden.")
    new_card = ('\n\n            <article class="info-card">\n'
                f"              <h3>{esc(name)}</h3>\n"
                f'              <p class="info-role">{esc(role)}</p>\n'
                f"{link}"
                "            </article>")
    return page_html[:grid.end(1)] + new_card + page_html[grid.end(1):], True


def upsert_author_card(page_html, card, slug, original_slug=None):
    """Insert or replace one post's card on an author page.

    A card that is already there is replaced where it stands. A translation is
    grouped under its original, after any siblings already sitting there, so a
    post and its translations stay together; everything else goes to the top of
    the grid. Falls back to the top when the original has no card on this page
    (it may belong to a different author, or predate the page).
    """
    existing = re.search(
        rf'[ \t]*<a class="post-card" href="/aktuelles/{re.escape(slug)}".*?</a>\n',
        page_html, re.S)
    if existing:
        return page_html[:existing.start()] + card + page_html[existing.end():]

    if original_slug:
        orig = re.search(
            rf'[ \t]*<a class="post-card" href="/aktuelles/{re.escape(original_slug)}".*?</a>\n',
            page_html, re.S)
        if orig:
            sibling = re.compile(r'\n[ \t]*<a class="post-card" .*?</a>\n', re.S)
            pos = orig.end()
            while True:
                m = sibling.match(page_html, pos)
                if not m or "post-translation-badge" not in m.group(0):
                    break
                pos = m.end()
            return page_html[:pos] + "\n" + card + page_html[pos:]

    anchor = re.search(r'<div class="posts-grid">\n', page_html)
    if not anchor:
        raise PublishError("Autorenseite hat kein posts-grid — Karte kann nicht eingefügt werden.")
    return page_html[:anchor.end()] + "\n" + card + page_html[anchor.end():]


def strip_tags(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s)).strip()


def teaser(subtitle, body_html, limit=260):
    first_p = re.search(r"<p>(.*?)</p>", body_html, re.S)
    text = strip_tags(first_p.group(1)) if first_p else ""
    lead = f"{subtitle}: {text}" if subtitle else text
    if len(lead) <= limit:
        return lead
    cut = lead[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(" ,;:—–-") + " …"


def slugify(title):
    s = fold(title)
    return re.sub(r"\s+", "-", s)[:60].strip("-") or "post"


# --------------------------------------------------------------------------
# Overview page updates
# --------------------------------------------------------------------------
def add_chip(index_html, lang):
    """Make sure the filter offers this language."""
    if f'data-lang="{lang}"' in index_html.split("</div>", 1)[0] or \
       re.search(rf'class="lang-chip" data-lang="{lang}"', index_html):
        return index_html, False
    chip = (f'            <button type="button" class="lang-chip" data-lang="{lang}" '
            f'aria-pressed="false">{LANGS[lang]["label"]}</button>\n')
    # insert in CHIP_ORDER position
    later = [l for l in CHIP_ORDER[CHIP_ORDER.index(lang) + 1:]
             if re.search(rf'class="lang-chip" data-lang="{l}"', index_html)] if lang in CHIP_ORDER else []
    if later:
        anchor = re.search(rf'^.*class="lang-chip" data-lang="{later[0]}".*$\n',
                           index_html, re.M)
        index_html = index_html[:anchor.start()] + chip + index_html[anchor.start():]
    else:
        last = list(re.finditer(r'^.*class="lang-chip".*$\n', index_html, re.M))[-1]
        index_html = index_html[:last.end()] + chip + index_html[last.end():]
    # keep the filter's accepted-language list in sync
    m = re.search(r"var langs = \[(.*?)\];", index_html)
    if m and f"'{lang}'" not in m.group(1):
        index_html = index_html.replace(
            m.group(0), f"var langs = [{m.group(1)}, '{lang}'];")
    return index_html, True


def add_card(index_html, card):
    anchor = '<div class="posts-grid" id="posts-grid">\n'
    if anchor not in index_html:
        raise PublishError("Could not find the post grid in aktuelles/index.html.")
    return index_html.replace(anchor, anchor + "\n" + card, 1)


def replace_card(index_html, card, slug):
    existing = re.search(
        rf'[ \t]*<a class="post-card" href="/aktuelles/{re.escape(slug)}".*?</a>\n',
        index_html, re.S)
    if not existing:
        return add_card(index_html, card)
    return index_html[:existing.start()] + card + index_html[existing.end():]


# --------------------------------------------------------------------------
def build_post(md_text, image_path, lang, date, author=None, slug=None, tag=None,
               highlight=None, alt=None, caption=None, subtitle_from="auto",
               new_author=False, write=False, original_slug=None, update=False):
    """Build (and optionally write) a blog post from a manuscript + cover image.

    Raises PublishError on any failure. Returns a dict describing the post;
    see the module docstring / task brief for the exact shape.
    """
    cfg = LANGS[lang]

    # ---- author -----------------------------------------------------------
    registry = load_authors()
    name = author or find_author_in_md(md_text)
    if not name:
        raise PublishError(
            "No author found. Add a byline like 'Author: Name' to the manuscript, "
            "or pass --author \"Name\".")
    entry, score = match_author(name, registry)
    author_new = False
    if entry and not new_author:
        author_display = entry.get("names", {}).get(lang) or entry["canonical"]
        author_canonical = entry["canonical"]
        author_id = entry["id"]
        # a desk/team byline ("Redaktion") is an Organization in schema.org
        author_is_org = bool(entry.get("org"))
        info(f"Author: '{name}' → known author {entry['canonical']} "
             f"(match {score:.0%}), using '{author_display}' for {lang}.")
    else:
        author_display = name
        author_canonical = None
        author_is_org = False
        if not new_author:
            raise PublishError(
                f"'{name}' does not match any known author (closest {score:.0%}).\n"
                f"  Re-run with --new-author to register them, or pass --author with "
                f"the spelling used in assets/blog/authors.json.")
        author_new = True
        author_id = slugify(name)
        info(f"Author: registering new author '{name}'.")
        registry["authors"].append({
            "id": author_id, "canonical": name, "role": "",
            "names": {lang: name}, "aliases": [],
        })

    # ---- manuscript -------------------------------------------------------
    title, subtitle, body_md = parse_md(md_text, lang, subtitle_from)
    body = md_to_blocks(body_md, lang)
    info(f"Title: {title}")
    info(f"Subtitle: {subtitle or '(none)'}")

    post_slug = slug or slugify(title)
    page_path = os.path.join(POSTS_DIR, post_slug + ".html")

    if update:
        if slug is None:
            raise PublishError("Update braucht einen --slug.")
        registry_posts = load_posts()["posts"]
        if slug not in registry_posts or not os.path.exists(page_path):
            raise PublishError(f"'{slug}' ist nicht im Register — nur veröffentlichte "
                               f"Beiträge können aktualisiert werden.")
        if registry_posts[slug].get("locked"):
            raise PublishError(f"'{slug}' ist gesperrt (Seite mit handgebauten Elementen) "
                               f"und kann nicht im Editor bearbeitet werden.")
        original_slug = original_slug or registry_posts[slug].get("original_slug")
    elif write and os.path.exists(page_path):
        raise PublishError(f"{page_path} already exists. Pass a different --slug.")

    # ---- cover ------------------------------------------------------------
    old_cover_path = None
    if image_path is None:
        if not update:
            raise PublishError("image_path fehlt (nur bei --update optional).")
        matches = glob.glob(os.path.join(IMG_DIR, f"{post_slug}-cover.*"))
        if not matches:
            raise PublishError(f"Kein bestehendes Cover für '{post_slug}' gefunden.")
        existing_cover = matches[0]
        ext = os.path.splitext(existing_cover)[1].lower()
        cover_rel = f"/assets/blog/{post_slug}-cover{ext}"
        w, h = image_size(existing_cover)
        dims = f' width="{w}" height="{h}"' if w and h else ""
    else:
        ext = os.path.splitext(image_path)[1].lower() or ".jpg"
        cover_rel = f"/assets/blog/{post_slug}-cover{ext}"
        w, h = image_size(image_path)
        dims = f' width="{w}" height="{h}"' if w and h else ""
        if update:
            existing = glob.glob(os.path.join(IMG_DIR, f"{post_slug}-cover.*"))
            if existing and os.path.splitext(existing[0])[1].lower() != ext:
                old_cover_path = existing[0]

    # ---- assemble ---------------------------------------------------------
    y, mo, d = (int(x) for x in date.split("-"))
    date_label = cfg["date"].format(d=d, m=MONTHS[lang][mo - 1], y=y)
    title_html = esc(title)
    if highlight:
        if highlight not in title:
            raise PublishError(f"--highlight {highlight!r} does not occur in the title.")
        title_html = esc(title).replace(esc(highlight),
                                        f"<em>{esc(highlight)}</em>", 1)
    description = strip_tags(teaser(subtitle, body, 155))
    published_line = (f"{cfg['published']} {date_label}" if lang != "tr"
                      else f"{date_label} {cfg['published']}")

    page = PAGE.format(
        lang=lang, locale=cfg["locale"], site=SITE,
        title_plain=esc(title), title_html=title_html,
        subtitle_html=f'\n            <p class="article-subtitle">{esc(subtitle)}</p>' if subtitle else "",
        description=esc(description).replace('"', "&quot;"),
        tag_html=f'\n              <span class="article-tag">{esc(tag)}</span>' if tag else "",
        iso_date=date, date_label=date_label, author=esc(author_display),
        author_type="Organization" if author_is_org else "Person",
        lang_label=cfg["label"], cover=cover_rel, dims=dims,
        alt=esc(alt or title).replace('"', "&quot;"),
        caption_html=f'\n              <figcaption>{esc(caption)}</figcaption>' if caption else "",
        body=body, by=cfg["by"], published_line=published_line, back=cfg["back"],
        dir_attr=' dir="rtl"' if cfg["rtl"] else "",
    )

    # ---- fidelity gate ----------------------------------------------------
    a, b, diffs = check_fidelity(md_text, page)
    if diffs:
        word_diffs = [(tag, a[i1:i2], b[j1:j2]) for tag, i1, i2, j1, j2 in diffs]
        raise PublishError(
            "The generated page does not match the manuscript word for word.",
            diffs=word_diffs)
    info(f"Fidelity check: {len(a)} words, identical to the manuscript. ✓")

    card = CARD.format(
        slug=post_slug, lang=lang, cover=cover_rel, dims=dims,
        alt=esc(alt or title).replace('"', "&quot;"),
        lang_label=cfg["label"], iso_date=date, date_label=date_label,
        author=esc(author_display), title_plain=esc(title),
        excerpt=esc(teaser(subtitle, body)), read_more=cfg["read_more"],
    )

    files = [
        os.path.relpath(page_path, ROOT),
        os.path.relpath(os.path.join(IMG_DIR, f"{post_slug}-cover{ext}"), ROOT),
        os.path.relpath(INDEX, ROOT),
        os.path.relpath(os.path.join(MANUSCRIPTS_DIR, post_slug + ".md"), ROOT),
        os.path.relpath(POSTS_JSON, ROOT),
    ]
    if author_new:
        files.append(os.path.relpath(AUTHORS, ROOT))
    if old_cover_path:
        files.append(os.path.relpath(old_cover_path, ROOT))

    # ---- author page --------------------------------------------------------
    # Originals and translations both get a card; translations are marked with
    # an extra "Übersetzung" badge so the list stays readable.
    author_page_rel = None
    apath = author_page_path(author_id) if author_id else None
    if apath and os.path.exists(apath):
        author_page_rel = os.path.relpath(apath, ROOT)
        files.append(author_page_rel)

    chip_added = False
    if write:
        # ---- write ----------------------------------------------------------
        with open(page_path, "w", encoding="utf-8") as fh:
            fh.write(page)
        if image_path is not None:
            cover_dest = os.path.join(IMG_DIR, f"{post_slug}-cover{ext}")
            # image_path can legitimately be the repo's own cover file
            # (e.g. an edit-mode publish that inherits the untouched cover)
            # — copying a file onto itself raises shutil.SameFileError, so
            # skip the copy in that case instead of crashing mid-write.
            if not (os.path.exists(cover_dest) and os.path.samefile(image_path, cover_dest)):
                shutil.copyfile(image_path, cover_dest)
        if old_cover_path:
            os.remove(old_cover_path)

        index_html = open(INDEX, encoding="utf-8").read()
        index_html, chip_added = add_chip(index_html, lang)
        index_html = replace_card(index_html, card, post_slug) if update else add_card(index_html, card)
        with open(INDEX, "w", encoding="utf-8") as fh:
            fh.write(index_html)

        os.makedirs(MANUSCRIPTS_DIR, exist_ok=True)
        with open(os.path.join(MANUSCRIPTS_DIR, post_slug + ".md"), "w",
                  encoding="utf-8") as fh:
            fh.write(md_text)
        posts_registry = load_posts()
        posts_registry["posts"][post_slug] = {
            "title": title, "lang": lang, "date": date,
            "author": author_canonical or author_display,
            "tag": tag, "highlight": highlight, "alt": alt, "caption": caption,
            "original_slug": original_slug, "locked": False,
        }
        save_posts(posts_registry)

        if author_new:
            with open(AUTHORS, "w", encoding="utf-8") as fh:
                json.dump(registry, fh, ensure_ascii=False, indent=2)
                fh.write("\n")

        if author_page_rel:
            acard = AUTHOR_CARD.format(
                slug=post_slug, lang=lang, cover=cover_rel, dims=dims,
                alt=esc(alt or title).replace('"', "&quot;"),
                lang_label=cfg["label"],
                translation_badge=TRANSLATION_BADGE if original_slug else "",
                iso_date=date, date_label=date_label, title_plain=esc(title),
                excerpt=esc(teaser(subtitle, body)), read_more=cfg["read_more"],
            )
            page_html_author = open(apath, encoding="utf-8").read()
            with open(apath, "w", encoding="utf-8") as fh:
                fh.write(upsert_author_card(page_html_author, acard, post_slug,
                                            original_slug))

    return {
        "slug": post_slug, "title": title, "subtitle": subtitle,
        "author": author_display, "author_canonical": author_canonical,
        "author_score": score, "author_new": author_new,
        "page_html": page, "card_html": card,
        "cover_rel": cover_rel, "files": files,
        "chip_added": chip_added, "author_page": author_page_rel,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--md", required=True, help="manuscript (.md)")
    ap.add_argument("--image", required=False, help="cover image (jpg/png)")
    ap.add_argument("--lang", required=True, choices=sorted(LANGS), help="language of the manuscript")
    ap.add_argument("--date", required=True, help="publication date, YYYY-MM-DD")
    ap.add_argument("--author", help="author name; default: byline found in the manuscript")
    ap.add_argument("--slug", help="URL slug; default: derived from the title")
    ap.add_argument("--tag", help="small label above the headline (e.g. Medienpreis)")
    ap.add_argument("--highlight", help="phrase in the title to mark with the accent colour")
    ap.add_argument("--alt", help="alt text for the cover image; default: the title")
    ap.add_argument("--caption", help="caption under the cover image")
    ap.add_argument("--subtitle-from", default="auto", choices=["auto", "italic", "heading", "none"])
    ap.add_argument("--new-author", action="store_true",
                    help="register the author as a new person instead of matching an existing one")
    ap.add_argument("--update", action="store_true",
                    help="edit an already-published post in place instead of creating a new one")
    ap.add_argument("--dry-run", action="store_true", help="report only, write nothing")
    args = ap.parse_args()

    if not args.image and not args.update:
        die("--image is required unless --update is given.")

    for p in (args.md, args.image):
        if p and not os.path.exists(p):
            die(f"File not found: {p}")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.date):
        die("--date must look like 2026-07-20.")

    raw_md = open(args.md, encoding="utf-8").read()

    try:
        r = build_post(raw_md, args.image, args.lang, args.date,
                       author=args.author, slug=args.slug, tag=args.tag,
                       highlight=args.highlight, alt=args.alt, caption=args.caption,
                       subtitle_from=args.subtitle_from, new_author=args.new_author,
                       write=not args.dry_run, update=args.update)
    except PublishError as e:
        if e.diffs:
            print("\n✗ The generated page does not match the manuscript word for word:")
            for tag, a_w, b_w in e.diffs[:20]:
                print(f"    [{tag}] md={' '.join(a_w)!r} page={' '.join(b_w)!r}")
            die("Nothing was written. Fix the converter or the manuscript and retry.")
        die(str(e))

    ext = os.path.splitext(r["cover_rel"])[1].lower() or ".jpg"

    if args.dry_run:
        print(f"\n[dry run] would write {os.path.join(POSTS_DIR, r['slug'] + '.html')}")
        if args.image:
            print(f"[dry run] would copy  {args.image} → {IMG_DIR}/{r['slug']}-cover{ext}")
        print(f"[dry run] would add a {LANGS[args.lang]['label']} card to aktuelles/index.html")
        return

    print(f"\n✓ Published /aktuelles/{r['slug']}")
    info(f"page   aktuelles/{r['slug']}.html")
    info(f"cover  assets/blog/{r['slug']}-cover{ext}")
    info("card   added to aktuelles/index.html" +
        (f" (+ {LANGS[args.lang]['label']} filter chip)" if r["chip_added"] else ""))
    print(f"\nPreview:  python3 dev-server.py  →  http://localhost:8000/aktuelles/{r['slug']}\n")


if __name__ == "__main__":
    main()
