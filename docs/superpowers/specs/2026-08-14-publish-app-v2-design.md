# Publish-App v2 — Design

**Date:** 2026-08-14
**Status:** Approved by Alper (conversation, 2026-08-14)

## Goal

Extend the browser publishing app (`scripts/publish_app.py` + `publish_app.html`) and the
underlying `publish_post.py` pipeline with:

1. Automatic author-page updates on publish (closes a gap between the publish skill's
   rules and what the app actually does).
2. A post list with editing of existing posts.
3. "Add translation" for an existing post.
4. Author creation from the app, with optional author-page generation.
5. A rich-text editing mode next to the markdown editor in the Angaben step.

The invariant that must survive every change: **all rendering goes through
`publish_post.build_post`, and the fidelity gate (manuscript words == page words) always
runs before anything is written.** The app must never be able to produce HTML the CLI
could not.

## Foundation: manuscript store + post registry

Editing a post requires its source markdown, which today is discarded after publishing.

- **Manuscript store.** Every publish writes the source manuscript to
  `assets/blog/manuscripts/<slug>.md` (exactly as converted, byline included). This file
  is the source of truth when a post is edited later.
- **Post registry.** `assets/blog/posts.json` maps slug → `{lang, date, author
  (canonical), tag, highlight, alt, caption, title, original_slug, locked}`.
  `original_slug` is set only on translations. `build_post` maintains this file on every
  write, so CLI and app publishes both keep it current. The registry powers the post
  list and pre-fills the edit form; nothing renders from it.
- **Backfill.** A one-time CLI (`scripts/backfill_manuscripts.py`) reverse-converts the
  9 existing posts (HTML → MD) and builds the initial registry. Verification per post:
  run `build_post` on the recovered manuscript and fidelity-compare the result against
  the existing page. A post that does not round-trip cleanly (hand-built design
  elements) is written to the registry with `locked: true`: it cannot be edited in the
  app, but translations can still be added (a translation only needs a new manuscript).

### Reverse converter (HTML → MD)

New module `scripts/html_to_md.py`: converts a generated post page back to the
manuscript markdown dialect (`#`/`##`/`###` headings, italic subtitle, `>` pull quotes
with attribution, tables, `-` lists, `**`/`*` inline, `[text](url)` links, byline).
Used by the backfill CLI and by the app's `/api/html-to-md` endpoint (rich-text mode).
It only ever needs to handle markup that `build_post` itself emits.

## 1. Author-page automation

In `build_post` (write path): after writing the page and index, check whether
`journalistennetzwerk/<author-id>.html` exists for the post's author. If it does, insert
a new `.post-card` (link, cover, date, title, excerpt — same fields as the index card)
at the top of the „Beiträge auf ZWISCHENWELTEN" grid, using the same marker-based
insertion technique as `add_card`. The author page is added to the returned `files` list
so the app's git flow commits it.

Rules carried over from the skill: translations do **not** get a card (only originals);
newest first. Because this lives in `build_post`, CLI and app behave identically, and
the manual step in `SKILL.md` becomes automatic (the skill doc is updated to say
"verify" instead of "do by hand").

## 2. Post list + editing

The app gains a start screen with two paths:

- **„Neuer Beitrag"** — the existing 4-step wizard, unchanged.
- **„Beiträge verwalten"** — a list built from `posts.json`: newest first, translations
  grouped under their original, each row showing cover thumbnail, title, language badge,
  date, author. Row actions: **Bearbeiten** (hidden/disabled when `locked`),
  **Übersetzung hinzufügen**.

**Bearbeiten** loads the stored manuscript and registry metadata into the same Angaben
form. The current cover is shown from the repo and can be replaced. Publishing runs
`build_post` in update mode:

- Rewrite `aktuelles/<slug>.html`.
- Replace the post's card in the index (matched by slug) instead of prepending.
- Replace the post's card on the author page, if present.
- Replace the cover file only when a new one was uploaded.
- Rewrite the manuscript and registry entry.
- Commit message: `content: update <Titel>`.

The slug is fixed in edit mode — renaming a published URL is out of scope. Language is
also fixed (changing it would be a different post).

## 3. Add translation

From a post's row: pick a target language (only languages the post does not yet have,
from the `de en tr ru uk ar ku fa` set), then supply the translated manuscript by file
drop or by typing in the editor. Pre-filled and derived values:

- Slug: `<original-slug>-<lang>`, read-only.
- Cover: inherited from the original by default, replaceable with a new upload.
- Author: pre-filled from the original (the manuscript byline, if present, wins after
  the usual matcher run).
- Registry entry gets `original_slug`.

Behaviour on the site (unchanged from today): the translation gets its own index card
and language filter chip; it does not appear on the author page.

## 4. Rich-text editing

The body field in the Angaben step becomes two tabs: **Markdown | Rich Text**.

- Rich Text is a dependency-free `contenteditable` editor. The toolbar offers exactly
  what the converter supports and nothing more: H2, H3, bold, italic, link, bulleted
  list, pull quote. Existing tables render and their cell text is editable, but there is
  no "insert table" button — new tables are written in the Markdown tab.
- Conversion between the tabs is done **server-side**: `/api/md-to-html` (the existing
  `md_to_body`/`parse_md` path) and `/api/html-to-md` (the reverse converter). No
  JavaScript re-implementation of the converter exists, so the single-converter
  guarantee holds. Tab switches round-trip through these endpoints.
- The fidelity gate at preview/publish remains the final backstop; a serializer bug can
  therefore block a publish but never corrupt one.

## 5. Author creation in the app

Trigger points: the Angaben step when the matcher reports an unknown byline (replacing
today's bare `new_author` checkbox), plus an explicit „Neuer Autor" action.

Form: canonical name (required), role (required — shown on posts), per-language name
variants (optional, default = canonical), aliases (optional). Submitting writes the
entry to `assets/blog/authors.json` with a slugified `id`, after a final
`match_author` check refuses names that resolve to an existing author.

Optional **„Autorenseite anlegen"** checkbox: when ticked, a photo upload
(→ `assets/autoren/<id>.png`) and a short bio become required, and the app generates
`journalistennetzwerk/<id>.html` from the `suleyman-bag.html` template (name, role, bio,
photo substituted; Beiträge grid empty — feature 1 fills it on first publish). When not
ticked, only the registry entry is created (pages stay opt-in, per the skill).

## Error handling

- The git flow (pull --rebase → add → commit → push, with retry-push) is unchanged;
  edit/translation publishes go through the same path with the same staged error
  reporting.
- Update mode refuses to run if the page, manuscript, or registry entry for the slug is
  missing (surfaced as a normal `PublishError` in the UI).
- `/api/html-to-md` failures surface in the tab switch and keep the user in their
  current tab with content intact; nothing is lost.
- Backfill is idempotent and writes nothing when verification fails for a post (that
  post is only marked `locked`).

## Testing

Extend `scripts/tests`:

- Round-trip tests: for every existing post, HTML → MD → `build_post` → fidelity vs the
  committed page.
- Unit tests: author-page card insertion (new + update), index card replacement in
  update mode, registry maintenance, translation slug/cover inheritance, author
  creation (duplicate refusal, page generation).
- API tests for the new endpoints (`/api/posts`, `/api/edit-load`, `/api/md-to-html`,
  `/api/html-to-md`, `/api/new-author`).

## Build order

1. Foundation: reverse converter, manuscript store, registry, backfill.
2. Author-page automation in `build_post` (+ skill doc update).
3. Post list + edit mode.
4. Add translation.
5. Author creation.
6. Rich-text editor (most isolated, riskiest UI work last).
