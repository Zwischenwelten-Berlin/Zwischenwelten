# Writing your article in Google Docs or Word

You do not need to learn Markdown, install anything, or change how you write. You
need to do exactly one thing differently:

> **Use the Styles menu to mark your headings and lists — never bold text, bigger
> fonts, or manual dashes.**

That single habit is what lets your article be published in two minutes instead of
being rebuilt paragraph by paragraph.

## Why

When your document is exported, the visual formatting is thrown away. Font size,
colour, bold, centring — all gone. What survives is only what you marked
*structurally*.

So these two look identical on your screen:

| What you did | What survives export |
|---|---|
| Typed the heading, made it bold and 18pt | a normal paragraph — the heading is lost |
| Typed the heading, applied **Heading 2** | a real heading ✅ |

If you format by eye, your article arrives as one flat wall of text and every
heading, quote and list has to be guessed back by hand.

---

# Part 1 — Google Docs

## Step 1: Mark your structure as you write

Use the style dropdown in the toolbar (it normally reads **Normal text**), or the
menu **Format → Paragraph styles**.

| Part of your article | Style to apply |
|---|---|
| The headline, at the very top | **Heading 1** — use it exactly once |
| The subtitle, directly beneath it | **Heading 2** |
| Each section heading | **Heading 2** |
| Ordinary paragraphs | **Normal text** |

For lists, use the real **bulleted-list button** in the toolbar. Do not type `-` or
`•` by hand at the start of lines.

## Step 2: Export as Markdown

**File → Download → Markdown (.md)**

That's it. Send us that `.md` file. Headings, lists, bold and italic all come
through correctly.

If you don't see a Markdown option, download as **Microsoft Word (.docx)** instead
and send that — just tell us, so we know to convert it.

## Step 3: The 30-second check

Open the downloaded `.md` file (double-click; it opens in any text editor). You
should see `#` and `##` in front of your headings and `-` in front of list items:

```
# Your headline

## Your subtitle

Your first paragraph...

## First section heading
```

**If you see a wall of plain text with no `#` anywhere, the styles weren't applied.**
Go back to Step 1 — that check takes seconds and saves an hour.

---

# Part 2 — Microsoft Word

Identical idea. In the **Home** tab, use the Styles gallery:

- **Heading 1** for the headline (once)
- **Heading 2** for the subtitle and every section heading
- **Quote** for pull quotes — Word has this style and it survives export
- The real bulleted-list button for lists

Then either save as `.docx` and send it, or paste the whole article into a Google
Doc and follow Part 1 to get a clean Markdown file.

---

## Pull quotes need one extra moment

Quotes are the one thing that often doesn't survive cleanly. Whichever tool you use,
put the speaker on **their own line immediately after** the quote, in this form:

```
"Social cohesion doesn't happen on its own. It needs journalism that listens."

Süleyman Bağ — Project lead, Zwischenwelten
```

Name first, then a dash, then the role. If you can apply Word's **Quote** style to
the quoted sentence, even better.

## Things that never survive — don't spend time on them

Fonts, colours, font sizes, centring, page breaks, text boxes, headers and footers,
tables of contents, comments and tracked changes. The website applies its own house
design to everything.

**Images:** send them as separate attachments, not pasted into the document. Pasted
images come out at screen resolution and are usually too small to print on the page.

## Two habits that quietly cause damage

**1. Don't use Shift+Enter or empty lines to create spacing.** A line break in the
middle of a sentence splits it into two paragraphs, and the page will publish it
split in half. Let the text flow; spacing is applied by the site.

**2. Don't type your own list dashes.** Manually typed `-` at the start of every
line in a section — including the sentence introducing the list — is a common export
artefact and makes the intro sentence render as a bullet.

## Before you send

- [ ] Headline uses **Heading 1**, once, at the top
- [ ] Subtitle and all section headings use **Heading 2**
- [ ] Lists made with the list button, not typed dashes
- [ ] Speaker line after each quote, as `Name — Role`
- [ ] Images attached separately
- [ ] Downloaded as Markdown and eyeballed for `#` and `-`
- [ ] Proofread — **your wording is published exactly as written, typos included**
- [ ] Contact address in the text is `Medienpreis@zwischenwelten.berlin`
      (the older `zwischenwelten@kubik-ev.de` is retired)
- [ ] Metadata pasted into your e-mail:

```
Language:       e.g. Persian
Publish date:   YYYY-MM-DD
Author:         Full name, spelled as that person spells it
Translation of: slug of the original post, or "new post"
Section label:  e.g. Medienpreis   (optional)
Cover image:    attached, or "reuse the original's"
```

---

## For the coordinator: converting a `.docx`

If an author sends Word rather than Markdown:

```bash
pandoc article.docx -t markdown --wrap=none --extract-media=. -o article.md
```

Then open `article.md` and confirm `#`, `##` and `-` are present. If the author used
real styles they will be. If the file is flat, it's faster to ask the author to
re-apply styles than to reconstruct the structure by hand — and it's the only way to
be sure the structure matches what they intended.
