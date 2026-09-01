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

You can also skip this step: if Python is missing when you first start the app,
it says so, offers to install it or to open the download page for you, and tells
you to double-click again afterwards. The same goes for the GitHub tool in the
next step. The one thing you do need up front is `git`, because step 3 uses it —
and if it is missing, the command in step 3 will offer to install it.

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

If you have not done this by the time you first start the app, it notices and
offers to run the login for you.

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

**Not the green "Code → Download ZIP" button on GitHub.** A ZIP has the files
but no connection to GitHub, and the app cannot publish from it — it would start
and look completely normal, then fail at the very end of your first post. The
app checks for this and stops instead, offering to download the site properly.
Use the command above and there is nothing to think about.

## 4. Start it

Open the `Zwischenwelten` folder in Finder and **double-click
`Publish-App.command`**. A Terminal window opens and your browser goes to
`http://localhost:8765`.

The very first start takes a minute: it sets up its own Python environment
inside the folder and installs the one package it needs (Word import). It says
so while it works. Every start after that is immediate.

If macOS refuses to open the file the first time ("unidentified developer"),
right-click it → **Open** → **Open** again in the dialog. Once only.

That Terminal window is the app. Leave it open while you work; closing it stops
the app. To publish again another day, double-click the same file.

> **On Windows?** There is no double-click file. Open a terminal in the folder
> and run `python3 scripts/publish_app.py` instead. Everything after that is
> identical.

## Updates

You never install an update. Every time you double-click
`Publish-App.command`, it fetches the current version of the site and the app
from GitHub before it starts, and installs any new package that version needs.
If something came down, it says `Update eingespielt.` in the Terminal.

The one thing worth knowing: the app that is *already running* keeps running the
version it started with. So if you have been told the app was improved, quit it
(close the Terminal window) and double-click again — that is the whole update
procedure.

If you are offline it says so and starts the version you already have.

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

- **"Für Word-Dateien fehlt das Paket 'mammoth'"** — the package install did not
  finish, usually because the first start had no internet. Quit the app and
  double-click `Publish-App.command` again; it retries by itself.
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
