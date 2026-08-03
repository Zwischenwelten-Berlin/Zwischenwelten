#!/usr/bin/env python3
"""Import a manuscript for the publish app.

Turns .docx/.doc files into the small markdown dialect publish_post.py
understands, and guesses the manuscript's language. Wording is never
altered: unsupported elements degrade to their plain text.
"""

import html.parser
import io
import os
import re
import subprocess
import tempfile

SITE_LANGS = ["de", "en", "tr", "ru", "uk", "ar", "ku", "fa"]


class ManuscriptError(Exception):
    """Human-readable import failure, safe to show in the UI."""


# --------------------------------------------------------------------------
# HTML (from mammoth) -> markdown
# --------------------------------------------------------------------------
class _MDBuilder(html.parser.HTMLParser):
    """Maps mammoth's clean HTML onto publish_post.py's markdown subset.

    h1 -> '# ' (first only; later h1s demote to '## '), h2 -> '## ',
    h3..h6 -> '### ', p -> paragraph, strong/b -> **, em/i -> *,
    ul/ol/li -> '- ', blockquote -> '> ', a -> [text](href), table -> md
    table. Images are dropped with a warning; unknown tags keep their text.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks = []          # finished markdown blocks
        self.inline = []          # inline fragments of the current block
        self.warnings = []
        self.seen_h1 = False
        self.list_items = []      # collected '- ' items
        self.quote_paras = []     # collected '> ' paragraphs
        self.in_li = False
        self.in_quote = False
        self.heading = None       # '#'/'##'/'###' while inside h1..h6
        self.href = None
        self.link_text = []
        self.table = None         # list of rows while inside a table
        self.row = None
        self.cell = None

    # ---- inline text -----------------------------------------------------
    def _emit(self, s):
        if self.cell is not None:
            self.cell.append(s)
        elif self.href is not None:
            self.link_text.append(s)
        else:
            self.inline.append(s)

    def handle_data(self, data):
        self._emit(data)

    def _flush_inline(self):
        text = re.sub(r"\s+", " ", "".join(self.inline)).strip()
        self.inline = []
        return text

    def _close_block(self):
        text = self._flush_inline()
        if not text:
            return
        if self.heading:
            self.blocks.append(f"{self.heading} {text}")
        elif self.in_li:
            self.list_items.append(f"- {text}")
        elif self.in_quote:
            self.quote_paras.append(f"> {text}")
        else:
            self.blocks.append(text)

    # ---- tags -------------------------------------------------------------
    def handle_starttag(self, tag, attrs):
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._close_block()
            if tag == "h1":
                self.heading = "#" if not self.seen_h1 else "##"
                self.seen_h1 = True
            elif tag == "h2":
                self.heading = "##"
            else:
                self.heading = "###"
        elif tag == "p":
            self._close_block()
        elif tag in ("ul", "ol"):
            self._close_block()
        elif tag == "li":
            self._close_block()
            self.in_li = True
        elif tag == "blockquote":
            self._close_block()
            self.in_quote = True
        elif tag in ("strong", "b"):
            self._emit("**")
        elif tag in ("em", "i"):
            self._emit("*")
        elif tag == "a":
            self.href = dict(attrs).get("href", "")
            self.link_text = []
        elif tag == "br":
            self._emit(" ")
        elif tag == "img":
            self.warnings.append(
                "Ein eingebettetes Bild wurde ignoriert (nur das Cover wird veröffentlicht).")
        elif tag == "table":
            self._close_block()
            self.table = []
        elif tag == "tr":
            self.row = []
        elif tag in ("td", "th"):
            self.cell = []

    def handle_endtag(self, tag):
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._close_block()
            self.heading = None
        elif tag == "p":
            self._close_block()
        elif tag == "li":
            self._close_block()
            self.in_li = False
        elif tag in ("ul", "ol"):
            self._close_block()
            if self.list_items:
                self.blocks.append("\n".join(self.list_items))
                self.list_items = []
        elif tag == "blockquote":
            self._close_block()
            self.in_quote = False
            if self.quote_paras:
                self.blocks.append("\n".join(self.quote_paras))
                self.quote_paras = []
        elif tag in ("strong", "b"):
            self._emit("**")
        elif tag in ("em", "i"):
            self._emit("*")
        elif tag == "a":
            text = re.sub(r"\s+", " ", "".join(self.link_text)).strip()
            href, self.href = self.href, None
            if text and href:
                self.inline.append(f"[{text}]({href})")
            elif text:
                self.inline.append(text)
        elif tag in ("td", "th"):
            self.row.append(re.sub(r"\s+", " ", "".join(self.cell)).strip())
            self.cell = None
        elif tag == "tr":
            if self.row is not None and any(self.row):
                self.table.append(self.row)
            self.row = None
        elif tag == "table":
            if self.table:
                header, *rows = self.table
                lines = ["| " + " | ".join(header) + " |",
                         "| " + " | ".join(["---"] * len(header)) + " |"]
                lines += ["| " + " | ".join(r) + " |" for r in rows]
                self.blocks.append("\n".join(lines))
            self.table = None

    def result(self):
        self._close_block()
        return "\n\n".join(self.blocks), self.warnings


def html_to_md(html_text):
    """mammoth HTML -> (markdown, warnings). Wording is preserved verbatim."""
    b = _MDBuilder()
    b.feed(html_text)
    b.close()
    return b.result()


# --------------------------------------------------------------------------
# Language detection
# --------------------------------------------------------------------------
_STOPWORDS = {
    "de": {"der", "die", "das", "und", "ist", "ein", "eine", "nicht", "mit",
           "von", "für", "auf", "dem", "den", "über", "sich"},
    "en": {"the", "and", "is", "of", "to", "in", "that", "for", "with",
           "are", "who", "about", "it"},
    "tr": {"ve", "bir", "bu", "için", "ile", "olarak", "daha", "gibi",
           "hakkında", "yazı", "içinde"},
    "ku": {"û", "li", "ji", "bi", "ev", "ku", "ne", "ya", "yê", "di",
           "ser", "e"},
}


def detect_lang(text):
    """Guess the manuscript language. A convenience, never authoritative."""
    if re.search(r"[؀-ۿ]", text):
        return "fa" if re.search(r"[پچژگکی]", text) else "ar"
    if re.search(r"[Ѐ-ӿ]", text):
        return "uk" if re.search(r"[іїєґІЇЄҐ]", text) else "ru"
    words = re.findall(r"[\wûîêçşğıöüäß]+", text.lower(), re.UNICODE)
    scores = {lang: sum(1 for w in words if w in sw)
              for lang, sw in _STOPWORDS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "de"


# --------------------------------------------------------------------------
# File dispatch
# --------------------------------------------------------------------------
# Word built-in style names (English + German Word) -> semantic HTML.
_STYLE_MAP = """
p[style-name='Title'] => h1:fresh
p[style-name='Titel'] => h1:fresh
p[style-name='Subtitle'] => h2:fresh
p[style-name='Untertitel'] => h2:fresh
p[style-name='Quote'] => blockquote > p:fresh
p[style-name='Zitat'] => blockquote > p:fresh
p[style-name='Intense Quote'] => blockquote > p:fresh
p[style-name='Intensives Zitat'] => blockquote > p:fresh
"""


def _doc_to_docx(data):
    """Legacy binary .doc -> .docx bytes via macOS textutil."""
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "in.doc")
        dst = os.path.join(tmp, "out.docx")
        with open(src, "wb") as fh:
            fh.write(data)
        r = subprocess.run(["textutil", "-convert", "docx", src, "-output", dst],
                           capture_output=True, text=True)
        if r.returncode != 0 or not os.path.exists(dst):
            raise ManuscriptError(
                "Die .doc-Datei konnte nicht konvertiert werden (textutil). "
                "Bitte in Word als .docx speichern und erneut versuchen.")
        with open(dst, "rb") as fh:
            return fh.read()


def load_manuscript(filename, data):
    """(filename, bytes) -> (markdown, warnings). Raises ManuscriptError."""
    ext = os.path.splitext(filename)[1].lower()
    if ext == ".md":
        try:
            return data.decode("utf-8"), []
        except UnicodeDecodeError:
            raise ManuscriptError("Die .md-Datei ist nicht UTF-8-kodiert.")
    if ext not in (".doc", ".docx"):
        raise ManuscriptError(
            f"Nicht unterstütztes Format: {ext or 'ohne Endung'}. "
            f"Bitte .md, .docx oder .doc verwenden.")
    if ext == ".doc":
        data = _doc_to_docx(data)
    try:
        import mammoth
    except ImportError:
        raise ManuscriptError(
            "Für Word-Dateien fehlt das Paket 'mammoth'. "
            "Im Terminal ausführen:  pip3 install mammoth")
    result = mammoth.convert_to_html(io.BytesIO(data), style_map=_STYLE_MAP)
    md, warnings = html_to_md(result.value)
    warnings += [m.message for m in result.messages]
    if not md.strip():
        raise ManuscriptError("Das Dokument enthält keinen Text.")
    return md, warnings
