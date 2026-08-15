---
name: publish
description: Use when the user wants to publish a new blog post to /aktuelles from a markdown manuscript and a cover image, or says /publish, "yeni blog yazısı", "bu md'yi yayınla", "publish this post".
---

# Publish a blog post

`scripts/publish_post.py` does the whole mechanical conversion: markdown → house-styled
HTML, cover image, overview card, filter chip, author lookup. It refuses to write
anything unless the generated page contains exactly the same words as the manuscript.

Your job is the judgment the script cannot make: collecting the inputs, confirming the
author, and reviewing the result before it goes live.

## Inputs to collect

The user supplies a manuscript and an image. Everything below must be settled before
running the script — ask for whatever is missing, in one message rather than one at a time.

| Input | How to settle it |
|---|---|
| `--md` | Path the user gave. |
| `--image` | Path the user gave. |
| `--lang` | Read the manuscript and infer it; state your inference and let the user correct it. One of `de en tr ru uk ar ku fa`. |
| `--date` | Publication date. Ask; do not assume today. |
| `--author` | See below. |
| `--slug` | Propose one from the title. Translations of an existing post reuse its slug plus a language suffix, e.g. `medienpreis-2026-tr`. |
| `--tag` | Optional label above the headline, e.g. `Medienpreis`. Ask if the topic has an obvious section. |
| `--highlight` | Optional phrase in the title to print in the accent colour, matching the other posts. Propose one. |

## Author matching

**Never create a second record for a person who already has one.** The registry is
`assets/blog/authors.json`; the script matches across diacritics and Cyrillic, so
"Сулейман Баг" resolves to the same person as "Süleyman Bağ" and publishes under the
right spelling for the post's language.

- The script reads a byline (`Author:`, `Yazar:`, `Автор:` …) from the manuscript. If
  there is none, ask the user who the author is and pass `--author`.
- A match ≥ 85% is used automatically and reported.
- No match aborts the run. Then either the name is a variant of someone already in the
  registry — re-run with `--author` using their registered spelling — or it is genuinely
  a new person, which needs `--new-author` **and** the user's confirmation that they are
  new. Ask before adding; do not guess.

## Run it

```bash
python3 scripts/publish_post.py --md POST.md --image COVER.jpg \
  --lang tr --date 2026-08-01 --slug my-post --tag "Medienpreis" --dry-run
```

Always `--dry-run` first. It reports the detected title, subtitle, author match and the
fidelity check without touching the repository. Re-run without `--dry-run` when the
report looks right.

To edit an already-published post, add `--update` (and `--slug` of the existing post);
`--image` becomes optional and, if omitted, the existing cover is kept.

## Author pages

Authors can have a profile page at `journalistennetzwerk/<author-id>.html`, where
`<author-id>` is their `id` in `assets/blog/authors.json` (e.g.
`journalistennetzwerk/suleyman-bag.html`). **`build_post` handles this automatically**:
if the author has such a page, it adds the new post to the „Beiträge auf ZWISCHENWELTEN"
grid — newest first — and reports the touched file in `files`/`author_page`. Translations
of a post do not get their own card; only the original does. Your job is to verify, not
to edit by hand: open the author page and confirm the new post appears at the top of the
Beiträge grid.

If the author has no page yet, nothing happens (pages are created per author on request;
`journalistennetzwerk/suleyman-bag.html` is the template to copy — photo goes to
`assets/autoren/<author-id>.png`).

## Verify before publishing

1. Serve the site (`python3 dev-server.py`) and open `/aktuelles/<slug>` **in a browser**,
   plus `/aktuelles/` to check the new card. A 200 response is not verification; look at
   the page.
2. Confirm the post carries the house style — cover, prose card, pull quotes, footer —
   and that the overview card shows the right language badge.
3. If the author has a page under `/journalistennetzwerk/`, open it and confirm the new
   post appears in their Beiträge list.
4. Show the user what you published, then ask before committing and pushing. Publishing
   is outward-facing; do not push on your own initiative.

## Rules that are not negotiable

**The manuscript's wording is untouchable.** Do not reword, reorder, retitle, translate,
summarise, fix typos, add a heading, or add a label the manuscript does not contain.
Markdown structure maps to house styling — that is the only thing allowed to change.

If the fidelity check fails, the script prints the differing words and writes nothing.
Fix the converter or ask the user about the manuscript. **Never pass `--allow-drift`-style
workarounds, never hand-edit the generated page to make it "look right", and never
disable the check.** A post that differs from its source is a defect, not a style choice.

Design elements from older posts (prize podiums, callout boxes) were hand-built. Do not
recreate them by hand for new posts: a list in the manuscript becomes a list.

## Browser-App

`python3 scripts/publish_app.py` opens a self-service GUI at `http://localhost:8765`
for editors who prefer dropping a manuscript and cover in a browser over the CLI. It
runs through the same `manuscript_import`/`publish_post.build_post` converter and
fidelity gate described above, so it can never produce a different result than this
skill.

Beyond a fresh "Neuer Beitrag", the app also covers editing, translating, and author
setup:

- **Beiträge verwalten** lists every published post, with translations grouped under
  their original. Every publish stores the manuscript at
  `assets/blog/manuscripts/<slug>.md` and records the post in
  `assets/blog/posts.json`; the list and the edit flow read from that registry, not
  by scraping HTML. The CLI equivalent of editing is `python3 scripts/publish_post.py
  --update` (image optional when updating — it keeps the existing cover unless a new
  one is given).
- **Bearbeiten** loads a post's stored manuscript back into the editor, either as
  Markdown or on a Rich-Text tab (backed by `/api/md-to-html` and `/api/html-to-md`),
  for a wording tweak followed by preview and re-publish. Posts published before this
  registry existed, or otherwise missing a recoverable manuscript, are **locked**: the
  app refuses to edit them (the underlying HTML would drift from any manuscript it
  regenerated), but they can still receive translations.
- **Übersetzung +** starts a new-language version of an existing post, slug forced to
  `<original-slug>-<lang>`, same fidelity gate as any other publish.
- **Neuer Autor** registers a person in `assets/blog/authors.json` from the app and,
  optionally, generates their `journalistennetzwerk/<author-id>.html` page from
  `scripts/author_page_template.html` — the same page `build_post` will start adding
  cards to automatically once it exists.

## Common mistakes

| Mistake | What to do instead |
|---|---|
| Adding a heading to a callout box because it "looks empty" | Leave it. Extra words are a fidelity defect. |
| Registering "Сулейман Баг" as a new author | Let the matcher resolve it; it is the same person. |
| Publishing with today's date without asking | Ask for the publication date. |
| Committing straight after the script succeeds | Show the rendered page to the user and ask first. |
| Trusting a 200 status as proof | Open the page and look at it. |
