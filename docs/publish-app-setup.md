# Setting up the publish app

This is for the person who publishes posts to the site. You do it once, it takes
about ten minutes, and afterwards publishing is a double-click.

You do not need to know git. You do need a GitHub account that has been given
access to the site's repository.

## What you are installing

The publish app is not a program you download. It lives *inside* the website's
own files: you make a copy of the site on your computer, and the app runs from
inside that copy. That is why there is nothing to send you by email — you fetch
everything in one command below.

This matters more than it sounds. The app reads and writes the site's real files
(articles, cover images, the author list) and then pushes them to GitHub, which
publishes them. Loose script files on their own cannot do any of that.

## 1. Check you have Python

Open **Terminal** (press ⌘-Space, type "Terminal", hit return) and run:

```
python3 -V
```

If you see a version number like `Python 3.13.0`, you are set. If you get an
error, install Python from [python.org/downloads](https://www.python.org/downloads/)
and run it again.

## 2. Install the GitHub command line tool

This is what lets your computer prove to GitHub that the posts are coming from
you. Install [GitHub CLI](https://cli.github.com/), then run:

```
gh auth login
```

Answer the prompts: **GitHub.com** → **HTTPS** → **Yes** (authenticate git) →
**Login with a web browser**. It shows you a short code, opens your browser, you
approve, and you are done.

You only ever do this once. The app itself never asks for a password and never
stores one — it borrows the permission you just granted here.

> If you prefer not to install the GitHub CLI, you can skip it. The first time
> you publish, git will ask for a username and password in the Terminal. The
> "password" must be a **Personal Access Token** with `repo` permission, created
> at github.com under Settings → Developer settings — *not* your account
> password, which GitHub no longer accepts.

## 3. Download the site

Pick where you want it — your home folder is fine — and run:

```
git clone https://github.com/Zwischenwelten-Berlin/Zwischenwelten.git
```

You now have a folder called `Zwischenwelten`. Keep it. Everything happens here,
and this is the folder you open whenever you publish.

## 4. Only if you get manuscripts as Word files

```
python3 -m pip install mammoth
```

Skip this if authors send you Markdown or Google Docs. If you skip it and later
open a `.docx`, the app tells you in plain German exactly what to run.

## 5. Start it

Open the `Zwischenwelten` folder in Finder and **double-click
`Publish-App.command`**. A Terminal window opens and your browser goes to
`http://localhost:8765`.

That Terminal window is the app. Leave it open while you work; closing it stops
the app. To publish again another day, double-click the same file.

> **On Windows?** There is no double-click file. Open a terminal in the folder
> and run `python3 scripts/publish_app.py` instead. Everything after that is
> identical.

## Publishing a post

Drop in the manuscript and the cover image, check the metadata the app filled in
for you, preview the finished page, and publish. The app writes the files,
commits them, and pushes to GitHub. The live site updates within a minute or two
at [zwischenwelten.berlin](https://zwischenwelten.berlin).

Before it writes anything, the app compares the finished page against the
manuscript word by word and refuses to publish if a single word differs. If it
stops you, the manuscript is the thing to fix — not the page.

## The one rule when two people publish

**Do not publish at the same moment as the other editor.**

Every publish updates a shared index of all posts. The app pulls in the other
person's work automatically before it writes, so taking turns is completely
safe — minutes apart is plenty. But two publishes genuinely overlapping will
collide on that index, and the app will stop and tell you it needs help in the
Terminal. A quick message to the other person beforehand avoids it entirely.

## When something goes wrong

The app shows you the exact commands it ran and what came back. Two common ones:

- **"Für Word-Dateien fehlt das Paket 'mammoth'"** — step 4 above.
- **A push fails with a permission error** — your GitHub access has lapsed or was
  never granted. Run `gh auth login` again; if it still fails, ask the repository
  owner to confirm you have write access.

If a publish stops midway and tells you the repository needs attention in the
Terminal, do not re-run it repeatedly. Send the message it printed to whoever
maintains the site — it is a git state that needs untangling once, not a
mistake you made.

## Sending guides to authors

See [README.md](README.md) for which manuscript guide to send an author,
depending on whether they write in Word, Google Docs, or Markdown. A manuscript
that follows the guide publishes in about two minutes; one that does not can
take an hour to rebuild by hand.
