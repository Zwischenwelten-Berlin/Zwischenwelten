# How to submit a manuscript for the ZWISCHENWELTEN blog

Read this once. It takes five minutes and it is the difference between a post that
goes live in two minutes and one that takes an hour of manual reconstruction.

> **Writing in Google Docs or Word?** Read
> [manuscript-guide-google-docs.md](manuscript-guide-google-docs.md) instead — you
> don't need any of the Markdown below, just the Styles menu.

## Why the format matters

The publishing tool converts your text into the site's house style automatically.
It is deliberately strict about one thing: **it never changes your wording.** It
compares the finished web page against your manuscript word by word and refuses to
publish if a single word differs.

What it *cannot* do is guess your intent. If your file is one flat wall of
paragraphs, nothing in it says "this line is a heading", "this paragraph is a pull
quote", "these six lines are a list". Someone then has to decide that by hand for
every paragraph — and every one of those decisions is a chance to get your article
wrong.

**A structured manuscript publishes itself. A flat one has to be rebuilt.**

## The fastest path

Copy `manuscript-template.md` from this folder, replace the text, send it. If you
do that, you can stop reading here.

## The seven markers

Everything below is plain text you type directly into the file. No special software.

| You want | You type |
|---|---|
| The headline | `# Your headline` — exactly one, at the very top |
| The standfirst / subtitle | `## Your subtitle` — the line right after the headline |
| A section heading | `## Section heading` |
| A pull quote | `> The quoted sentence.` |
| …its attribution | a `>` blank line, then `> **Name** — Role` |
| A bullet list | `- one item per line` |
| Bold / italic | `**bold**`, `*italic*` |

A worked pull quote — note the empty `>` line between quote and speaker:

```
> "Social cohesion doesn't happen on its own. It needs journalism that listens."
>
> **Süleyman Bağ** — Project lead, Zwischenwelten
```

Links and e-mail addresses can be written plainly (`name@example.org`) — they are
turned into links for you.

## Two mistakes that cost the most time

**1. A sentence split across two paragraphs.** Word exports often break a sentence
in half with a blank line in the middle:

```
…These are the questions

that lie at the heart of the award.
```

Those are now two separate paragraphs and the page renders them as such. Keep each
sentence in one block.

**2. Everything turned into a bullet list.** Exports sometimes prefix every line in
a region with `-`, including the sentence introducing the list. Only the actual list
items should have `-`.

## If you write in Word

Do not just save as `.txt` — the structure is lost. Instead:

1. Use Word's real **Heading 1 / Heading 2** styles for your headlines. Do *not*
   fake a heading with bold text in a bigger font — that carries no information.
2. Use Word's real bullet-list button for lists.
3. Convert with: `pandoc yourfile.docx -t markdown -o yourfile.md`

If you used the real styles, the conversion produces correct `#`, `##` and `-`
markers on its own and you are done.

## What we cannot fix for you

Because the tool guarantees your wording is published untouched, **it also publishes
your typos untouched.** Nobody downstream will silently correct a misspelling, a
wrong date or a wrong e-mail address — changing them requires going back to you.

So before you send, check the facts yourself:

- **The contact address** is `Medienpreis@zwischenwelten.berlin`. Older drafts
  circulate with `zwischenwelten@kubik-ev.de` — that address is retired. This is
  the single most common error and it sends applicants to a dead mailbox.
- Deadlines and dates match the current call for entries.
- Names are spelled the way that person spells them.

## Send this alongside the file

Paste this into your e-mail so nobody has to ask you six follow-up questions:

```
Language:      Persian
Publish date:  2026-07-16
Author:        Süleyman Bağ
Translation of: medienpreis-2026   (or "new post")
Section label: Medienpreis          (optional, shown above the headline)
Cover image:   attached / reuse the one from the German version
```

For a translation of an existing post, say so — the date, cover image and section
label are then simply reused from the original, and nothing has to be guessed.

## Checklist before you send

- [ ] Exactly one `#` headline at the top
- [ ] A `##` subtitle directly beneath it
- [ ] Every section heading marked `##`
- [ ] Every pull quote marked `>`, with its speaker after a blank `>` line
- [ ] Lists marked `-`, and the sentence introducing them *not* marked
- [ ] No sentence broken across two paragraphs
- [ ] Contact address is `Medienpreis@zwischenwelten.berlin`
- [ ] Proofread — your wording is published exactly as written
- [ ] Metadata block pasted into the e-mail
