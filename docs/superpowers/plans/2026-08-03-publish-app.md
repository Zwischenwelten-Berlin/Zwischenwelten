# Publish App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A local browser app (`python3 scripts/publish_app.py`) where an editor drops a manuscript (`.md`/`.docx`/`.doc`) + cover image, reviews pre-filled metadata, previews the exact rendered page, and publishes to GitHub Pages in one click.

**Architecture:** Stdlib `http.server` app that imports the existing `scripts/publish_post.py` pipeline (refactored from CLI-only into a callable library) so GUI and CLI share one rendering path. Word conversion via `mammoth` (docx→HTML) plus a small stdlib HTML→markdown converter. Publish = write files + `git add/commit/push` via subprocess.

**Tech Stack:** Python 3.13 stdlib (http.server, html.parser, subprocess, base64, tempfile) + `mammoth` (only third-party dep, lazily imported) + vanilla HTML/JS/CSS single page.

**Spec:** `docs/superpowers/specs/2026-08-03-publish-app-design.md`

## Global Constraints

- Python 3.13 — the `cgi` module is REMOVED; file uploads are sent as base64 inside JSON, never multipart.
- Only third-party runtime dep: `mammoth`. Imported lazily — the app must start and handle `.md` without it.
- The manuscript's wording is untouchable; the fidelity gate in `publish_post.py` must run before any write and must never be weakened.
- `publish_post.py` CLI behavior and flags must not change (the `/publish` skill depends on them).
- Server binds `127.0.0.1:8765` only; fail loudly if the port is occupied (same style as `dev-server.py`).
- Site languages: `de en tr ru uk ar ku fa`.
- Commit message prefixes follow repo style: `tooling:` for this feature's commits.
- Tests: pytest under `scripts/tests/`, run as `python3 -m pytest scripts/tests/ -v` (install with `pip3 install pytest` if missing).

## File Structure

| File | Responsibility |
|---|---|
| `scripts/publish_post.py` (modify) | Existing pipeline; `main()` body extracted into `build_post(...)` + `PublishError`. CLI unchanged. |
| `scripts/manuscript_import.py` (create) | Pure conversion: `html_to_md`, `detect_lang`, `load_manuscript` (md/docx/doc dispatch, mammoth, textutil). |
| `scripts/publish_app.py` (create) | HTTP server, JSON API (`/api/convert`, `/api/preview`, `/api/publish`, `/api/retry-push`), preview serving, git operations. |
| `scripts/publish_app.html` (create) | Single-page UI: drop → form → preview → publish result. |
| `scripts/requirements.txt` (create) | `mammoth` (runtime), `pytest` (dev). |
| `scripts/tests/test_manuscript_import.py` (create) | Tests for `html_to_md` + `detect_lang`. |
| `scripts/tests/test_build_post.py` (create) | Tests for the `build_post` refactor. |

---

### Task 1: Refactor `publish_post.py` into a library (`build_post`)

**Files:**
- Modify: `scripts/publish_post.py`
- Test: `scripts/tests/test_build_post.py`, `scripts/tests/__init__.py` (empty)

**Interfaces:**
- Consumes: nothing new.
- Produces (used by Tasks 3–4):
  - `class PublishError(Exception)` with attribute `diffs: list` (word-diff tuples `(tag, a_words, b_words)`, empty unless the fidelity gate failed).
  - `build_post(md_text, image_path, lang, date, author=None, slug=None, tag=None, highlight=None, alt=None, caption=None, subtitle_from="auto", new_author=False, write=False) -> dict` — raises `PublishError` on any failure; returns:
    ```python
    {
      "slug": str, "title": str, "subtitle": str,
      "author": str,               # display name for this lang
      "author_canonical": str|None,# matched registry entry, None if new
      "author_score": float,
      "author_new": bool,
      "page_html": str, "card_html": str,
      "cover_rel": str,            # e.g. "/assets/blog/<slug>-cover.jpg"
      "files": [str],              # repo-relative paths written (write=True) or that would be written
    }
    ```
  - `parse_md(text, lang, subtitle_mode="auto")` — now takes **text**, not a path; raises `PublishError` when there is no `# Title`.
  - Unchanged public helpers reused later: `LANGS`, `find_author_in_md`, `load_authors`, `match_author`, `slugify`, `ROOT`.

**Behavioral notes for the refactor:**
- Every `die(...)` inside pipeline logic becomes `raise PublishError(...)`; the CLI `main()` wraps the call in `try/except PublishError` and `sys.exit`s with the same message format (`\n✗ {msg}\n`).
- `check_fidelity` takes `(md_text, page_html)` (text, not path).
- Fidelity failure raises `PublishError("The generated page does not match the manuscript word for word.", diffs=[(tag, a_words, b_words), ...])` — before anything is written.
- Duplicate slug (`aktuelles/<slug>.html` exists) raises `PublishError` only when `write=True` (preview of an existing slug is allowed; the app warns separately).
- Author resolution stays identical: registry match ≥ 0.85 wins; no match without `new_author=True` raises; `new_author=True` appends to the registry (registry file written only when `write=True`).
- `write=True` performs exactly what `main()` does today: write page, copy cover, update `aktuelles/index.html` (chip + card), write `authors.json` if `new_author`. Collect all touched paths into `files`.
- `main()` reads the md file, calls `build_post(...)`, and reproduces today's console output, including the `--dry-run` `[dry run] would write ...` lines (driven by the returned `files` list).

- [ ] **Step 1: Capture pre-refactor CLI output as the equivalence baseline**

```bash
mkdir -p scripts/tests
S=/private/tmp/claude-501/-Users-alperozturk-Desktop-Zwischenwelten-Website/2a073424-c75d-44fc-b470-4b49c3eaf302/scratchpad
mkdir -p "$S"
cat > "$S/sample.md" <<'EOF'
# Ein Test

*Der Untertitel*

Author: Süleyman Bağ

Erster Absatz mit **wichtig** und einem "Zitat".

## Zwischentitel

- eins
- zwei

> Ein schönes Zitat.
EOF
python3 - <<'EOF'
import base64
png = base64.b64decode(b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGBgAAAABQABh6FO1AAAAABJRU5ErkJggg==")
open("/private/tmp/claude-501/-Users-alperozturk-Desktop-Zwischenwelten-Website/2a073424-c75d-44fc-b470-4b49c3eaf302/scratchpad/cover.png","wb").write(png)
EOF
python3 scripts/publish_post.py --md "$S/sample.md" --image "$S/cover.png" \
  --lang de --date 2026-08-03 --dry-run | tee "$S/baseline.txt"
```

Expected: dry-run report (author match, title, fidelity ✓, `[dry run] would write ...`).

- [ ] **Step 2: Write the failing tests**

`scripts/tests/__init__.py`: empty file.

```python
# scripts/tests/test_build_post.py
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python3 -m pytest scripts/tests/test_build_post.py -v`
Expected: FAIL / ERROR with `AttributeError: module 'publish_post' has no attribute 'build_post'`.

- [ ] **Step 4: Refactor `publish_post.py`**

Mechanical moves, no logic changes:

1. Add near `die()`:

```python
class PublishError(Exception):
    """Raised by build_post instead of exiting; .diffs carries fidelity diffs."""
    def __init__(self, message, diffs=None):
        super().__init__(message)
        self.diffs = diffs or []
```

2. `parse_md(path, ...)` → `parse_md(text, lang, subtitle_mode="auto")`: drop the `open(...)` line, keep the rest; its `die(...)` becomes `raise PublishError(...)`.
3. `check_fidelity(md_path, page_html)` → `check_fidelity(md_text, page_html)`: drop the `open`.
4. Move the body of `main()` between "---- author ----" and the final prints into `build_post(...)` with the signature above. Inside it:
   - `args.X` → the corresponding parameter.
   - `die(...)` → `raise PublishError(...)`.
   - The fidelity block raises `PublishError(..., diffs=diffs)` instead of printing.
   - The duplicate-slug check moves after slug computation and only applies `if write`.
   - The dry-run branch disappears; instead compute `files` (repo-relative) and perform the writes only `if write`.
   - Return the result dict specified in **Interfaces**.
5. New `main()` keeps all argparse setup and file-existence/date-format checks, reads the md file, then:

```python
    try:
        r = build_post(raw_md, args.image, args.lang, args.date,
                       author=args.author, slug=args.slug, tag=args.tag,
                       highlight=args.highlight, alt=args.alt, caption=args.caption,
                       subtitle_from=args.subtitle_from, new_author=args.new_author,
                       write=not args.dry_run)
    except PublishError as e:
        if e.diffs:
            print("\n✗ The generated page does not match the manuscript word for word:")
            for tag, a_w, b_w in e.diffs[:20]:
                print(f"    [{tag}] md={' '.join(a_w)!r} page={' '.join(b_w)!r}")
            die("Nothing was written. Fix the converter or the manuscript and retry.")
        die(str(e))
    if args.dry_run:
        ext = os.path.splitext(args.image)[1].lower() or ".jpg"
        print(f"\n[dry run] would write {os.path.join(POSTS_DIR, r['slug'] + '.html')}")
        print(f"[dry run] would copy  {args.image} → {IMG_DIR}/{r['slug']}-cover{ext}")
        print(f"[dry run] would add a {LANGS[args.lang]['label']} card to aktuelles/index.html")
        return
    print(f"\n✓ Published /aktuelles/{r['slug']}")
    ...  # keep today's success output verbatim
```

(`check_fidelity`'s diff opcodes must be converted to `(tag, a[i1:i2], b[j1:j2])` word lists when raising, so the CLI print above matches today's output.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest scripts/tests/test_build_post.py -v`
Expected: 4 passed.

- [ ] **Step 6: Verify CLI equivalence against the baseline**

```bash
S=/private/tmp/claude-501/-Users-alperozturk-Desktop-Zwischenwelten-Website/2a073424-c75d-44fc-b470-4b49c3eaf302/scratchpad
python3 scripts/publish_post.py --md "$S/sample.md" --image "$S/cover.png" \
  --lang de --date 2026-08-03 --dry-run | diff "$S/baseline.txt" -
git status --porcelain   # must show only the new test files, no repo content touched
```

Expected: `diff` prints nothing; git status clean apart from `scripts/tests/`.

- [ ] **Step 7: Commit**

```bash
git add scripts/publish_post.py scripts/tests/__init__.py scripts/tests/test_build_post.py
git commit -m "tooling: extract build_post() library from publish_post CLI"
```

---

### Task 2: `manuscript_import.py` — Word→markdown + language detection

**Files:**
- Create: `scripts/manuscript_import.py`, `scripts/requirements.txt`
- Test: `scripts/tests/test_manuscript_import.py`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces (used by Task 3):
  - `class ManuscriptError(Exception)` — human-readable message, safe to show in the UI.
  - `html_to_md(html: str) -> tuple[str, list[str]]` — `(markdown, warnings)`.
  - `detect_lang(text: str) -> str` — one of `de en tr ru uk ar ku fa`; defaults to `"de"` when unsure.
  - `load_manuscript(filename: str, data: bytes) -> tuple[str, list[str]]` — dispatches `.md`/`.docx`/`.doc`; raises `ManuscriptError` (unsupported type, empty document, mammoth missing, textutil failure).

- [ ] **Step 1: Write the failing tests**

```python
# scripts/tests/test_manuscript_import.py
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from manuscript_import import html_to_md, detect_lang


# ---- html_to_md ---------------------------------------------------------

def test_headings():
    md, _ = html_to_md("<h1>Titel</h1><h2>Sub</h2><h3>Tief</h3><h4>Tiefer</h4>")
    assert md == "# Titel\n\n## Sub\n\n### Tief\n\n### Tiefer"

def test_second_h1_demoted():
    md, _ = html_to_md("<h1>Titel</h1><p>x</p><h1>Noch eins</h1>")
    assert md == "# Titel\n\nx\n\n## Noch eins"

def test_paragraph_emphasis():
    md, _ = html_to_md("<p>Ein <strong>fettes</strong> und <em>kursives</em> Wort.</p>")
    assert md == "Ein **fettes** und *kursives* Wort."

def test_unordered_list():
    md, _ = html_to_md("<ul><li>eins</li><li>zwei <strong>fett</strong></li></ul>")
    assert md == "- eins\n- zwei **fett**"

def test_ordered_list_degrades_to_bullets():
    md, _ = html_to_md("<ol><li>erstens</li><li>zweitens</li></ol>")
    assert md == "- erstens\n- zweitens"

def test_blockquote_with_paragraphs():
    md, _ = html_to_md("<blockquote><p>Weise Worte.</p><p>Noch mehr.</p></blockquote>")
    assert md == "> Weise Worte.\n> Noch mehr."

def test_blockquote_bare_text():
    md, _ = html_to_md("<blockquote>Weise Worte.</blockquote>")
    assert md == "> Weise Worte."

def test_link():
    md, _ = html_to_md('<p>Siehe <a href="https://x.de">hier</a>.</p>')
    assert md == "Siehe [hier](https://x.de)."

def test_table():
    md, _ = html_to_md(
        "<table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>")
    assert md == "| A | B |\n| --- | --- |\n| 1 | 2 |"

def test_image_dropped_with_warning():
    md, warnings = html_to_md('<p>Davor</p><img src="data:image/png;base64,xx"><p>Danach</p>')
    assert md == "Davor\n\nDanach"
    assert any("Bild" in w or "image" in w.lower() for w in warnings)

def test_whitespace_collapsed():
    md, _ = html_to_md("<p>Ein\n   Wort\n mehr</p>")
    assert md == "Ein Wort mehr"

def test_empty_input():
    md, _ = html_to_md("  <p>  </p> ")
    assert md == ""

def test_unknown_tags_keep_text():
    md, _ = html_to_md("<p><span>Text in</span> <sup>Spans</sup></p>")
    assert md == "Text in Spans"


# ---- detect_lang --------------------------------------------------------

def test_detect_de():
    assert detect_lang("Das ist ein Text über die Stadt und das Leben der Menschen.") == "de"

def test_detect_en():
    assert detect_lang("This is a text about the city and the people who live in it.") == "en"

def test_detect_tr():
    assert detect_lang("Bu, şehir ve içinde yaşayan insanlar hakkında bir yazı.") == "tr"

def test_detect_ku():
    assert detect_lang("Ev nivîsek e li ser bajar û mirovên ku lê dijîn.") == "ku"

def test_detect_ru():
    assert detect_lang("Это текст о городе и людях, которые в нём живут.") == "ru"

def test_detect_uk():
    assert detect_lang("Це текст про місто і людей, які в ньому живуть.") == "uk"

def test_detect_ar():
    assert detect_lang("هذا نص عن المدينة والناس الذين يعيشون فيها.") == "ar"

def test_detect_fa():
    assert detect_lang("این متنی درباره شهر و مردمی است که در آن زندگی می‌کنند.") == "fa"

def test_detect_default_de():
    assert detect_lang("xyzzy 123") == "de"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest scripts/tests/test_manuscript_import.py -v`
Expected: collection ERROR — `ModuleNotFoundError: No module named 'manuscript_import'`.

- [ ] **Step 3: Implement `scripts/manuscript_import.py`**

```python
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
```

`scripts/requirements.txt`:

```
# publish app: Word (.docx) import
mammoth
# dev only: tests
pytest
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest scripts/tests/test_manuscript_import.py -v`
Expected: all pass. Fix converter edge cases until green — never loosen a test that guards wording preservation.

- [ ] **Step 5: Install mammoth and smoke-test a real docx round-trip**

```bash
pip3 install mammoth
S=/private/tmp/claude-501/-Users-alperozturk-Desktop-Zwischenwelten-Website/2a073424-c75d-44fc-b470-4b49c3eaf302/scratchpad
printf 'Ein Test\n\nErster Absatz mit Text.\n' > "$S/sample.txt"
textutil -convert docx "$S/sample.txt" -output "$S/sample.docx"
python3 - <<'EOF'
import sys
sys.path.insert(0, "scripts")
from manuscript_import import load_manuscript
S = "/private/tmp/claude-501/-Users-alperozturk-Desktop-Zwischenwelten-Website/2a073424-c75d-44fc-b470-4b49c3eaf302/scratchpad"
md, warnings = load_manuscript("sample.docx", open(S + "/sample.docx", "rb").read())
print(repr(md)); print(warnings)
EOF
```

Expected: markdown containing both sentences, no exception.

- [ ] **Step 6: Run the full test suite**

Run: `python3 -m pytest scripts/tests/ -v`
Expected: all pass (Task 1 tests still green).

- [ ] **Step 7: Commit**

```bash
git add scripts/manuscript_import.py scripts/requirements.txt scripts/tests/test_manuscript_import.py
git commit -m "tooling: add Word->markdown import and language detection"
```

---

### Task 3: `publish_app.py` — server, API, git publish

**Files:**
- Create: `scripts/publish_app.py`

**Interfaces:**
- Consumes: `publish_post.build_post/PublishError/parse_md/find_author_in_md/load_authors/match_author/slugify/LANGS/ROOT`; `manuscript_import.load_manuscript/detect_lang/ManuscriptError`.
- Produces (consumed by Task 4's JS):
  - `GET /` → `scripts/publish_app.html`
  - `GET /preview/page` → the in-memory rendered post (`text/html`, no-cache)
  - `GET <cover_rel>` (e.g. `/assets/blog/<slug>-cover.png`) → the uploaded temp cover, while previewing
  - `GET` anything else → static file from repo root (clean-URL fallback like `dev-server.py`)
  - `POST /api/convert` body `{"manuscript_name","manuscript_b64","cover_name","cover_b64"}` →
    `{"ok":true,"markdown","lang","title","subtitle","slug","author":{"name","canonical","score","known"},"warnings":[...],"langs":{...}}` or `{"ok":false,"error"}`
    (`title` is `null` + warning when the manuscript has no `# Title`; `author.name` is `null` when no byline; `langs` maps code→label for the dropdown)
  - `POST /api/preview` body `{"markdown","lang","date","author","slug","tag","highlight","alt","caption","new_author"}` →
    `{"ok":true,"fidelity_ok":true,"slug","title","card_html","slug_exists","branch"}` or
    `{"ok":true,"fidelity_ok":false,"diffs":[[tag,"md words","page words"],...]}` or `{"ok":false,"error"}`
  - `POST /api/publish` (uses the state stored by the last successful preview) →
    `{"ok":true,"url","commit","git_output"}` or `{"ok":false,"stage":"pull|write|commit|push","error","git_output"}`
  - `POST /api/retry-push` → same shape as publish (runs `git pull --rebase` + `git push origin HEAD` again)

- [ ] **Step 1: Implement the server**

```python
#!/usr/bin/env python3
"""Browser publishing app for the ZWISCHENWELTEN blog.

    python3 scripts/publish_app.py

Opens http://localhost:8765 — drop a manuscript (.md/.docx/.doc) and a cover
image, review the pre-filled metadata, preview the exact page, publish to
GitHub Pages. All rendering goes through publish_post.build_post, so the app
can never produce different HTML than the CLI, and the fidelity gate always
runs before anything is written.
"""

import base64
import http.server
import json
import os
import subprocess
import sys
import tempfile
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import publish_post
from publish_post import LANGS, PublishError, ROOT, build_post
from manuscript_import import ManuscriptError, detect_lang, load_manuscript

PORT = 8765
APP_HTML = os.path.join(os.path.dirname(os.path.abspath(__file__)), "publish_app.html")

# Single-editor session state: uploaded cover, last preview, last publish args.
SESSION = {"cover_path": None, "cover_rel": None, "preview": None, "publish_args": None}


def run_git(*args):
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip()


def current_branch():
    _, out = run_git("rev-parse", "--abbrev-ref", "HEAD")
    return out


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    # ---- helpers ----------------------------------------------------------
    def send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, text):
        body = text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def translate_path(self, path):
        resolved = super().translate_path(path)
        if not os.path.exists(resolved) and os.path.exists(resolved + ".html"):
            return resolved + ".html"
        return resolved

    # ---- GET --------------------------------------------------------------
    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/":
            self.send_html(open(APP_HTML, encoding="utf-8").read())
        elif path == "/preview/page":
            if not SESSION["preview"]:
                self.send_error(404, "No preview yet")
            else:
                self.send_html(SESSION["preview"]["page_html"])
        elif SESSION["cover_rel"] and path == SESSION["cover_rel"] and SESSION["cover_path"]:
            with open(SESSION["cover_path"], "rb") as fh:
                data = fh.read()
            self.send_response(200)
            self.send_header("Content-Type", "image/png" if path.endswith(".png") else "image/jpeg")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            super().do_GET()

    # ---- POST -------------------------------------------------------------
    def do_POST(self):
        try:
            body = self.read_body()
            if self.path == "/api/convert":
                self.api_convert(body)
            elif self.path == "/api/preview":
                self.api_preview(body)
            elif self.path == "/api/publish":
                self.api_publish()
            elif self.path == "/api/retry-push":
                self.api_retry_push()
            else:
                self.send_error(404)
        except (ManuscriptError, PublishError) as e:
            self.send_json({"ok": False, "error": str(e)})
        except Exception as e:                     # noqa: BLE001 — show, don't crash
            self.send_json({"ok": False, "error": f"{type(e).__name__}: {e}"}, status=500)

    def api_convert(self, body):
        md, warnings = load_manuscript(body["manuscript_name"],
                                       base64.b64decode(body["manuscript_b64"]))
        # cover -> temp file, remember the future URL for the preview
        cover_ext = os.path.splitext(body["cover_name"])[1].lower() or ".jpg"
        if cover_ext not in (".jpg", ".jpeg", ".png"):
            raise ManuscriptError(f"Cover muss .jpg oder .png sein, nicht {cover_ext}.")
        fd, SESSION["cover_path"] = tempfile.mkstemp(suffix=cover_ext)
        with os.fdopen(fd, "wb") as fh:
            fh.write(base64.b64decode(body["cover_b64"]))

        lang = detect_lang(md)
        title = subtitle = None
        try:
            title, subtitle, _ = publish_post.parse_md(md, lang)
        except PublishError:
            warnings.append("Keine '# Titel'-Zeile gefunden — bitte im Markdown-Editor ergänzen.")
        byline = publish_post.find_author_in_md(md)
        author = {"name": byline, "canonical": None, "score": 0, "known": False}
        if byline:
            entry, score = publish_post.match_author(byline, publish_post.load_authors())
            author.update(score=round(score, 2), known=bool(entry),
                          canonical=entry["canonical"] if entry else None)
        self.send_json({
            "ok": True, "markdown": md, "lang": lang,
            "title": title, "subtitle": subtitle,
            "slug": publish_post.slugify(title) if title else "",
            "author": author, "warnings": warnings,
            "langs": {code: cfg["label"] for code, cfg in LANGS.items()},
        })

    def api_preview(self, body):
        kwargs = dict(
            md_text=body["markdown"], image_path=SESSION["cover_path"],
            lang=body["lang"], date=body["date"],
            author=body.get("author") or None, slug=body.get("slug") or None,
            tag=body.get("tag") or None, highlight=body.get("highlight") or None,
            alt=body.get("alt") or None, caption=body.get("caption") or None,
            new_author=bool(body.get("new_author")),
        )
        if not SESSION["cover_path"]:
            raise PublishError("Kein Cover hochgeladen — bitte von vorn beginnen.")
        try:
            r = build_post(**kwargs, write=False)
        except PublishError as e:
            if e.diffs:
                self.send_json({"ok": True, "fidelity_ok": False,
                                "diffs": [[t, " ".join(a), " ".join(b)] for t, a, b in e.diffs]})
                return
            raise
        SESSION["preview"] = r
        SESSION["cover_rel"] = r["cover_rel"]
        SESSION["publish_args"] = kwargs
        self.send_json({
            "ok": True, "fidelity_ok": True,
            "slug": r["slug"], "title": r["title"], "card_html": r["card_html"],
            "slug_exists": os.path.exists(
                os.path.join(ROOT, "aktuelles", r["slug"] + ".html")),
            "branch": current_branch(),
        })

    def api_publish(self):
        if not SESSION["publish_args"]:
            raise PublishError("Bitte zuerst die Vorschau erzeugen.")
        log = []

        code, out = run_git("pull", "--rebase")
        log.append(f"$ git pull --rebase\n{out}")
        if code != 0:
            run_git("rebase", "--abort")
            self.send_json({"ok": False, "stage": "pull", "error":
                            "git pull --rebase ist fehlgeschlagen — nichts wurde veröffentlicht.",
                            "git_output": "\n\n".join(log)})
            return

        try:
            r = build_post(**SESSION["publish_args"], write=True)
        except PublishError as e:
            self.send_json({"ok": False, "stage": "write", "error": str(e),
                            "git_output": "\n\n".join(log)})
            return

        code, out = run_git("add", "--", *r["files"])
        log.append(f"$ git add {' '.join(r['files'])}\n{out}")
        msg = f"content: add {r['title']}"
        code, out = run_git("commit", "-m", msg)
        log.append(f"$ git commit -m {msg!r}\n{out}")
        if code != 0:
            self.send_json({"ok": False, "stage": "commit", "error": "git commit ist fehlgeschlagen.",
                            "git_output": "\n\n".join(log)})
            return

        code, out = run_git("push", "origin", "HEAD")
        log.append(f"$ git push origin HEAD\n{out}")
        if code != 0:
            self.send_json({"ok": False, "stage": "push",
                            "error": "git push wurde abgelehnt. Lokal ist der Post committet — "
                                     "»Erneut versuchen« führt pull --rebase + push aus.",
                            "git_output": "\n\n".join(log)})
            return

        self.send_json({"ok": True,
                        "url": f"https://zwischenwelten-berlin.de/aktuelles/{r['slug']}",
                        "commit": msg, "git_output": "\n\n".join(log)})

    def api_retry_push(self):
        log = []
        code, out = run_git("pull", "--rebase")
        log.append(f"$ git pull --rebase\n{out}")
        if code != 0:
            run_git("rebase", "--abort")
            self.send_json({"ok": False, "stage": "pull", "error": "git pull --rebase ist fehlgeschlagen.",
                            "git_output": "\n\n".join(log)})
            return
        code, out = run_git("push", "origin", "HEAD")
        log.append(f"$ git push origin HEAD\n{out}")
        if code != 0:
            self.send_json({"ok": False, "stage": "push", "error": "git push wurde erneut abgelehnt.",
                            "git_output": "\n\n".join(log)})
            return
        slug = SESSION["preview"]["slug"] if SESSION["preview"] else ""
        self.send_json({"ok": True, "url": f"https://zwischenwelten-berlin.de/aktuelles/{slug}",
                        "commit": "", "git_output": "\n\n".join(log)})

    def log_message(self, fmt, *args):   # quieter console
        if "/api/" in (args[0] if args else ""):
            super().log_message(fmt, *args)


if __name__ == "__main__":
    try:
        server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError:
        raise SystemExit(
            f"Port {PORT} ist bereits belegt — läuft die Publish-App schon in einem "
            f"anderen Terminal? Dort stoppen (Ctrl+C) und erneut starten.")
    url = f"http://localhost:{PORT}"
    print(f"Publish-App läuft auf {url} (Ctrl+C zum Beenden)")
    webbrowser.open(url)
    server.serve_forever()
```

Note: publishing pushes the **current branch** (`git push origin HEAD`). The UI shows the branch name from `/api/preview` and warns when it is not `main` ("GitHub Pages veröffentlicht nur main") — this is what makes throwaway-branch testing possible.

- [ ] **Step 2: Verify the API with curl (no UI yet)**

`scripts/publish_app.html` does not exist yet — create a placeholder so `GET /` works:

```bash
echo '<p>UI kommt in Task 4</p>' > scripts/publish_app.html
python3 scripts/publish_app.py &   # runs in background; browser opens the placeholder
sleep 1
S=/private/tmp/claude-501/-Users-alperozturk-Desktop-Zwischenwelten-Website/2a073424-c75d-44fc-b470-4b49c3eaf302/scratchpad
python3 - <<'EOF'
import base64, json, urllib.request
S = "/private/tmp/claude-501/-Users-alperozturk-Desktop-Zwischenwelten-Website/2a073424-c75d-44fc-b470-4b49c3eaf302/scratchpad"

def post(path, payload):
    req = urllib.request.Request("http://localhost:8765" + path,
                                 json.dumps(payload).encode(), {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req))

md = open(S + "/sample.md", "rb").read()
png = open(S + "/cover.png", "rb").read()
r = post("/api/convert", {"manuscript_name": "sample.md", "manuscript_b64": base64.b64encode(md).decode(),
                          "cover_name": "cover.png", "cover_b64": base64.b64encode(png).decode()})
assert r["ok"] and r["lang"] == "de" and r["title"] == "Ein Test", r
assert r["author"]["known"] and r["author"]["canonical"] == "Süleyman Bağ", r

p = post("/api/preview", {"markdown": r["markdown"], "lang": "de", "date": "2026-08-03",
                          "slug": r["slug"], "author": "", "tag": "", "highlight": "",
                          "alt": "", "caption": "", "new_author": False})
assert p["ok"] and p["fidelity_ok"] and p["slug"] == "ein-test", p

page = urllib.request.urlopen("http://localhost:8765/preview/page").read().decode()
assert "<h2>Zwischentitel</h2>" in page
cover = urllib.request.urlopen("http://localhost:8765/assets/blog/ein-test-cover.png").read()
assert cover[:8] == b"\x89PNG\r\n\x1a\n"
css = urllib.request.urlopen("http://localhost:8765/assets/blog.css").read()
assert len(css) > 0
print("API OK")
EOF
kill %1
git status --porcelain   # nothing in the repo may have changed
```

Expected: `API OK`; git status shows only the placeholder + new files, no content changes. Do NOT call `/api/publish` here — that is Task 5, on a throwaway branch.

- [ ] **Step 3: Commit**

```bash
git add scripts/publish_app.py scripts/publish_app.html
git commit -m "tooling: add publish app server and JSON API"
```

---

### Task 4: `publish_app.html` — the UI

**Files:**
- Modify: `scripts/publish_app.html` (replace the placeholder)

**Interfaces:**
- Consumes: the exact API shapes from Task 3.
- Produces: the four-screen flow. No framework, no build step, no external requests (works offline).

**Screens & behavior (all in one file, `<script>` at the bottom):**

1. **Drop** — two labelled drop zones (manuscript: `.md .docx .doc`; cover: `.jpg .jpeg .png`), each also clickable (`<input type=file hidden>`). Zone shows the chosen filename. "Weiter" button enabled only when both files are set → `FileReader.readAsDataURL`, strip the `data:...;base64,` prefix, `POST /api/convert`. Errors from the API render in a red banner on this screen.
2. **Form** — pre-filled from the convert response: title (read-only display), language `<select>` (from `langs`), date (`<input type=date>`, default today), author (text input; underneath either "✓ erkannt als *canonical*" in green, or a yellow warning "Unbekannte Autor:in" + checkbox "Als neue Autor:in registrieren" which maps to `new_author`), slug, tag, highlight, alt (defaults to title), caption, plus `<details>` with a `<textarea>` holding the markdown (the manuscript of record — edits here are what gets published and fidelity-checked). Convert warnings shown as a yellow list. "Vorschau" → `POST /api/preview`.
3. **Preview** — full-width `<iframe src="/preview/page?ts=<Date.now()>">` (the ts param busts iframe caching), the overview card rendered from `card_html` inside a `posts-grid`-styled wrapper, and status lines: fidelity ✓/✗ (on ✗ show the `diffs` table and disable publish), warning when `slug_exists` ("Slug existiert bereits — Veröffentlichen wird fehlschlagen"), warning when `branch !== "main"` ("Achtung: Branch *X* — GitHub Pages veröffentlicht nur main"). Buttons: "Zurück" (to form) and "Veröffentlichen" → `POST /api/publish` (button disables + shows spinner while pending).
4. **Result** — success: big ✓, link to the live URL, note "GitHub Pages braucht 1–2 Minuten", collapsed `<details>` with `git_output`. Failure: red banner with `error`, the `git_output` in a `<pre>`, and — only when `stage === "push"` — a "Erneut versuchen (pull --rebase + push)" button → `POST /api/retry-push`.

**Design:** minimal and clean, site colors (accent `#123f7a`, background `#f5f7fa`), system font stack, max-width 720px card layout, drop zones with dashed borders that highlight on `dragover`. German UI copy throughout (the editors' language). No CSS framework.

- [ ] **Step 1: Implement the page**

Structure (the implementer writes the full file; every element ID referenced by the JS below must exist):

```html
<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Publish-App – ZWISCHENWELTEN</title>
  <style>/* minimal styles per the design notes above */</style>
</head>
<body>
  <main>
    <h1>Neuer Blogpost</h1>
    <ol id="steps"><!-- 1 Dateien · 2 Angaben · 3 Vorschau · 4 Fertig --></ol>
    <section id="screen-drop">…</section>
    <section id="screen-form" hidden>…</section>
    <section id="screen-preview" hidden>…</section>
    <section id="screen-result" hidden>…</section>
  </main>
  <script>
  const state = { manuscript: null, cover: null, convert: null, preview: null };

  async function api(path, payload) {
    const res = await fetch(path, { method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload || {}) });
    return res.json();
  }

  function fileToB64(file) {
    return new Promise((resolve, reject) => {
      const r = new FileReader();
      r.onload = () => resolve(r.result.split(",", 2)[1]);
      r.onerror = reject;
      r.readAsDataURL(file);
    });
  }

  function show(id) {
    for (const s of document.querySelectorAll("main > section")) s.hidden = true;
    document.getElementById(id).hidden = false;
  }

  // Drop zones: dragover/dragleave toggle a highlight class; drop/change store
  // the File in state and print its name. Both set -> enable #btn-continue.

  async function doConvert() {
    const r = await api("/api/convert", {
      manuscript_name: state.manuscript.name,
      manuscript_b64: await fileToB64(state.manuscript),
      cover_name: state.cover.name,
      cover_b64: await fileToB64(state.cover),
    });
    if (!r.ok) return showError("screen-drop", r.error);
    state.convert = r;
    fillForm(r);           // populate every form field + author status + warnings
    show("screen-form");
  }

  function formPayload() {
    return {
      markdown: document.getElementById("f-markdown").value,
      lang: document.getElementById("f-lang").value,
      date: document.getElementById("f-date").value,
      author: document.getElementById("f-author").value.trim(),
      slug: document.getElementById("f-slug").value.trim(),
      tag: document.getElementById("f-tag").value.trim(),
      highlight: document.getElementById("f-highlight").value.trim(),
      alt: document.getElementById("f-alt").value.trim(),
      caption: document.getElementById("f-caption").value.trim(),
      new_author: document.getElementById("f-new-author").checked,
    };
  }

  async function doPreview() {
    const r = await api("/api/preview", formPayload());
    if (!r.ok) return showError("screen-form", r.error);
    state.preview = r;
    renderPreview(r);      // iframe src, card_html, fidelity/slug/branch status
    show("screen-preview");
  }

  async function doPublish() {
    setPublishPending(true);
    const r = await api("/api/publish");
    renderResult(r);       // success or failure incl. retry button on stage==='push'
    show("screen-result");
  }
  </script>
</body>
</html>
```

Date field default: `document.getElementById("f-date").value = new Date().toISOString().slice(0, 10);` — pre-filled, editor confirms (per spec, the date is always visible on the form, never silently assumed).

- [ ] **Step 2: Verify in the browser (no publish)**

```bash
python3 scripts/publish_app.py
```

Walk the flow manually with `$S/sample.md` (or any Word file) + `$S/cover.png`:
- both drop zones accept drag & drop AND click-to-choose,
- form is pre-filled (language de, author recognized, slug `ein-test`, date today),
- preview iframe shows the post pixel-identical to the house style (cover, fonts, pull quote),
- the card preview renders,
- stop before "Veröffentlichen".

Then check the failure paths: drop a `.txt` (clear error), clear the markdown title in the editor and preview (error from parse), set author to nonsense (unknown-author warning + checkbox appears).

- [ ] **Step 3: Commit**

```bash
git add scripts/publish_app.html
git commit -m "tooling: publish app UI (drop, form, preview, publish screens)"
```

---

### Task 5: End-to-end verification on a throwaway branch

**Files:** none created — this is the manual gate before the feature is called done.

- [ ] **Step 1: Full E2E on a throwaway branch**

```bash
git checkout -b publish-app-e2e
git push -u origin publish-app-e2e
python3 scripts/publish_app.py
```

In the browser: create a real `.docx` (e.g. `textutil -convert docx` of a few
paragraphs with a Heading 1, a Quote-styled paragraph, a bullet list), drop it
with a real image, fill the form (author: an existing registry author), preview,
then **Veröffentlichen**.

Verify:
- UI showed the branch warning (branch ≠ main) but published anyway,
- `git log -1` shows `content: add <title>` touching only page/cover/index files,
- the pushed branch on GitHub contains the post,
- `python3 dev-server.py` → the post renders at `/aktuelles/<slug>` and the card appears on `/aktuelles/`.

- [ ] **Step 2: Test the push-rejected path**

```bash
git commit --allow-empty -m "e2e: simulate remote ahead" && git push
git reset --hard HEAD~1
```

Publish another post from the app → push is rejected? No — pull --rebase will
absorb it. Instead: on GitHub (or a second clone) push any commit to
`publish-app-e2e` that this clone does not have, then publish from the app and
confirm the pull --rebase step handles it and the publish succeeds. If setting
that up is impractical, at minimum verify the retry button appears by
temporarily renaming the remote: `git remote rename origin origin-x`, publish
(push fails, files stay committed, retry button shown), `git remote rename
origin-x origin`, click "Erneut versuchen" → success.

- [ ] **Step 3: Clean up the throwaway branch**

```bash
git checkout main
git branch -D publish-app-e2e
git push origin --delete publish-app-e2e
```

- [ ] **Step 4: Run the whole test suite one last time**

Run: `python3 -m pytest scripts/tests/ -v`
Expected: all pass.

- [ ] **Step 5: Document the app for editors**

Add a short section to `.claude/skills/publish/SKILL.md` under a new heading
"## Browser-App" (two sentences: `python3 scripts/publish_app.py` opens the
self-service GUI; it uses the same converter and fidelity gate as this skill).

```bash
git add .claude/skills/publish/SKILL.md
git commit -m "tooling: mention the publish app in the /publish skill"
```

- [ ] **Step 6: Push**

Ask the user before pushing `main` (repo rule: pushing is outward-facing).

```bash
git push origin main
```
