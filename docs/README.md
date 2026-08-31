# Documentation

## For whoever publishes the posts

[publish-app-setup.md](publish-app-setup.md) — one-time setup of the publish app
on a new computer: Python, GitHub access, cloning the site, starting the app.
Send this to a new editor before anything else.

## For authors and translators

Send whichever applies to the person writing the article:

| If they write in… | Send them |
|---|---|
| Google Docs or Microsoft Word | [manuscript-guide-google-docs.md](manuscript-guide-google-docs.md) |
| Markdown, or any plain-text editor | [manuscript-guide.md](manuscript-guide.md) + [manuscript-template.md](manuscript-template.md) |

Both guides end with the same checklist and ask for the same metadata block, so it
does not matter which one an author follows.

## Why these exist

Posts are published with `scripts/publish_post.py`, which converts a manuscript into
the site's house style and refuses to publish if the finished page differs from the
manuscript by even one word. It cannot infer structure that isn't marked: a flat
document has to be rebuilt heading by heading, which is slow and risks
misrepresenting the author.

A manuscript that arrives with its headings, quotes and lists marked publishes
almost immediately. That is the entire purpose of these two guides.

## House facts that must be right in every post

- Contact address: **Medienpreis@zwischenwelten.berlin**
  (the older `zwischenwelten@kubik-ev.de` is retired)
- Translations of an existing post reuse the original's cover image, publication
  date and section label — they are not re-chosen per language
- Author names are matched against `assets/blog/authors.json`; the same person must
  never get a second record
