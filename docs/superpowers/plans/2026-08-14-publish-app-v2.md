# Publish-App v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the publish pipeline and browser app with author-page automation, a post list with editing, translation publishing, in-app author creation, and a rich-text editing mode — per `docs/superpowers/specs/2026-08-14-publish-app-v2-design.md`.

**Architecture:** All rendering stays inside `publish_post.build_post`; the app only orchestrates. A new reverse converter (page HTML → manuscript MD) built on `manuscript_import._MDBuilder` enables a manuscript store (`assets/blog/manuscripts/`) and post registry (`assets/blog/posts.json`), which power listing/editing. Rich text round-trips through server endpoints so the Python converter remains the single source of truth.

**Tech Stack:** Python 3 stdlib only (http.server, html.parser, difflib), vanilla JS/`contenteditable` in `publish_app.html`, pytest for tests.

## Global Constraints

- **Fidelity gate is sacred:** every publish path must go through `build_post`, whose word-for-word check must never be bypassed, weakened, or special-cased.
- **No new Python dependencies.** stdlib only (mammoth is already an optional import inside `manuscript_import`).
- **UI copy is German** (matches the existing app: „Beiträge verwalten", „Neuer Beitrag", error texts in German).
- **Language set is the 8 languages in `publish_post.LANGS`:** `ar de en fa ku ru tr uk`.
- **Translations never get a card on author pages** (only on `/aktuelles`). Originals do.
- **Slug and language are immutable in edit mode.**
- Run tests with `python3 -m pytest scripts/tests/ -v` from the repo root (`pip3` is a different interpreter on this machine — always use `python3`).
- Commit messages: `feat:`/`tooling:` for pipeline work, `content:` only for actual published content, per existing history.

---

### Task 1: Reverse converter — `scripts/html_to_md.py`

Convert a generated post page back into manuscript markdown + metadata. Only ever needs to handle markup `build_post` itself emits.

**Files:**
- Create: `scripts/html_to_md.py`
- Test: `scripts/tests/test_html_to_md.py`

**Interfaces:**
- Consumes: `manuscript_import._MDBuilder` (HTML→MD builder class), `publish_post.build_post` / `publish_post.check_fidelity` (in tests).
- Produces:
  - `page_to_md(page_html: str) -> dict` with keys `md, title, subtitle, lang, date, author, tag, highlight, alt, caption` (strings or `None`; `md` is the full manuscript incl. `# title`, `*subtitle*`, `Author:` byline).
  - `fragment_to_md(html: str) -> str` — body-level HTML fragment → markdown (used later by `/api/html-to-md`).

- [ ] **Step 1: Write the failing tests**

```python
# scripts/tests/test_html_to_md.py
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


def test_fragment_to_md_headings_and_bold():
    md = html_to_md.fragment_to_md(
        "<h1>Titel</h1><p><em>Unter</em></p><h2>Kapitel</h2>"
        "<p>Text mit <strong>fett</strong>.</p><ul><li>a</li></ul>")
    assert md.startswith("# Titel")
    assert "*Unter*" in md
    assert "## Kapitel" in md
    assert "**fett**" in md
    assert "- a" in md
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest scripts/tests/test_html_to_md.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'html_to_md'`

- [ ] **Step 3: Implement `scripts/html_to_md.py`**

```python
#!/usr/bin/env python3
"""Reverse converter: generated post page HTML -> manuscript markdown.

Only ever needs to understand markup that publish_post.build_post emits.
Used by the backfill CLI and the app's rich-text endpoints.
"""

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

    def handle_starttag(self, tag, attrs):
        if tag == "cite":
            self.cite = ([], [])
        elif self.cite is not None and tag in ("strong", "b"):
            self.cite_strong = True
        elif self.cite is None:
            super().handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
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
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s)).strip() if s else None


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
```

Note for the implementer: `alt` falls back to the title in `build_post` (`alt or title`), so an alt equal to the title means "none was given" — that is why `page_to_md` returns `None` in that case.

- [ ] **Step 4: Run tests until they pass**

Run: `python3 -m pytest scripts/tests/test_html_to_md.py -v`
Expected: PASS (5 tests). Iterate on `_PageMDBuilder` if the round-trip diff test fails — print `diffs` to see the differing words; typical culprits are the attribution line and the em-para subtitle (must round-trip as `*…*` so `parse_md` re-detects it).

- [ ] **Step 5: Run the whole suite, then commit**

Run: `python3 -m pytest scripts/tests/ -v` — all green.

```bash
git add scripts/html_to_md.py scripts/tests/test_html_to_md.py
git commit -m "feat: reverse converter page HTML -> manuscript markdown"
```

---

### Task 2: Manuscript store + post registry in `build_post`

**Files:**
- Modify: `scripts/publish_post.py` (constants near line 28; `build_post` signature line 633, write path lines 741–757, `files` list line 733, return dict line 759)
- Test: `scripts/tests/test_build_post.py`

**Interfaces:**
- Consumes: nothing new.
- Produces (later tasks rely on these exact names):
  - `publish_post.MANUSCRIPTS_DIR` = `<ROOT>/assets/blog/manuscripts`
  - `publish_post.POSTS_JSON` = `<ROOT>/assets/blog/posts.json`
  - `load_posts() -> dict` — `{"posts": {slug: entry}}`; missing file → `{"posts": {}}`
  - `save_posts(registry) -> None`
  - Registry entry shape (all keys always present):
    `{"title", "lang", "date", "author", "tag", "highlight", "alt", "caption", "original_slug", "locked"}` — `author` is the canonical name; optional fields are `None`; `locked` is bool.
  - `build_post(..., original_slug=None)` new keyword; on `write=True` it writes `assets/blog/manuscripts/<slug>.md` (the verbatim `md_text`) and the registry entry, and appends both paths to `files`.

- [ ] **Step 1: Write the failing test**

Add to `scripts/tests/test_build_post.py` (reuse the existing `cover` fixture and `MD` constant; add a `repo` fixture that redirects all write-path constants into a tmp tree — later tasks extend this same fixture):

```python
import json
import shutil


INDEX_MIN = """<html><body>
            <button type="button" class="lang-chip" data-lang="de" aria-pressed="false">Deutsch</button>
<div class="posts-grid" id="posts-grid">
</div>
<script>var langs = ['de'];</script>
</body></html>"""


@pytest.fixture
def repo(tmp_path, monkeypatch):
    (tmp_path / "aktuelles").mkdir()
    (tmp_path / "assets" / "blog").mkdir(parents=True)
    (tmp_path / "journalistennetzwerk").mkdir()
    (tmp_path / "aktuelles" / "index.html").write_text(INDEX_MIN, encoding="utf-8")
    shutil.copyfile(publish_post.AUTHORS, tmp_path / "assets" / "blog" / "authors.json")
    monkeypatch.setattr(publish_post, "ROOT", str(tmp_path))
    monkeypatch.setattr(publish_post, "POSTS_DIR", str(tmp_path / "aktuelles"))
    monkeypatch.setattr(publish_post, "INDEX", str(tmp_path / "aktuelles" / "index.html"))
    monkeypatch.setattr(publish_post, "IMG_DIR", str(tmp_path / "assets" / "blog"))
    monkeypatch.setattr(publish_post, "AUTHORS", str(tmp_path / "assets" / "blog" / "authors.json"))
    monkeypatch.setattr(publish_post, "MANUSCRIPTS_DIR", str(tmp_path / "assets" / "blog" / "manuscripts"))
    monkeypatch.setattr(publish_post, "POSTS_JSON", str(tmp_path / "assets" / "blog" / "posts.json"))
    return tmp_path


def test_write_stores_manuscript_and_registry(repo, cover):
    publish_post.build_post(MD, cover, lang="de", date="2026-08-03", write=True)
    ms = repo / "assets" / "blog" / "manuscripts" / "ein-test.md"
    assert ms.read_text(encoding="utf-8") == MD
    reg = json.loads((repo / "assets" / "blog" / "posts.json").read_text())
    entry = reg["posts"]["ein-test"]
    assert entry["title"] == "Ein Test"
    assert entry["lang"] == "de"
    assert entry["date"] == "2026-08-03"
    assert entry["author"] == "Süleyman Bağ"
    assert entry["original_slug"] is None
    assert entry["locked"] is False


def test_files_include_manuscript_and_registry(repo, cover):
    r = publish_post.build_post(MD, cover, lang="de", date="2026-08-03", write=True)
    assert "assets/blog/manuscripts/ein-test.md" in r["files"]
    assert "assets/blog/posts.json" in r["files"]


def test_original_slug_recorded(repo, cover):
    r = publish_post.build_post(MD, cover, lang="tr", date="2026-08-03",
                                slug="ein-test-tr", original_slug="ein-test", write=True)
    reg = json.loads((repo / "assets" / "blog" / "posts.json").read_text())
    assert reg["posts"]["ein-test-tr"]["original_slug"] == "ein-test"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest scripts/tests/test_build_post.py -v -k "manuscript or registry or original_slug"`
Expected: FAIL — `AttributeError: ... has no attribute 'MANUSCRIPTS_DIR'`

- [ ] **Step 3: Implement**

In `scripts/publish_post.py`, after the `AUTHORS` constant:

```python
MANUSCRIPTS_DIR = os.path.join(IMG_DIR, "manuscripts")
POSTS_JSON = os.path.join(IMG_DIR, "posts.json")


def load_posts():
    if not os.path.exists(POSTS_JSON):
        return {"posts": {}}
    with open(POSTS_JSON, encoding="utf-8") as fh:
        return json.load(fh)


def save_posts(registry):
    with open(POSTS_JSON, "w", encoding="utf-8") as fh:
        json.dump(registry, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
```

Add `original_slug=None` to the `build_post` signature. In the write block (after the index update, before the `author_new` write), add:

```python
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
```

Extend the `files` list (unconditionally, next to the existing entries):

```python
        os.path.relpath(os.path.join(MANUSCRIPTS_DIR, post_slug + ".md"), ROOT),
        os.path.relpath(POSTS_JSON, ROOT),
```

- [ ] **Step 4: Run the full suite**

Run: `python3 -m pytest scripts/tests/ -v`
Expected: PASS (existing write-path tests must still pass — if any old test writes without the `repo` fixture and now creates `manuscripts/` in the real repo, port it onto the fixture).

- [ ] **Step 5: Commit**

```bash
git add scripts/publish_post.py scripts/tests/test_build_post.py
git commit -m "feat: manuscript store + posts.json registry on publish"
```

---

### Task 3: Backfill CLI — recover the 9 existing posts

**Files:**
- Create: `scripts/backfill_manuscripts.py`
- Test: `scripts/tests/test_backfill.py`
- Creates (when run): `assets/blog/manuscripts/*.md`, `assets/blog/posts.json`

**Interfaces:**
- Consumes: `html_to_md.page_to_md`, `publish_post.check_fidelity`, `publish_post.load_posts/save_posts`, `publish_post.match_author`.
- Produces: `backfill(root=publish_post.ROOT, force=False) -> list[tuple[slug, status]]` where status is `"ok"`, `"locked"`, or `"skipped"` — plus the CLI entry point.

- [ ] **Step 1: Write the failing test**

```python
# scripts/tests/test_backfill.py
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import backfill_manuscripts
import publish_post

# Reuse the repo/cover fixtures and MD from test_build_post.
from test_build_post import repo, cover, MD, INDEX_MIN  # noqa: F401


def test_backfill_recovers_written_post(repo, cover):
    publish_post.build_post(MD, cover, lang="de", date="2026-08-03", write=True)
    # wipe store+registry, keep the page — the pre-v2 state
    os.remove(repo / "assets" / "blog" / "manuscripts" / "ein-test.md")
    os.remove(repo / "assets" / "blog" / "posts.json")

    results = backfill_manuscripts.backfill()
    assert ("ein-test", "ok") in results
    assert (repo / "assets" / "blog" / "manuscripts" / "ein-test.md").exists()
    reg = json.loads((repo / "assets" / "blog" / "posts.json").read_text())
    assert reg["posts"]["ein-test"]["author"] == "Süleyman Bağ"


def test_backfill_is_idempotent(repo, cover):
    publish_post.build_post(MD, cover, lang="de", date="2026-08-03", write=True)
    results = backfill_manuscripts.backfill()
    assert results == [("ein-test", "skipped")]


def test_unrecoverable_page_is_locked(repo, cover):
    publish_post.build_post(MD, cover, lang="de", date="2026-08-03", write=True)
    os.remove(repo / "assets" / "blog" / "posts.json")
    page = repo / "aktuelles" / "ein-test.html"
    # inject a hand-built element whose words a recovered manuscript cannot contain
    html = page.read_text(encoding="utf-8").replace(
        '<div class="article-back">',
        '<div class="podium">Handgebauter Sonderblock</div><div class="article-back">')
    page.write_text(html, encoding="utf-8")

    results = backfill_manuscripts.backfill()
    assert ("ein-test", "locked") in results
    reg = json.loads((repo / "assets" / "blog" / "posts.json").read_text())
    assert reg["posts"]["ein-test"]["locked"] is True
    assert not (repo / "assets" / "blog" / "manuscripts" / "ein-test.md").exists()


def test_translation_suffix_sets_original_slug(repo, cover):
    publish_post.build_post(MD, cover, lang="de", date="2026-08-03", write=True)
    publish_post.build_post(MD, cover, lang="tr", date="2026-08-03",
                            slug="ein-test-tr", write=True)
    os.remove(repo / "assets" / "blog" / "posts.json")
    backfill_manuscripts.backfill()
    reg = json.loads((repo / "assets" / "blog" / "posts.json").read_text())
    assert reg["posts"]["ein-test-tr"]["original_slug"] == "ein-test"
    assert reg["posts"]["ein-test"]["original_slug"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest scripts/tests/test_backfill.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backfill_manuscripts'`

- [ ] **Step 3: Implement `scripts/backfill_manuscripts.py`**

```python
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
```

- [ ] **Step 4: Run tests until they pass**

Run: `python3 -m pytest scripts/tests/ -v`
Expected: PASS. (`check_fidelity` compares the recovered manuscript against the *existing* page's title/subtitle/body words — exactly the verification the spec requires.)

- [ ] **Step 5: Run the backfill against the real repo and inspect**

```bash
python3 scripts/backfill_manuscripts.py
git status
git diff --stat
```

Expected: 9 statuses printed. Ideally 9× `ok`. Any `locked` post: open the page and the diff output (add a temporary print of `diffs` if needed) and decide — if the mismatch is a converter gap that is easy to close (e.g. an inline pattern), fix `html_to_md.py` with a new unit test and re-run with `--force`. Genuinely hand-built layouts stay locked. Read 2–3 recovered manuscripts fully (`assets/blog/manuscripts/*.md`) and compare against the live pages by eye.

- [ ] **Step 6: Commit the tool and the recovered content separately**

```bash
git add scripts/backfill_manuscripts.py scripts/tests/test_backfill.py
git commit -m "tooling: backfill CLI recovers manuscripts + registry from published pages"
git add assets/blog/manuscripts assets/blog/posts.json
git commit -m "content: backfill manuscripts and post registry for existing posts"
```

---

### Task 4: Author-page automation in `build_post`

**Files:**
- Modify: `scripts/publish_post.py` (new template + helpers near `CARD` line 559; write path)
- Modify: `.claude/skills/publish/SKILL.md` (Author pages section lines 59–69; langs list line 24)
- Test: `scripts/tests/test_build_post.py`

**Interfaces:**
- Consumes: registry entry `id` from `authors.json`, `LANGS`, `teaser`, existing card metadata.
- Produces:
  - `AUTHOR_PAGES_DIR` = `<ROOT>/journalistennetzwerk`
  - `author_page_path(author_id: str) -> str`
  - `upsert_author_card(page_html: str, card: str, slug: str) -> str` — replaces the existing `.post-card` for `slug` or inserts newest-first; raises `PublishError` if no `posts-grid` found. (Task 5 reuses this for updates; Task 9's generated pages must contain the same grid markup.)
  - `build_post` return dict gains `"author_page": relpath-or-None`.

- [ ] **Step 1: Write the failing tests**

Add to `scripts/tests/test_build_post.py`:

```python
AUTHOR_PAGE_MIN = """<html><body>
          <div class="posts-grid">

            <a class="post-card" href="/aktuelles/alter-beitrag">
              <div class="post-info"><h3 class="post-title">Alt</h3></div>
            </a>

          </div>
</body></html>"""


@pytest.fixture
def author_page(repo):
    p = repo / "journalistennetzwerk" / "suleyman-bag.html"
    p.write_text(AUTHOR_PAGE_MIN, encoding="utf-8")
    return p


def test_publish_adds_card_to_author_page(repo, cover, author_page):
    r = publish_post.build_post(MD, cover, lang="de", date="2026-08-03", write=True)
    html = author_page.read_text(encoding="utf-8")
    assert '/aktuelles/ein-test"' in html
    assert html.index("ein-test") < html.index("alter-beitrag")  # newest first
    assert '<h3 class="post-title">Ein Test</h3>' in html
    assert "journalistennetzwerk/suleyman-bag.html" in r["files"]
    assert r["author_page"] == "journalistennetzwerk/suleyman-bag.html"


def test_translation_skips_author_page(repo, cover, author_page):
    before = author_page.read_text(encoding="utf-8")
    r = publish_post.build_post(MD, cover, lang="tr", date="2026-08-03",
                                slug="ein-test-tr", original_slug="ein-test", write=True)
    assert author_page.read_text(encoding="utf-8") == before
    assert r["author_page"] is None


def test_no_author_page_is_fine(repo, cover):
    r = publish_post.build_post(MD, cover, lang="de", date="2026-08-03", write=True)
    assert r["author_page"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest scripts/tests/test_build_post.py -v -k author_page`
Expected: FAIL — `KeyError: 'author_page'` / missing card.

- [ ] **Step 3: Implement**

In `scripts/publish_post.py`, next to `CARD`:

```python
AUTHOR_PAGES_DIR = os.path.join(ROOT, "journalistennetzwerk")

AUTHOR_CARD = """            <a class="post-card" href="/aktuelles/{slug}">
              <div class="post-thumb">
                <img src="{cover}" alt="{alt}" loading="lazy"{dims}>
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


def author_page_path(author_id):
    return os.path.join(AUTHOR_PAGES_DIR, f"{author_id}.html")


def upsert_author_card(page_html, card, slug):
    existing = re.search(
        rf'[ \t]*<a class="post-card" href="/aktuelles/{re.escape(slug)}".*?</a>\n',
        page_html, re.S)
    if existing:
        return page_html[:existing.start()] + card + page_html[existing.end():]
    anchor = re.search(r'<div class="posts-grid">\n', page_html)
    if not anchor:
        raise PublishError("Autorenseite hat kein posts-grid — Karte kann nicht eingefügt werden.")
    return page_html[:anchor.end()] + "\n" + card + page_html[anchor.end():]
```

In `build_post`: resolve the author's registry `id` where the author is matched (only known authors have one — `entry["id"]` in the `entry and not new_author` branch, else `None`). In the write block, after the index update:

```python
        author_page_rel = None
        apath = author_page_path(author_id) if author_id else None
        if apath and os.path.exists(apath) and not original_slug:
            acard = AUTHOR_CARD.format(
                slug=post_slug, cover=cover_rel, dims=dims,
                alt=esc(alt or title).replace('"', "&quot;"),
                iso_date=date, date_label=date_label, title_plain=esc(title),
                excerpt=esc(teaser(subtitle, body)), read_more=cfg["read_more"],
            )
            page_html_author = open(apath, encoding="utf-8").read()
            with open(apath, "w", encoding="utf-8") as fh:
                fh.write(upsert_author_card(page_html_author, acard, post_slug))
            author_page_rel = os.path.relpath(apath, ROOT)
            files.append(author_page_rel)
```

(The dry-run path sets `author_page_rel = None` before the `if write:` block; compute `apath`/eligibility before it so the return value is meaningful for `write=False` too if trivial — otherwise just return `None` on dry runs.) Add `"author_page": author_page_rel` to the return dict.

- [ ] **Step 4: Run full suite**

Run: `python3 -m pytest scripts/tests/ -v` — PASS.

- [ ] **Step 5: Update the skill doc**

In `.claude/skills/publish/SKILL.md`: line 24, langs become `de en tr ru uk ar ku fa`. Rewrite the „Author pages" section: the card is now added automatically by `build_post`; the manual instruction becomes a verification instruction („öffne die Autorenseite und prüfe, dass der neue Beitrag oben in der Beiträge-Liste steht"). Keep the rules (translations get no card; pages are opt-in).

- [ ] **Step 6: Commit**

```bash
git add scripts/publish_post.py scripts/tests/test_build_post.py .claude/skills/publish/SKILL.md
git commit -m "feat: publish adds the post card to the author page automatically"
```

---

### Task 5: Update mode in `build_post`

**Files:**
- Modify: `scripts/publish_post.py` (`build_post`; `add_card` area line 625; CLI arg parser `main()` gets `--update`)
- Test: `scripts/tests/test_build_post.py`

**Interfaces:**
- Consumes: Task 2 registry, Task 4 `upsert_author_card`.
- Produces: `build_post(..., update=False)`:
  - `update=True` requires the page, manuscript entry and registry entry to exist (else `PublishError`), allows the existing page, and **replaces** instead of prepending: index card (helper `replace_card(index_html, card, slug) -> str`, falls back to `add_card` when missing), author-page card (via `upsert_author_card`), registry entry, manuscript.
  - `image_path=None` is allowed only with `update=True`: the existing cover `assets/blog/<slug>-cover.*` is kept (its `cover_rel`/`dims` are read from disk); a `PublishError` if none exists.
  - The chip step still runs (no-op when the chip exists).

- [ ] **Step 1: Write the failing tests**

```python
def test_update_replaces_page_and_card(repo, cover, author_page):
    publish_post.build_post(MD, cover, lang="de", date="2026-08-03", write=True)
    changed = MD.replace("Erster Absatz", "Geänderter Absatz")
    r = publish_post.build_post(changed, None, lang="de", date="2026-08-03",
                                slug="ein-test", update=True, write=True)
    page = (repo / "aktuelles" / "ein-test.html").read_text(encoding="utf-8")
    assert "Geänderter Absatz" in page
    index = (repo / "aktuelles" / "index.html").read_text(encoding="utf-8")
    assert index.count('href="/aktuelles/ein-test"') == 1
    author_html = author_page.read_text(encoding="utf-8")
    assert author_html.count('href="/aktuelles/ein-test"') == 1
    ms = (repo / "assets" / "blog" / "manuscripts" / "ein-test.md").read_text(encoding="utf-8")
    assert "Geänderter Absatz" in ms
    assert r["cover_rel"] == "/assets/blog/ein-test-cover.png"  # kept


def test_update_with_new_cover_replaces_file(repo, cover, tmp_path):
    publish_post.build_post(MD, cover, lang="de", date="2026-08-03", write=True)
    jpg = tmp_path / "neu.jpg"
    jpg.write_bytes(bytes.fromhex(
        "ffd8ffe000104a46494600010100000100010000ffdb004300ffffffffffffffffffffff"
        "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
        "ffffffffffffffffffffffffffc2000b080001000101011100ffc40014100100000000000"
        "00000000000000000000000ffda0008010100013f10ffd9"))
    r = publish_post.build_post(MD, str(jpg), lang="de", date="2026-08-03",
                                slug="ein-test", update=True, write=True)
    assert r["cover_rel"] == "/assets/blog/ein-test-cover.jpg"
    assert not (repo / "assets" / "blog" / "ein-test-cover.png").exists()
    assert "assets/blog/ein-test-cover.png" in r["files"]  # staged deletion


def test_update_requires_existing_post(repo, cover):
    with pytest.raises(publish_post.PublishError):
        publish_post.build_post(MD, cover, lang="de", date="2026-08-03",
                                slug="gibt-es-nicht", update=True, write=True)


def test_new_post_still_refuses_existing_slug(repo, cover):
    publish_post.build_post(MD, cover, lang="de", date="2026-08-03", write=True)
    with pytest.raises(publish_post.PublishError):
        publish_post.build_post(MD, cover, lang="de", date="2026-08-03", write=True)
```

If the hex-JPEG fixture proves fiddly, generate a 1×1 JPEG once with any tool and embed its base64 like `COVER_PNG` — the point is only that the extension differs.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest scripts/tests/test_build_post.py -v -k update`
Expected: FAIL — `TypeError: build_post() got an unexpected keyword argument 'update'`

- [ ] **Step 3: Implement**

Add next to `add_card`:

```python
def replace_card(index_html, card, slug):
    existing = re.search(
        rf'[ \t]*<a class="post-card" href="/aktuelles/{re.escape(slug)}".*?</a>\n',
        index_html, re.S)
    if not existing:
        return add_card(index_html, card)
    return index_html[:existing.start()] + card + index_html[existing.end():]
```

In `build_post`:
- Signature: `..., original_slug=None, update=False, write=False` and allow `image_path=None`.
- Guard block replacing the current "already exists" check:

```python
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
```

- Cover block: when `image_path is None` (only legal with `update`), glob `IMG_DIR/<slug>-cover.*`, use it for `ext`/`cover_rel`/`image_size`; else current behaviour. On update with a new image whose ext differs, `os.remove` the old cover in the write path and append its relpath to `files` (git add stages the deletion).
- Write path: `index_html = replace_card(...) if update else add_card(...)`; author-page card goes through `upsert_author_card` in both modes already (Task 4), so nothing changes there. Skip the cover copy when `image_path is None`.
- `main()`: add `--update` flag and make `--image` optional (`required=False`, error when missing and not `--update`).

- [ ] **Step 4: Run full suite**

Run: `python3 -m pytest scripts/tests/ -v` — PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/publish_post.py scripts/tests/test_build_post.py
git commit -m "feat: build_post update mode edits a published post in place"
```

---

### Task 6: App backend — posts list, edit-load, translation-init, mode-aware publish

**Files:**
- Modify: `scripts/publish_app.py` (SESSION line 31; `do_GET` line 109; `do_POST` dispatch line 132; `api_preview` line 200; `api_publish` line 243)
- Test: `scripts/tests/test_publish_app.py` (new)

**Interfaces:**
- Consumes: Tasks 2/4/5 (`load_posts`, `update=`, `original_slug=`).
- Produces (the UI tasks call these):
  - `GET /api/posts` → `{"ok": true, "posts": [entry…]}` — originals sorted date-desc, each with `"slug"`, `"cover"` (site-relative cover URL or `null`), `"translations": [entry…]`.
  - `POST /api/edit-load` `{slug}` → `{"ok": true, "markdown", "title", "subtitle", "slug", "lang", "date", "author", "tag", "highlight", "alt", "caption", "cover", "langs": {...}}` and sets `SESSION["mode"]="edit"`, `SESSION["cover_path"]` to the repo cover (so preview works without an upload).
  - `POST /api/translation-init` `{slug}` → `{"ok": true, "original": entry, "available_langs": {code: label}, "author", "cover"}` and sets `SESSION["mode"]="translate"`, `SESSION["translate_of"]=slug`, `SESSION["cover_path"]` to the original's cover.
  - `api_convert` sets `SESSION["mode"]="new"` (and clears `translate_of`) **unless** mode is `"translate"` (a translation's manuscript arrives via convert too — only the cover part of convert becomes optional then).
  - `api_preview` forwards `update=(mode=="edit")` and `original_slug=SESSION.get("translate_of")` into `build_post`, and forces the slug in translate mode to `f"{translate_of}-{lang}"`.
  - `api_publish` commit message: `content: update {title}` in edit mode, else `content: add {title}`.

- [ ] **Step 1: Write the failing tests**

Test the handler logic without sockets by extracting pure functions. First refactor target: the API methods already only use `self.send_json` + body dicts — add a tiny harness:

```python
# scripts/tests/test_publish_app.py
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import publish_app
import publish_post

from test_build_post import repo, cover, MD, INDEX_MIN  # noqa: F401


class FakeHandler(publish_app.Handler):
    """Bypass BaseHTTPRequestHandler's socket constructor."""
    def __init__(self):
        self.sent = None
    def send_json(self, payload, status=200):
        self.sent = (status, payload)


@pytest.fixture(autouse=True)
def clean_session():
    publish_app.SESSION.update(cover_path=None, cover_rel=None, preview=None,
                               publish_args=None, mode="new", translate_of=None)


def published(repo, cover):
    publish_post.build_post(MD, cover, lang="de", date="2026-08-03", write=True)


def test_api_posts_groups_translations(repo, cover):
    published(repo, cover)
    publish_post.build_post(MD, cover, lang="tr", date="2026-08-04",
                            slug="ein-test-tr", original_slug="ein-test", write=True)
    h = FakeHandler()
    h.api_posts()
    status, payload = h.sent
    assert payload["ok"]
    assert [p["slug"] for p in payload["posts"]] == ["ein-test"]
    assert [t["slug"] for t in payload["posts"][0]["translations"]] == ["ein-test-tr"]


def test_edit_load_returns_manuscript_and_meta(repo, cover):
    published(repo, cover)
    h = FakeHandler()
    h.api_edit_load({"slug": "ein-test"})
    _, payload = h.sent
    assert payload["ok"]
    assert payload["markdown"] == MD
    assert payload["lang"] == "de"
    assert payload["slug"] == "ein-test"
    assert publish_app.SESSION["mode"] == "edit"
    assert os.path.exists(publish_app.SESSION["cover_path"])


def test_edit_load_refuses_locked(repo, cover):
    published(repo, cover)
    reg = publish_post.load_posts()
    reg["posts"]["ein-test"]["locked"] = True
    publish_post.save_posts(reg)
    h = FakeHandler()
    h.api_edit_load({"slug": "ein-test"})
    _, payload = h.sent
    assert not payload["ok"]


def test_translation_init_lists_missing_langs(repo, cover):
    published(repo, cover)
    h = FakeHandler()
    h.api_translation_init({"slug": "ein-test"})
    _, payload = h.sent
    assert payload["ok"]
    assert "de" not in payload["available_langs"]
    assert "tr" in payload["available_langs"]
    assert publish_app.SESSION["mode"] == "translate"


def test_preview_in_translate_mode_forces_slug(repo, cover):
    published(repo, cover)
    h = FakeHandler()
    h.api_translation_init({"slug": "ein-test"})
    h.api_preview({"markdown": MD, "lang": "tr", "date": "2026-08-05",
                   "slug": "ignoriert"})
    _, payload = h.sent
    assert payload["ok"] and payload["fidelity_ok"]
    assert payload["slug"] == "ein-test-tr"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest scripts/tests/test_publish_app.py -v`
Expected: FAIL — `AttributeError: 'FakeHandler' object has no attribute 'api_posts'`

- [ ] **Step 3: Implement in `scripts/publish_app.py`**

- SESSION init becomes `{"cover_path": None, "cover_rel": None, "preview": None, "publish_args": None, "mode": "new", "translate_of": None}`.
- `_cover_path_for(slug)`: glob `publish_post.IMG_DIR` for `f"{slug}-cover.*"`, return abs path or `None`.
- New methods + dispatch entries (`/api/posts` also as GET in `do_GET`):

```python
    def api_posts(self, body=None):
        posts = publish_post.load_posts()["posts"]
        def entry(slug):
            e = dict(posts[slug], slug=slug)
            cover = _cover_path_for(slug)
            e["cover"] = "/" + os.path.relpath(cover, ROOT) if cover else None
            return e
        originals = sorted(
            (s for s, e in posts.items() if not e.get("original_slug")),
            key=lambda s: posts[s]["date"] or "", reverse=True)
        out = []
        for slug in originals:
            e = entry(slug)
            e["translations"] = sorted(
                (entry(s) for s, t in posts.items() if t.get("original_slug") == slug),
                key=lambda t: t["lang"])
            out.append(e)
        self.send_json({"ok": True, "posts": out})

    def api_edit_load(self, body):
        slug = body["slug"]
        posts = publish_post.load_posts()["posts"]
        if slug not in posts:
            raise PublishError(f"'{slug}' ist nicht im Register.")
        if posts[slug].get("locked"):
            raise PublishError(f"'{slug}' ist gesperrt und kann nur im Terminal bearbeitet werden.")
        ms = os.path.join(publish_post.MANUSCRIPTS_DIR, slug + ".md")
        if not os.path.exists(ms):
            raise PublishError(f"Manuskript für '{slug}' fehlt — bitte Backfill prüfen.")
        SESSION.update(mode="edit", translate_of=None, preview=None,
                       publish_args=None, cover_rel=None,
                       cover_path=_cover_path_for(slug))
        e = posts[slug]
        self.send_json({"ok": True, "markdown": open(ms, encoding="utf-8").read(),
                        "slug": slug, "cover": "/" + os.path.relpath(SESSION["cover_path"], ROOT)
                            if SESSION["cover_path"] else None,
                        "langs": {c: cfg["label"] for c, cfg in LANGS.items()},
                        **{k: e[k] for k in ("title", "lang", "date", "author",
                                             "tag", "highlight", "alt", "caption")}})

    def api_translation_init(self, body):
        slug = body["slug"]
        posts = publish_post.load_posts()["posts"]
        if slug not in posts:
            raise PublishError(f"'{slug}' ist nicht im Register.")
        taken = {posts[slug]["lang"]} | {
            t["lang"] for t in posts.values() if t.get("original_slug") == slug}
        SESSION.update(mode="translate", translate_of=slug, preview=None,
                       publish_args=None, cover_rel=None,
                       cover_path=_cover_path_for(slug))
        self.send_json({"ok": True, "original": dict(posts[slug], slug=slug),
                        "author": posts[slug]["author"],
                        "cover": "/" + os.path.relpath(SESSION["cover_path"], ROOT)
                            if SESSION["cover_path"] else None,
                        "available_langs": {c: LANGS[c]["label"]
                                            for c in LANGS if c not in taken}})
```

- `api_convert`: keep behaviour, but make the cover part conditional — when `SESSION["mode"] == "translate"` and no `cover_b64` in the body, leave `SESSION["cover_path"]` (the original's cover) untouched; when mode is not `translate`, first `SESSION.update(mode="new", translate_of=None)`.
- `api_preview`: build kwargs as today plus

```python
            update=(SESSION["mode"] == "edit"),
            original_slug=SESSION.get("translate_of"),
```

and before that: `if SESSION["mode"] == "translate": body["slug"] = f"{SESSION['translate_of']}-{body['lang']}"`; `if SESSION["mode"] == "edit": body["slug"] = SESSION-stored edit slug` (store `edit_slug` in `api_edit_load`; simplest: reuse `translate_of=None` and add `SESSION["edit_slug"]`). Also `slug_exists` in the response must be `False` in edit mode (the page exists by definition).
- `api_publish`: `msg = f"content: {'update' if SESSION['mode'] == 'edit' else 'add'} {r['title']}"`.

- [ ] **Step 4: Run full suite**

Run: `python3 -m pytest scripts/tests/ -v` — PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/publish_app.py scripts/tests/test_publish_app.py
git commit -m "feat: app API for post list, edit mode and translations"
```

---

### Task 7: App UI — start screen and post list

**Files:**
- Modify: `scripts/publish_app.html` (screens block from line ~330; `state`/step logic from ~515)

**Interfaces:**
- Consumes: `GET /api/posts` (Task 6 shape).
- Produces: DOM ids the next task wires into: `screen-home`, `btn-home-new`, `btn-home-manage`, `screen-list`, `list-body`; per-row buttons carry `data-action="edit"|"translate"` and `data-slug`. A nav helper `show(screenId)` (replacing the current implicit screen switching) and `state.mode` (`"new" | "edit" | "translate"`).

- [ ] **Step 1: Add the two new screens before `screen-drop`**

```html
  <!-- SCREEN 0: HOME -->
  <section id="screen-home">
    <div class="card">
      <div class="dropzones">
        <div class="dropzone" id="btn-home-new" tabindex="0" role="button">
          <div class="zone-icon" aria-hidden="true">✍️</div>
          <div class="zone-label">Neuer Beitrag</div>
          <div class="zone-hint">Manuskript &amp; Titelbild hochladen</div>
        </div>
        <div class="dropzone" id="btn-home-manage" tabindex="0" role="button">
          <div class="zone-icon" aria-hidden="true">🗂️</div>
          <div class="zone-label">Beiträge verwalten</div>
          <div class="zone-hint">Bearbeiten · Übersetzung hinzufügen</div>
        </div>
      </div>
    </div>
  </section>

  <!-- SCREEN 0b: LIST -->
  <section id="screen-list" hidden>
    <div class="card">
      <div id="list-error" class="banner banner-error" hidden></div>
      <div id="list-body"></div>
      <div class="actions actions-split">
        <a href="#" id="btn-list-back" class="link-muted">← Zurück</a>
      </div>
    </div>
  </section>
```

The steps `<ol id="steps">` and the `<h1>` stay hidden on home/list (`document.querySelector("h1")` text becomes „Blog verwalten" on those screens, „Neuer Blogpost"/„Beitrag bearbeiten"/„Übersetzung hinzufügen" per mode elsewhere).

- [ ] **Step 2: Render the list**

```html
<style>
  .post-row{ display:flex; gap:14px; align-items:center; padding:12px 0;
             border-bottom:1px solid var(--line, #e5e7ee); }
  .post-row img{ width:72px; height:48px; object-fit:cover; border-radius:8px; }
  .post-row .grow{ flex:1; min-width:0; }
  .post-row .title{ font-weight:600; }
  .post-row .meta{ color:#667; font-size:13px; }
  .post-row.is-translation{ margin-left:56px; }
  .post-row .badge{ font-size:12px; border:1px solid currentColor;
                    border-radius:999px; padding:1px 8px; }
</style>
```

```js
async function loadList() {
  const r = await fetch("/api/posts").then(r => r.json());
  const body = document.getElementById("list-body");
  body.innerHTML = "";
  for (const p of r.posts) {
    body.appendChild(postRow(p, false));
    for (const t of p.translations) body.appendChild(postRow(t, true));
  }
}

function postRow(p, isTranslation) {
  const row = document.createElement("div");
  row.className = "post-row" + (isTranslation ? " is-translation" : "");
  const locked = p.locked;
  row.innerHTML = `
    ${p.cover ? `<img src="${p.cover}" alt="">` : ""}
    <div class="grow">
      <div class="title">${p.title}</div>
      <div class="meta">${p.date} · ${p.author} · <span class="badge">${p.lang}</span>
        ${locked ? " · 🔒 gesperrt" : ""}</div>
    </div>
    ${locked ? "" : `<button class="btn btn-secondary" data-action="edit"
        data-slug="${p.slug}">Bearbeiten</button>`}
    ${isTranslation ? "" : `<button class="btn btn-secondary" data-action="translate"
        data-slug="${p.slug}">Übersetzung +</button>`}`;
  return row;
}
```

Wire `#btn-home-new` → existing drop screen (`state.mode = "new"`), `#btn-home-manage` → `loadList(); show("screen-list")`, `#btn-list-back` → home. Delegate clicks on `#list-body` by `data-action` (handlers land in Task 8 — for now `console.log`). Existing „Weiteren Beitrag veröffentlichen" link goes to `screen-home`.

- [ ] **Step 3: Manual check**

Run `python3 scripts/publish_app.py`, open http://localhost:8765 **in a browser**: home screen shows two tiles; „Beiträge verwalten" lists the real posts newest-first with the medienpreis translations indented beneath their original; locked rows (if any) show 🔒 and no Bearbeiten button. Ctrl+C the server.

- [ ] **Step 4: Commit**

```bash
git add scripts/publish_app.html
git commit -m "feat: app start screen and post list"
```

---

### Task 8: App UI — edit and translation flows

**Files:**
- Modify: `scripts/publish_app.html`

**Interfaces:**
- Consumes: `/api/edit-load`, `/api/translation-init` (Task 6 shapes), `state.mode`, `show()` from Task 7.
- Produces: fully working Bearbeiten and Übersetzung flows through the existing form → preview → publish screens.

- [ ] **Step 1: Edit flow**

Click `data-action="edit"`:

```js
async function startEdit(slug) {
  const r = await fetch("/api/edit-load", {method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({slug})}).then(r => r.json());
  if (!r.ok) return showListError(r.error);
  state.mode = "edit";
  state.convert = r;                       // same shape api_convert feeds the form
  fillForm(r);                             // existing form-filling routine
  document.getElementById("f-slug").value = r.slug;
  document.getElementById("f-slug").disabled = true;
  document.getElementById("f-lang").disabled = true;
  document.querySelector("h1").textContent = "Beitrag bearbeiten";
  showCoverPreview(r.cover);               // small <img> near the form, new element
  show("screen-form");
}
```

`fillForm` is extracted from the current `api/convert` success handler so both paths share it (title/subtitle display, lang select, date, author, tag, highlight, alt, caption, markdown textarea). Add a „Titelbild ersetzen" file input on the form screen, visible only in edit/translate mode; when a file is chosen it is sent with the next `/api/convert`-style upload — simplest correct wiring: a dedicated `POST /api/replace-cover {cover_name, cover_b64}` that just updates `SESSION["cover_path"]` (5-line handler in `publish_app.py`, add it in this task with a unit test in `test_publish_app.py` following the FakeHandler pattern).

Publish button text in edit mode: „Änderungen veröffentlichen". Result screen header: „Aktualisiert!".

- [ ] **Step 2: Translation flow**

Click `data-action="translate"`:

```js
async function startTranslate(slug) {
  const r = await fetch("/api/translation-init", {method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({slug})}).then(r => r.json());
  if (!r.ok) return showListError(r.error);
  state.mode = "translate";
  state.translateInit = r;
  document.querySelector("h1").textContent =
    `Übersetzung: ${r.original.title}`;
  show("screen-drop");
  // drop screen variant: cover zone shows the inherited cover as optional
  document.getElementById("zone-cover").classList.add("is-optional");
  document.querySelector("#zone-cover .zone-hint").textContent =
    "optional — Titelbild wird vom Original übernommen";
  updateContinueButton();   // manuscript alone enables Weiter in translate mode
}
```

After convert, restrict `#f-lang` to `r.available_langs`, prefill author from `r.author`, set the slug field to `${slug}-${lang}` and disable it, re-deriving on language change. The manuscript still goes through `/api/convert` (server keeps the inherited cover because mode is `translate` and no cover bytes are sent).

- [ ] **Step 3: Full manual pass**

`python3 scripts/publish_app.py`, in the browser:
1. Bearbeiten on `wem-gehort-berlin`: form pre-filled, slug/lang locked, markdown matches the live text. Change one word → Vorschau → fidelity green, card preview correct → **stop before publishing** (do not push content changes during development; verify then Zurück).
2. Übersetzung + on `wem-gehort-berlin`: language list excludes `de`, cover inherited, slug derives `wem-gehort-berlin-<lang>`. Cancel before publish.
3. Neuer Beitrag flow still works end to end up to the preview.

- [ ] **Step 4: Run suite, commit**

`python3 -m pytest scripts/tests/ -v` — PASS.

```bash
git add scripts/publish_app.html scripts/publish_app.py scripts/tests/test_publish_app.py
git commit -m "feat: app edit and translation flows"
```

---

### Task 9: Author creation in the app

**Files:**
- Create: `scripts/author_page_template.html`
- Modify: `scripts/publish_post.py` (add `render_author_page`), `scripts/publish_app.py` (`/api/new-author`, git-flow refactor), `scripts/publish_app.html` (author panel)
- Test: `scripts/tests/test_publish_app.py`, `scripts/tests/test_build_post.py`

**Interfaces:**
- Consumes: `match_author`, `slugify`, `fold`, Task 4's grid markup contract.
- Produces:
  - `publish_post.render_author_page(name, role, bio_paragraphs: list[str], photo_rel: str) -> str` — full page HTML containing an empty `<div class="posts-grid">\n\n          </div>` (so `upsert_author_card` finds its anchor).
  - `POST /api/new-author` `{canonical, role, names?, aliases?, page?: {bio, photo_b64, photo_ext}}` → `{"ok": true, "id", "canonical", "committed": bool, "git_output"}`. Registers in `authors.json`; with `page`, writes `assets/autoren/<id>.<ext>` and `journalistennetzwerk/<id>.html`; commits+pushes via the shared git flow.
  - `publish_app.git_flow(files: list[str], msg: str) -> (ok: bool, stage: str, log: str)` — the pull/add/commit/push sequence extracted from `api_publish`, reused by both.

- [ ] **Step 1: Create the template**

Copy `journalistennetzwerk/suleyman-bag.html` to `scripts/author_page_template.html` and parameterize: every occurrence of the name → `{name}`, the role line → `{role}`, meta description → `{description}` (= `"{name} – {role}. Porträt und Beiträge auf ZWISCHENWELTEN."`), photo src → `{photo}`, the `<div class="author-bio …">` content → `{bio_html}`, and the posts-grid emptied to:

```html
          <div class="posts-grid">

          </div>
```

Escape the template's literal CSS/JS braces for `str.format` — **do not** use `str.format`; use `string.Template`-style manual replacement instead:

```python
AUTHOR_PAGE_TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "author_page_template.html")

def render_author_page(name, role, bio_paragraphs, photo_rel):
    tpl = open(AUTHOR_PAGE_TEMPLATE, encoding="utf-8").read()
    bio_html = "\n                  ".join(
        f"<p>{esc(p)}</p>" for p in bio_paragraphs if p.strip())
    for key, val in [("__NAME__", esc(name)), ("__ROLE__", esc(role)),
                     ("__PHOTO__", photo_rel), ("__BIO__", bio_html),
                     ("__DESCRIPTION__",
                      esc(f"{name} – {role}. Porträt und Beiträge auf ZWISCHENWELTEN."))]:
        tpl = tpl.replace(key, val)
    return tpl
```

(Use `__NAME__`-style placeholders in the template file accordingly.)

- [ ] **Step 2: Write the failing tests**

```python
# in test_build_post.py
def test_render_author_page(repo):
    html = publish_post.render_author_page(
        "Ayşe Örnek", "Journalistin", ["Absatz eins.", "Absatz zwei."],
        "/assets/autoren/ayse-ornek.png")
    assert "Ayşe Örnek" in html
    assert "<p>Absatz eins.</p>" in html
    assert '<div class="posts-grid">' in html
    assert "Süleyman" not in html
    # the generated grid must accept cards
    card = publish_post.AUTHOR_CARD.format(
        slug="x", cover="/c.png", dims="", alt="", iso_date="2026-01-01",
        date_label="1. Januar 2026", title_plain="X", excerpt="", read_more="Weiterlesen")
    assert "/aktuelles/x" in publish_post.upsert_author_card(html, card, "x")
```

```python
# in test_publish_app.py
COVER_PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGBgAAAABQABh6FO1AAAAABJRU5ErkJggg=="


def test_new_author_registers_and_builds_page(repo, monkeypatch):
    monkeypatch.setattr(publish_app, "git_flow", lambda files, msg: (True, "", "ok"))
    (repo / "assets" / "autoren").mkdir(parents=True)
    h = FakeHandler()
    h.api_new_author({"canonical": "Ayşe Örnek", "role": "Journalistin",
                      "page": {"bio": "Absatz eins.\n\nAbsatz zwei.",
                               "photo_b64": COVER_PNG_B64, "photo_ext": ".png"}})
    _, payload = h.sent
    assert payload["ok"] and payload["id"] == "ayse-ornek"
    reg = json.loads((repo / "assets" / "blog" / "authors.json").read_text())
    assert any(a["id"] == "ayse-ornek" for a in reg["authors"])
    assert (repo / "journalistennetzwerk" / "ayse-ornek.html").exists()
    assert (repo / "assets" / "autoren" / "ayse-ornek.png").exists()


def test_new_author_refuses_known_person(repo, monkeypatch):
    monkeypatch.setattr(publish_app, "git_flow", lambda files, msg: (True, "", "ok"))
    h = FakeHandler()
    h.api_new_author({"canonical": "Сулейман Баг", "role": "x"})
    _, payload = h.sent
    assert not payload["ok"]
    assert "Süleyman Bağ" in payload["error"]
```

Note: `render_author_page` and `api_new_author` must resolve paths through `publish_post.ROOT`-derived module attributes so the `repo` fixture's monkeypatching reaches them (in `publish_app.py`, compute paths from `publish_post.ROOT` at call time, not import time; add `AUTOR_PHOTO_DIR = os.path.join(publish_post.ROOT, "assets", "autoren")` style lookups inside the handler and monkeypatch-friendly `publish_post.AUTHOR_PAGES_DIR` usage inside `render_author_page`'s caller).

- [ ] **Step 3: Run tests to verify they fail**

Run: `python3 -m pytest scripts/tests/ -v -k author` — FAIL (`render_author_page` missing).

- [ ] **Step 4: Implement**

- `render_author_page` as above; template file from Step 1.
- In `publish_app.py`: extract `git_flow(files, msg)` from `api_publish` (returns `(ok, stage, log)`; `api_publish` keeps its per-stage error JSON by mapping over the return) and add:

```python
    def api_new_author(self, body):
        name = (body.get("canonical") or "").strip()
        role = (body.get("role") or "").strip()
        if not name or not role:
            raise PublishError("Name und Rolle sind Pflichtfelder.")
        registry = publish_post.load_authors()
        entry, _ = publish_post.match_author(name, registry)
        if entry:
            raise PublishError(
                f"'{name}' ist bereits als '{entry['canonical']}' registriert.")
        author_id = publish_post.slugify(name)
        registry["authors"].append({
            "id": author_id, "canonical": name, "role": role,
            "names": body.get("names") or {}, "aliases": body.get("aliases") or [],
        })
        with open(publish_post.AUTHORS, "w", encoding="utf-8") as fh:
            json.dump(registry, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        files = [os.path.relpath(publish_post.AUTHORS, ROOT)]
        page = body.get("page")
        if page:
            ext = page.get("photo_ext", ".png").lower()
            if ext not in (".png", ".jpg", ".jpeg"):
                raise PublishError("Autorenfoto muss .png oder .jpg sein.")
            photo_dir = os.path.join(publish_post.ROOT, "assets", "autoren")
            os.makedirs(photo_dir, exist_ok=True)
            photo_path = os.path.join(photo_dir, author_id + ext)
            with open(photo_path, "wb") as fh:
                fh.write(base64.b64decode(page["photo_b64"]))
            photo_rel = "/" + os.path.relpath(photo_path, publish_post.ROOT)
            bio_paras = [p.strip() for p in (page.get("bio") or "").split("\n\n")]
            html = publish_post.render_author_page(name, role, bio_paras, photo_rel)
            apath = publish_post.author_page_path(author_id)
            with open(apath, "w", encoding="utf-8") as fh:
                fh.write(html)
            files += [os.path.relpath(apath, publish_post.ROOT),
                      os.path.relpath(photo_path, publish_post.ROOT)]
        ok, stage, log = git_flow(files, f"content: Autor:in {name} registriert")
        self.send_json({"ok": True, "id": author_id, "canonical": name,
                        "committed": ok, "git_output": log})
```

- UI (`publish_app.html`): in the `#author-warn` box, replace the bare checkbox with two options — keep „Als neue Autor:in registrieren" (checkbox, unchanged behaviour for quick registration via publish) and add a „Mit Autorenseite anlegen…" button that expands an inline panel: Rolle (text), Biografie (textarea), Foto (file). Submit → `POST /api/new-author` → on success hide panel, set `#f-author` to the canonical name, re-run the existing author-check, uncheck `#f-new-author`.

- [ ] **Step 5: Run full suite, manual check, commit**

`python3 -m pytest scripts/tests/ -v` — PASS. Manual: create a throwaway author in the app against a scratch branch or verify with the form only up to the request (the endpoint commits — for the manual check use a test branch: `git checkout -b tmp-author-test`, run the app, create „Test Autor", verify page renders via `python3 dev-server.py` at `/journalistennetzwerk/test-autor`, then `git checkout main && git branch -D tmp-author-test` and clean the untracked files: `git checkout main` keeps them — delete `journalistennetzwerk/test-autor.html`, `assets/autoren/test-autor.*` and revert `authors.json` if the commit landed on the temp branch only; **do not push**).

```bash
git add scripts/author_page_template.html scripts/publish_post.py scripts/publish_app.py scripts/publish_app.html scripts/tests/
git commit -m "feat: register authors and generate author pages from the app"
```

---

### Task 10: Rich-text editor

**Files:**
- Modify: `scripts/publish_app.py` (`/api/md-to-html`, `/api/html-to-md`), `scripts/publish_app.html` (tabs + toolbar + contenteditable), `scripts/html_to_md.py` (only if fragment gaps surface)
- Test: `scripts/tests/test_publish_app.py`

**Interfaces:**
- Consumes: `publish_post.parse_md`, `publish_post.md_to_blocks`, `publish_post.find_author_in_md`, `html_to_md.fragment_to_md`.
- Produces:
  - `POST /api/md-to-html` `{markdown, lang}` → `{"ok": true, "html"}` — editable fragment: `<h1>` title, `<p><em>subtitle</em></p>`, `<p>Author: …</p>`, then the exact `md_to_blocks` body markup.
  - `POST /api/html-to-md` `{html}` → `{"ok": true, "markdown"}`.

- [ ] **Step 1: Write the failing tests**

```python
def test_md_to_html_and_back_round_trips(repo):
    h = FakeHandler()
    h.api_md_to_html({"markdown": MD, "lang": "de"})
    _, payload = h.sent
    assert payload["ok"]
    assert payload["html"].startswith("<h1>Ein Test</h1>")
    assert "<em>Der Untertitel</em>" in payload["html"]
    assert "Author: Süleyman Bağ" in payload["html"]

    h2 = FakeHandler()
    h2.api_html_to_md({"html": payload["html"]})
    _, p2 = h2.sent
    assert p2["ok"]
    # word-identical: rebuilding from the round-tripped md must satisfy fidelity
    import publish_post
    r = publish_post.build_post(p2["markdown"], None, lang="de",
                                date="2026-08-03", slug="rt", author=None,
                                write=False)
    assert r["title"] == "Ein Test"
```

(If `build_post` requires `image_path` even for `write=False`, pass the `cover` fixture instead of `None` — Task 5 made `None` legal only with `update=True`.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest scripts/tests/test_publish_app.py -v -k round_trips` — FAIL.

- [ ] **Step 3: Implement the endpoints**

```python
    def api_md_to_html(self, body):
        md, lang = body["markdown"], body.get("lang") or "de"
        byline = publish_post.find_author_in_md(md)
        title, subtitle, body_md = publish_post.parse_md(md, lang)
        parts = [f"<h1>{publish_post.esc(title)}</h1>"]
        if subtitle:
            parts.append(f"<p><em>{publish_post.esc(subtitle)}</em></p>")
        if byline:
            parts.append(f"<p>Author: {publish_post.esc(byline)}</p>")
        parts.append(publish_post.md_to_blocks(body_md, lang))
        self.send_json({"ok": True, "html": "\n".join(parts)})

    def api_html_to_md(self, body):
        from html_to_md import fragment_to_md
        self.send_json({"ok": True, "markdown": fragment_to_md(body["html"])})
```

Watch one subtlety: `fragment_to_md` must keep the `Author:` paragraph on its own line (it does — paragraphs become their own blocks) and the em-para subtitle must come out as `*…*` so `parse_md` re-detects it. If the smart-quoted body (typographic quotes/dashes from `inline()`) fails the fidelity check after a round trip, extend `words()`-compatible normalization *inside `fragment_to_md`* — never touch `check_fidelity`.

- [ ] **Step 4: Build the UI**

Replace the `<details class="md-details">` block with:

```html
      <div class="editor-tabs" role="tablist">
        <button type="button" id="tab-md" class="tab is-active" role="tab">Markdown</button>
        <button type="button" id="tab-rich" class="tab" role="tab">Rich Text</button>
      </div>
      <textarea id="f-markdown" spellcheck="false"></textarea>
      <div id="rich-wrap" hidden>
        <div class="rich-toolbar">
          <button type="button" data-cmd="bold"><b>F</b></button>
          <button type="button" data-cmd="italic"><i>K</i></button>
          <button type="button" data-block="h2">H2</button>
          <button type="button" data-block="h3">H3</button>
          <button type="button" data-block="p">¶</button>
          <button type="button" data-cmd="insertUnorderedList">• Liste</button>
          <button type="button" data-block="blockquote">„Zitat“</button>
          <button type="button" id="rich-link">Link</button>
        </div>
        <div id="f-rich" contenteditable="true" spellcheck="false"></div>
        <div class="rich-linkbar" id="rich-linkbar" hidden>
          <input type="url" id="rich-link-url" placeholder="https://…">
          <button type="button" id="rich-link-apply" class="btn btn-secondary">OK</button>
        </div>
      </div>
```

```js
let richActive = false;

async function toRich() {
  const r = await api("/api/md-to-html", {markdown: f("f-markdown").value,
                                          lang: f("f-lang").value});
  if (!r.ok) return showFormError(r.error);
  f("f-rich").innerHTML = r.html;
  richActive = true; toggleTabs();
}

async function toMarkdown() {
  const r = await api("/api/html-to-md", {html: f("f-rich").innerHTML});
  if (!r.ok) return showFormError(r.error);
  f("f-markdown").value = r.markdown;
  richActive = false; toggleTabs();
}

// before Vorschau: serialize if the rich tab is active
async function syncEditor() { if (richActive) await toMarkdown(); }

document.querySelectorAll(".rich-toolbar [data-cmd]").forEach(b =>
  b.addEventListener("click", () => document.execCommand(b.dataset.cmd)));
document.querySelectorAll(".rich-toolbar [data-block]").forEach(b =>
  b.addEventListener("click", () =>
    document.execCommand("formatBlock", false, b.dataset.block)));
// link: no window.prompt (blocks automation) — inline URL bar
f("rich-link").addEventListener("click", () => {
  savedRange = window.getSelection().getRangeAt(0);
  f("rich-linkbar").hidden = false; f("rich-link-url").focus();
});
f("rich-link-apply").addEventListener("click", () => {
  const sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(savedRange);
  document.execCommand("createLink", false, f("rich-link-url").value);
  f("rich-linkbar").hidden = true; f("rich-link-url").value = "";
});
```

(`f(id)` = `document.getElementById`; `api(url, body)` = the existing JSON-POST helper — reuse whatever helper names the file already has.) The `btn-preview` handler calls `await syncEditor()` first. Style `#f-rich` with the form's font, min-height 320px, and the article's blockquote/list styling at reduced scale so editors see structure.

- [ ] **Step 5: Manual pass**

App im Browser: convert a manuscript → Rich-Text tab → bold a word, add an H2, a list, a quote and a link → back to Markdown tab: the markdown shows `**…**`, `## …`, `- …`, `> …`, `[…](…)`. Vorschau → fidelity green. Switch tabs repeatedly: content stable (no duplication, no lost words).

- [ ] **Step 6: Run suite, commit**

`python3 -m pytest scripts/tests/ -v` — PASS.

```bash
git add scripts/publish_app.py scripts/publish_app.html scripts/tests/test_publish_app.py
git commit -m "feat: rich text editing tab backed by server-side converters"
```

---

### Task 11: End-to-end verification + docs

**Files:**
- Modify: `.claude/skills/publish/SKILL.md` (Browser-App section), `scripts/publish_app.py` docstring

**Interfaces:** none — verification and documentation only.

- [ ] **Step 1: Full suite + fresh backfill sanity**

```bash
python3 -m pytest scripts/tests/ -v
python3 scripts/backfill_manuscripts.py    # expect: all "skipped"
git status                                  # expect: clean except intended docs edits
```

- [ ] **Step 2: Browser walkthrough**

`python3 scripts/publish_app.py` and in the browser:
1. Home → Liste: all posts, translations grouped, covers shown.
2. Bearbeiten `wem-gehort-berlin` → rich text tab → tiny wording change → Vorschau (fidelity green) → **Veröffentlichen only with the user's explicit go-ahead**; otherwise back out and restore.
3. Übersetzung + → language choice correct → cancel.
4. Neuer Beitrag with a scratch manuscript → up to Vorschau → cancel.
5. `python3 dev-server.py` (other terminal): `/aktuelles/`, one post page, and `/journalistennetzwerk/suleyman-bag` all render correctly — look at the pages, don't trust 200s.

- [ ] **Step 3: Update the docs**

- `SKILL.md` Browser-App section: mention list/edit/translate/author flows, that manuscripts live in `assets/blog/manuscripts/` + `posts.json`, and that the CLI equivalent of editing is `--update`.
- `publish_app.py` module docstring: same one-line summary of the new flows.

- [ ] **Step 4: Final commit**

```bash
git add .claude/skills/publish/SKILL.md scripts/publish_app.py
git commit -m "docs: publish skill + app docs for v2 flows"
```

---

## Self-review notes (already applied)

- Spec coverage: foundation → Tasks 1–3; author-page automation → Task 4; list+edit → Tasks 5–8; translation → Tasks 6+8; author creation → Task 9; rich text → Task 10; skill-doc updates → Tasks 4+11.
- Deviation from spec, intentional: the reverse converter reuses `manuscript_import._MDBuilder` (already exists for docx import) instead of a from-scratch parser; module name `scripts/html_to_md.py` kept as specced.
- `git_flow` extraction (Task 9) must not change `api_publish`'s per-stage JSON contract — the existing failure UI depends on `stage` strings `pull/add/commit/push`.
