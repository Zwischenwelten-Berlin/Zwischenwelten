# Publish App — in-browser blog publishing

**Date:** 2026-08-03
**Status:** Approved design, ready for implementation planning

## Goal

Let an editor publish a blog post to `/aktuelles` without using the CLI or the
`/publish` skill: start a local app, drag a manuscript (`.md`, `.docx`, or legacy
`.doc`) and a cover image into a browser window, review pre-filled metadata,
preview the exact rendered page, and publish to GitHub Pages with one click.

## Context

The mechanical pipeline already exists: `scripts/publish_post.py` converts a
markdown manuscript into a house-styled post (page + overview card + filter chip
+ author registry) and refuses to write anything that does not match the
manuscript word for word (the fidelity gate). This app is a GUI over that
pipeline plus Word-to-markdown conversion up front. It must not duplicate the
rendering logic.

**Assumptions:** the editor has this repo cloned, Python 3, git with push access
to `main`, and runs macOS (needed only for legacy `.doc` support via `textutil`).

## Architecture

Two new files, one refactor:

| Piece | What it is |
|---|---|
| `scripts/publish_app.py` | Stdlib `http.server` on `127.0.0.1:8765`. Fails loudly if the port is occupied (same behaviour as `dev-server.py`). Auto-opens the browser via `webbrowser`. Serves the UI, the JSON API, and the site's real assets from the repo root. |
| `scripts/publish_app.html` | Single-page UI, inline CSS/JS, no build step. Screens: drop → form → preview → publish result. |
| Refactor of `scripts/publish_post.py` | Extract the body of `main()` into `build_post(options, write=False)` returning page HTML, card HTML, slug, resolved author, file paths, and fidelity results. The CLI's behaviour and flags are unchanged; the app imports the module so GUI and CLI share one rendering path forever. |

The only third-party dependency is `mammoth` (docx → HTML), imported lazily —
the app starts and publishes `.md` manuscripts without it.

## Manuscript conversion

- `.md` — used as-is.
- `.docx` — `mammoth` converts to HTML; a small HTML→markdown converter maps it
  to exactly the subset `publish_post.py` understands: headings (h1–h3 → `#`/`##`/`###`),
  paragraphs, bold/italic, bullet lists, blockquotes, links, tables. Unknown or
  unsupported elements degrade to their text content — no wording is ever dropped.
- `.doc` — converted to `.docx` first with macOS `textutil -convert docx` in a
  temp dir, then the `.docx` path.
- If `mammoth` is missing when a Word file is dropped, the UI shows the exact
  install command (`pip3 install mammoth`) instead of a stack trace.

### Language detection

A stopword scorer over the eight site languages (`de en tr ru uk ar ku fa`),
with script detection as a shortcut (Cyrillic → ru/uk, Arabic script → ar/fa).
The result pre-selects the language dropdown; the editor confirms or corrects.
Detection is a convenience, never authoritative.

### Markdown editor escape hatch

The form screen includes a collapsible markdown editor showing the converted
manuscript. This is the fix-it path when a Word doc lacks a Heading-1 title or
converted oddly. Whatever is in this editor is the manuscript of record: the
fidelity gate compares the published page against it, so the gate stays
meaningful even after hand edits.

## Editor flow and API

### Screen 1 — Drop

One screen with two labelled drop zones: manuscript (`.md`/`.docx`/`.doc`) and
cover image (jpg/png). Both are required before continuing. `POST /api/convert` uploads both and returns:

- converted markdown, detected language, title, subtitle
- byline author and registry match (name, matched canonical entry, score) —
  matching reuses `match_author` / `fold` from `publish_post.py`
- proposed slug (from `slugify`)
- warnings (e.g. no Heading-1 title found, empty document)

### Screen 2 — Form (everything pre-filled)

Fields, mirroring the CLI flags: language, date (defaults to today, editor
confirms), author, slug, tag (optional), title highlight (optional, validated
against the title), cover alt text (defaults to title), cover caption
(optional), plus the collapsible markdown editor.

Author handling mirrors the skill's rules: a registry match ≥ 85 % is shown as
"publishing as *canonical name*"; no match shows a warning and a "register as
new author" checkbox that the editor must tick explicitly (equivalent of
`--new-author`). The app never silently creates a second record for a known
person.

### Screen 3 — Preview

`POST /api/preview` sends the form fields + markdown. The server runs
`build_post(write=False)` in memory and the UI shows:

- the full rendered post in an iframe at `/preview/page`, with the site's real
  CSS. The cover is served from a temp file at the exact URL it will have after
  publishing (`/assets/blog/<slug>-cover.<ext>`), so the preview is
  pixel-identical to the live page.
- the overview card as it will appear on `/aktuelles`.
- the fidelity check result. A failing gate blocks the publish button and shows
  the word-level diff.

Nothing is written to the repository at this stage.

### Screen 4 — Publish

`POST /api/publish`:

1. `git pull --rebase` (fail early on conflicts, before writing anything)
2. `build_post(write=True)` — fidelity gate runs again; page, cover, index
   card/chip, and (only with the explicit new-author confirmation) the author
   registry are written
3. `git add` of only the files this post touches
4. `git commit -m "content: add <title>"`
5. `git push origin main`
6. Response: the live URL (`https://zwischenwelten-berlin.de/aktuelles/<slug>`)
   with a note that GitHub Pages takes a minute or two to deploy

## Error handling

| Failure | Behaviour |
|---|---|
| Port 8765 occupied | Startup aborts with a clear message (matches `dev-server.py`). |
| Word file empty / image-only / no extractable text | Inline error on the drop screen. |
| No Heading-1 title | Warning; editor adds one in the markdown editor. |
| Duplicate slug (`aktuelles/<slug>.html` exists) | Inline error on the form; editor picks another slug. |
| Fidelity gate fails | Diff shown, nothing written, publish blocked. |
| `git pull --rebase` conflicts | Abort the rebase, publish nothing, show the git output. |
| `git push` rejected | Files remain committed locally; UI shows git output and a "retry (pull --rebase + push)" button. |
| `mammoth` not installed | Install instruction shown in the UI. |

The server binds to localhost only and is meant for a single local editor; no
auth, no HTTPS, no concurrent-editor handling.

## Testing

- **pytest** in `scripts/tests/` for the pure functions: HTML→markdown
  conversion (headings, emphasis, lists, quotes, links, tables, nesting,
  garbage input) and language detection (a sample per language).
- The refactor of `publish_post.py` is verified by re-publishing an existing
  post via the CLI in `--dry-run` mode and confirming byte-identical output.
- Server flow and UI verified manually end-to-end: drop a real `.docx`, publish
  to a throwaway branch during development, then to `main` once verified.

## Out of scope

- Hosted/remote operation, multi-user access, authentication
- Editing or unpublishing existing posts
- Image editing (resize/crop) — the cover is used as dropped
- Windows/Linux `.doc` support (`.docx` and `.md` work everywhere)
