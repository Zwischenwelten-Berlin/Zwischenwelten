#!/usr/bin/env python3
"""Browser publishing app for the ZWISCHENWELTEN blog.

    python3 scripts/publish_app.py

Opens http://localhost:8765 — drop a manuscript (.md/.docx/.doc) and a cover
image, review the pre-filled metadata, preview the exact page, publish to
GitHub Pages. All rendering goes through publish_post.build_post, so the app
can never produce different HTML than the CLI, and the fidelity gate always
runs before anything is written.

Beyond a fresh post, it also lists/edits/translates existing posts (backed by
the assets/blog/manuscripts/ + posts.json registry, with a Markdown|Rich-Text
tab pair for edits) and registers new authors with optional page generation.
"""

import base64
import binascii
import glob
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
# mode is one of "new" (fresh manuscript), "edit" (editing an existing post,
# slug/lang immutable), or "translate" (new-language version of an original,
# slug forced to f"{translate_of}-{lang}").
# cover_is_repo marks that cover_path points straight at a post's existing
# repo cover file (set by api_edit_load/api_translation_init when they load
# it), as opposed to a freshly uploaded temp file — see api_preview, which
# must not pass that path back into build_post as image_path in edit mode
# (copying the repo cover onto itself raises shutil.SameFileError).
SESSION = {"cover_path": None, "cover_rel": None, "preview": None, "publish_args": None,
           "mode": "new", "translate_of": None, "edit_slug": None, "cover_is_repo": False}


# Origins allowed to hit the state-changing POST endpoints. Guards against a
# cross-origin page silently triggering a real commit+push (text/plain POSTs
# avoid CORS preflight, so the browser won't block them on its own).
ALLOWED_ORIGINS = {"http://localhost:8765", "http://127.0.0.1:8765"}


def _origin_allowed(headers):
    """True unless `headers` carries an Origin that isn't ours.

    No Origin header at all (curl, the test harness, same-process calls) is
    allowed — only a *present but foreign* Origin is rejected.
    """
    origin = headers.get("Origin")
    return not origin or origin in ALLOWED_ORIGINS


def _cover_path_for(slug):
    """Absolute path to slug's cover image in the repo, or None if missing.
    Resolves publish_post.IMG_DIR at call time (not import time) so tests
    that monkeypatch it see the patched value."""
    matches = glob.glob(os.path.join(publish_post.IMG_DIR, f"{slug}-cover.*"))
    return matches[0] if matches else None


def run_git(*args):
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip()


def current_branch():
    _, out = run_git("rev-parse", "--abbrev-ref", "HEAD")
    return out


def _rebase_in_progress():
    """Whether a `git rebase` is actually mid-flight (rebase-merge/-apply
    state dirs exist under .git). Most `git pull --rebase` failures (dirty
    working tree, offline, auth) never get far enough to create these —
    they fail before a rebase starts."""
    for name in ("rebase-merge", "rebase-apply"):
        code, path = run_git("rev-parse", "--git-path", name)
        if code == 0 and path and os.path.exists(os.path.join(ROOT, path)):
            return True
    return False


_PULL_WARN_MARK = "\x00pull-warn\x00"


def _pull(log):
    """`git pull --rebase --autostash`, appending the command transcript to
    `log` (a list the caller owns). Returns True on success.

    `--autostash` (rather than the pre-refactor plain `--rebase`) matters
    because both git_flow's callers write their files to disk *before*
    pulling — `git add` needs the files to exist — so the working tree is
    essentially never clean when this runs. Autostash makes that safe: it
    stashes the just-written files, rebases, and reapplies them, so a
    plain "nothing to pull" run is still a no-op and a real upstream
    change still rebases cleanly on top of the stashed work.

    On failure, attempts to recover a stuck rebase (`_abort_stuck_rebase`);
    if *that* also fails, its German warning text is appended to `log`
    behind a private marker that `split_pull_warning` extracts, so a
    caller can fold it into its user-facing "pull" error message without
    it also polluting the git_output transcript shown verbatim in the UI.
    """
    code, out = run_git("pull", "--rebase", "--autostash")
    log.append(f"$ git pull --rebase --autostash\n{out}")
    if code != 0:
        warn = _abort_stuck_rebase(log)
        if warn:
            log.append(f"{_PULL_WARN_MARK}{warn}")
        return False
    return True


def split_pull_warning(log):
    """Split a _pull/git_flow log back into (git_output, warning_suffix).
    warning_suffix is "" unless _abort_stuck_rebase escalated; see _pull."""
    if _PULL_WARN_MARK in log:
        base, warn = log.split(_PULL_WARN_MARK, 1)
        return base.rstrip("\n"), warn
    return log, ""


def _add_commit_push(files, msg, log):
    """`git add`, `commit`, `push` `files` under `msg`, appending each
    command's transcript to `log`. Returns the failing stage
    ("add"/"commit"/"push"), or "" on success."""
    code, out = run_git("add", "--", *files)
    log.append(f"$ git add {' '.join(files)}\n{out}")
    if code != 0:
        return "add"

    code, out = run_git("commit", "-m", msg)
    log.append(f"$ git commit -m {msg!r}\n{out}")
    if code != 0:
        return "commit"

    code, out = run_git("push", "origin", "HEAD")
    log.append(f"$ git push origin HEAD\n{out}")
    if code != 0:
        return "push"

    return ""


def git_flow(files, msg):
    """Shared pull/add/commit/push sequence, built from `_pull` and
    `_add_commit_push`. Returns (ok, stage, log) where stage is "" on
    success and one of "pull"/"add"/"commit"/"push" on failure; log is the
    joined command transcript. Used directly by api_new_author, whose
    files are written to disk before this is called.

    Unlike api_publish (which has its own "pull" error text to fold
    `split_pull_warning`'s suffix into, and so keeps the sentinel-bearing
    raw log around just long enough to split it), git_flow has no separate
    error-text field — its `log` *is* the whole story shown to the caller
    — so the sentinel is resolved into plain, human-readable text here and
    never returned to a caller.

    api_publish calls `_pull`/`_add_commit_push` itself instead of this
    function — it needs `build_post`'s write to happen *between* the pull
    and the add, to keep its pre-refactor observable behaviour (including
    exact git_output content on a `build_post` failure) byte-for-byte
    unchanged. See its docstring for the mapping.
    """
    log = []
    if not _pull(log):
        out, warn = split_pull_warning("\n\n".join(log))
        if warn:
            out += "\n\n" + warn.strip()
        return False, "pull", out
    stage = _add_commit_push(files, msg, log)
    if stage:
        return False, stage, "\n\n".join(log)
    return True, "", "\n\n".join(log)


def _abort_stuck_rebase(log):
    """Called after a failed `git pull --rebase`. Only runs `git rebase
    --abort` (and only ever escalates to the German "repo may be stuck
    mid-rebase" warning) when a rebase is actually in progress — otherwise
    the abort itself fails with "No rebase in progress?" and the scary
    warning misfires for ordinary pull failures. Returns the warning
    suffix to append to the error message, or "" if there's nothing to
    report.
    """
    if not _rebase_in_progress():
        return ""
    abort_code, abort_out = run_git("rebase", "--abort")
    log.append(f"$ git rebase --abort\n{abort_out}")
    if abort_code != 0 and "No rebase in progress" not in abort_out:
        return (" Außerdem konnte der Rebase nicht automatisch abgebrochen werden — "
                "das Repository steckt möglicherweise noch mitten in einem Rebase und "
                "braucht manuelle Aufmerksamkeit im Terminal (git status, git rebase --abort).")
    return ""


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
        elif path == "/api/posts":
            try:
                self.api_posts()
            except (ManuscriptError, PublishError) as e:
                self.send_json({"ok": False, "error": str(e)})
            except Exception as e:                  # noqa: BLE001 — show, don't crash
                self.send_json({"ok": False, "error": f"{type(e).__name__}: {e}"}, status=500)
        elif path == "/preview/page":
            if not SESSION["preview"]:
                self.send_error(404, "No preview yet")
            else:
                self.send_html(SESSION["preview"]["page_html"])
        elif (SESSION["cover_rel"] and path == SESSION["cover_rel"] and SESSION["cover_path"]
              and os.path.exists(SESSION["cover_path"])):
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
        if not _origin_allowed(self.headers):
            self.send_json({"ok": False,
                            "error": "Anfrage von einem fremden Origin wurde abgelehnt."}, status=403)
            return
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
            elif self.path == "/api/author-check":
                self.api_author_check(body)
            elif self.path == "/api/new-author":
                self.api_new_author(body)
            elif self.path == "/api/posts":
                self.api_posts(body)
            elif self.path == "/api/edit-load":
                self.api_edit_load(body)
            elif self.path == "/api/translation-init":
                self.api_translation_init(body)
            elif self.path == "/api/replace-cover":
                self.api_replace_cover(body)
            elif self.path == "/api/md-to-html":
                self.api_md_to_html(body)
            elif self.path == "/api/html-to-md":
                self.api_html_to_md(body)
            else:
                self.send_error(404)
        except (ManuscriptError, PublishError) as e:
            self.send_json({"ok": False, "error": str(e)})
        except Exception as e:                     # noqa: BLE001 — show, don't crash
            self.send_json({"ok": False, "error": f"{type(e).__name__}: {e}"}, status=500)

    def api_convert(self, body):
        # A new manuscript invalidates any prior preview/publish state — never
        # let a stale draft be published after a fresh conversion. A fresh
        # (non-translate) convert also invalidates any prior edit/translate
        # session; a translation's manuscript, however, arrives via convert
        # too, so translate mode (and its original's cover) must survive —
        # but only when the client explicitly asserts it's still in translate
        # mode (body["translate"]). Without that assertion, an abandoned or
        # already-published translation must not leak into the next "Neuer
        # Beitrag": the client only ever sends the flag while
        # state.mode === "translate", so its absence means the session's
        # stale mode is exactly that — stale — and gets reset here.
        SESSION["preview"] = None
        SESSION["publish_args"] = None
        if not (SESSION["mode"] == "translate" and body.get("translate")):
            SESSION.update(mode="new", translate_of=None, edit_slug=None, cover_is_repo=False)
        md, warnings = load_manuscript(body["manuscript_name"],
                                       base64.b64decode(body["manuscript_b64"]))
        # cover -> temp file, remember the future URL for the preview. In
        # translate mode the cover is optional — SESSION["cover_path"]
        # already holds the original post's cover (set by
        # api_translation_init) unless a new one is uploaded here.
        if not (SESSION["mode"] == "translate" and not body.get("cover_b64")):
            cover_ext = os.path.splitext(body["cover_name"])[1].lower() or ".jpg"
            if cover_ext not in (".jpg", ".jpeg", ".png"):
                raise ManuscriptError(f"Cover muss .jpg oder .png sein, nicht {cover_ext}.")
            fd, SESSION["cover_path"] = tempfile.mkstemp(suffix=cover_ext)
            with os.fdopen(fd, "wb") as fh:
                fh.write(base64.b64decode(body["cover_b64"]))
            SESSION["cover_is_repo"] = False

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

    def api_author_check(self, body):
        # Read-only lookup the UI calls as the editor types/leaves the author
        # field — reuses the same fuzzy matcher build_post uses, so the app
        # never shows a "new author" prompt for someone already on file.
        name = (body.get("name") or "").strip()
        if not name:
            self.send_json({"ok": True, "known": False, "canonical": None, "score": 0.0})
            return
        entry, score = publish_post.match_author(name, publish_post.load_authors())
        self.send_json({"ok": True, "known": bool(entry),
                        "canonical": entry["canonical"] if entry else None,
                        "score": round(score, 2)})

    def api_posts(self, body=None):
        posts = publish_post.load_posts()["posts"]

        def entry(slug):
            e = dict(posts[slug], slug=slug)
            cover = _cover_path_for(slug)
            e["cover"] = "/" + os.path.relpath(cover, publish_post.ROOT) if cover else None
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
        try:
            if slug not in posts:
                raise PublishError(f"'{slug}' ist nicht im Register.")
            if posts[slug].get("locked"):
                raise PublishError(f"'{slug}' ist gesperrt und kann nur im Terminal bearbeitet werden.")
            ms = os.path.join(publish_post.MANUSCRIPTS_DIR, slug + ".md")
            if not os.path.exists(ms):
                raise PublishError(f"Manuskript für '{slug}' fehlt — bitte Backfill prüfen.")
        except PublishError as e:
            # Caught locally (not left to do_POST's handler) so this method
            # behaves the same whether reached via the HTTP dispatch or
            # called directly, as the test harness does.
            self.send_json({"ok": False, "error": str(e)})
            return
        SESSION.update(mode="edit", translate_of=None, edit_slug=slug, preview=None,
                       publish_args=None, cover_rel=None,
                       cover_path=_cover_path_for(slug), cover_is_repo=True)
        e = posts[slug]
        markdown = open(ms, encoding="utf-8").read()
        # The registry never stores subtitle — recompute it from the
        # manuscript, same as api_convert does for a fresh upload. A stored
        # manuscript should always have a title line, but guard anyway so a
        # malformed one degrades to no subtitle instead of a 500.
        try:
            _, subtitle, _ = publish_post.parse_md(markdown, e["lang"])
        except PublishError:
            subtitle = None
        self.send_json({"ok": True, "markdown": markdown,
                        "slug": slug, "subtitle": subtitle,
                        "cover": "/" + os.path.relpath(SESSION["cover_path"], publish_post.ROOT)
                            if SESSION["cover_path"] else None,
                        "langs": {c: cfg["label"] for c, cfg in LANGS.items()},
                        **{k: e[k] for k in ("title", "lang", "date", "author",
                                             "tag", "highlight", "alt", "caption")}})

    def api_translation_init(self, body):
        slug = body["slug"]
        posts = publish_post.load_posts()["posts"]
        try:
            if slug not in posts:
                raise PublishError(f"'{slug}' ist nicht im Register.")
        except PublishError as e:
            # Caught locally, same as api_edit_load, so this method behaves
            # the same whether reached via the HTTP dispatch or called
            # directly, as the test harness does.
            self.send_json({"ok": False, "error": str(e)})
            return
        taken = {posts[slug]["lang"]} | {
            t["lang"] for t in posts.values() if t.get("original_slug") == slug}
        SESSION.update(mode="translate", translate_of=slug, edit_slug=None, preview=None,
                       publish_args=None, cover_rel=None,
                       cover_path=_cover_path_for(slug), cover_is_repo=True)
        self.send_json({"ok": True, "original": dict(posts[slug], slug=slug),
                        "author": posts[slug]["author"],
                        "cover": "/" + os.path.relpath(SESSION["cover_path"], publish_post.ROOT)
                            if SESSION["cover_path"] else None,
                        "available_langs": {c: LANGS[c]["label"]
                                            for c in LANGS if c not in taken}})

    def api_replace_cover(self, body):
        # Used from the edit/translate form to swap the cover shown in the
        # editor without going through /api/convert again. Mirrors
        # api_convert's cover-temp-file handling. Caught locally (not left
        # to do_POST's handler) so this behaves the same whether reached via
        # HTTP or called directly, as the test harness does.
        cover_ext = os.path.splitext(body["cover_name"])[1].lower() or ".jpg"
        if cover_ext not in (".jpg", ".jpeg", ".png"):
            self.send_json({"ok": False,
                            "error": f"Cover muss .jpg oder .png sein, nicht {cover_ext}."})
            return
        fd, SESSION["cover_path"] = tempfile.mkstemp(suffix=cover_ext)
        with os.fdopen(fd, "wb") as fh:
            fh.write(base64.b64decode(body["cover_b64"]))
        SESSION["cover_is_repo"] = False
        # A new cover invalidates any existing preview/publish state — the
        # page HTML embeds the old cover's URL, so it must be regenerated.
        SESSION["cover_rel"] = None
        SESSION["preview"] = None
        SESSION["publish_args"] = None
        self.send_json({"ok": True})

    def api_md_to_html(self, body):
        # Rich-text tab: converts the manuscript into an editable HTML
        # fragment via the exact same publish_post building blocks the CLI
        # uses, so the rich editor can never drift from the Markdown ->
        # house-style pipeline. Caught locally (not left to do_POST's
        # handler) so this behaves the same whether reached via HTTP
        # dispatch or called directly, as the test harness does.
        try:
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
        except PublishError as e:
            self.send_json({"ok": False, "error": str(e)})

    def api_html_to_md(self, body):
        # Rich-text tab, reverse direction: the contenteditable fragment ->
        # manuscript markdown, via the same converter the backfill CLI
        # uses. Caught locally, same reasoning as api_md_to_html.
        try:
            from html_to_md import fragment_to_md
            self.send_json({"ok": True, "markdown": fragment_to_md(body["html"])})
        except PublishError as e:
            self.send_json({"ok": False, "error": str(e)})

    def api_preview(self, body):
        # Slug (and, for edit, language) are immutable once a post is being
        # edited or translated — never trust whatever the UI happened to send.
        if SESSION["mode"] == "translate":
            body["slug"] = f"{SESSION['translate_of']}-{body['lang']}"
        elif SESSION["mode"] == "edit":
            body["slug"] = SESSION["edit_slug"]
        # In edit mode, an untouched repo cover must NOT be passed through as
        # image_path — build_post's write path would shutil.copyfile it onto
        # itself (C1). update=True already treats image_path=None as "keep
        # the existing cover", so substitute that here. Translate mode must
        # keep passing the real path: the inherited cover has to be copied
        # to the *new* slug's cover file, and image_path=None would be
        # illegal there anyway (only --update accepts it).
        cover_for_build = (
            None if (SESSION["mode"] == "edit" and SESSION.get("cover_is_repo"))
            else SESSION["cover_path"])
        kwargs = dict(
            md_text=body["markdown"], image_path=cover_for_build,
            lang=body["lang"], date=body["date"],
            author=body.get("author") or None, slug=body.get("slug") or None,
            tag=body.get("tag") or None, highlight=body.get("highlight") or None,
            alt=body.get("alt") or None, caption=body.get("caption") or None,
            new_author=bool(body.get("new_author")),
            update=(SESSION["mode"] == "edit"),
            original_slug=SESSION.get("translate_of"),
        )
        if not SESSION["cover_path"]:
            raise PublishError("Kein Cover hochgeladen — bitte von vorn beginnen.")
        if kwargs["new_author"]:
            # Belt-and-suspenders against a duplicate authors.json entry: the
            # CLI trusts --new-author, but the app double-checks here because
            # its checkbox can be ticked from a stale/heuristic UI state. A
            # known match always wins over "register as new".
            name = kwargs["author"] or publish_post.find_author_in_md(kwargs["md_text"])
            if name:
                entry, _ = publish_post.match_author(name, publish_post.load_authors())
                if entry:
                    self.send_json({"ok": False, "error":
                        f"'{name}' ist bereits als '{entry['canonical']}' registriert — bitte "
                        f"Häkchen entfernen; veröffentlicht wird unter dem registrierten Namen."})
                    return
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
            # In edit mode the page exists by definition — not a conflict.
            "slug_exists": False if SESSION["mode"] == "edit" else os.path.exists(
                os.path.join(ROOT, "aktuelles", r["slug"] + ".html")),
            "branch": current_branch(),
        })

    def api_publish(self):
        # Pulls before build_post writes anything (via the shared `_pull`,
        # same helper git_flow uses for its own first step) so a pull
        # failure here truly precedes any local write, then hands the
        # add/commit/push half to `_add_commit_push` — also shared with
        # git_flow. It doesn't call the top-level `git_flow` in one shot
        # because build_post's write has to happen *between* the pull and
        # the add (build_post needs `files`/the commit title, which don't
        # exist until it runs) — see git_flow's docstring.
        if not SESSION["publish_args"]:
            raise PublishError("Bitte zuerst die Vorschau erzeugen.")
        log = []

        if not _pull(log):
            git_output, warn = split_pull_warning("\n\n".join(log))
            error = "git pull --rebase ist fehlgeschlagen — nichts wurde veröffentlicht." + warn
            self.send_json({"ok": False, "stage": "pull", "error": error,
                            "git_output": git_output})
            return

        try:
            r = build_post(**SESSION["publish_args"], write=True)
        except PublishError as e:
            self.send_json({"ok": False, "stage": "write", "error": str(e),
                            "git_output": "\n\n".join(log)})
            return

        msg = f"content: {'update' if SESSION['mode'] == 'edit' else 'add'} {r['title']}"
        stage = _add_commit_push(r["files"], msg, log)
        if stage == "add":
            self.send_json({"ok": False, "stage": "add",
                            "error": "git add ist fehlgeschlagen. Die Beitragsdateien wurden bereits "
                                     "geschrieben — bitte im Terminal prüfen.",
                            "git_output": "\n\n".join(log), "files": r["files"]})
            return
        if stage == "commit":
            self.send_json({"ok": False, "stage": "commit",
                            "error": "git commit ist fehlgeschlagen. Die Dateien des Beitrags sind "
                                     "bereits geschrieben und mit git add vorgemerkt (im Index) — "
                                     "bitte im Terminal beheben (z. B. Git-Identität oder ein "
                                     "Pre-Commit-Hook) und dort manuell committen und pushen.",
                            "git_output": "\n\n".join(log), "files": r["files"]})
            return
        if stage == "push":
            self.send_json({"ok": False, "stage": "push",
                            "error": "git push wurde abgelehnt. Lokal ist der Post committet — "
                                     "»Erneut versuchen« führt pull --rebase + push aus.",
                            "git_output": "\n\n".join(log)})
            return

        # Publish succeeded: the temp cover is now redundant — the real
        # /assets/blog/... file was just committed, so let it be served
        # from the repo like any other post's cover from now on.
        SESSION["cover_rel"] = None
        SESSION["cover_path"] = None
        # C2: a completed edit/translate must not leak into the next "Neuer
        # Beitrag" — reset to a fresh session now that publishing is done.
        SESSION.update(mode="new", translate_of=None, edit_slug=None, cover_is_repo=False)

        self.send_json({"ok": True,
                        "url": f"https://zwischenwelten-berlin.de/aktuelles/{r['slug']}",
                        "commit": msg, "git_output": "\n\n".join(log)})

    def api_retry_push(self):
        log = []
        code, out = run_git("pull", "--rebase")
        log.append(f"$ git pull --rebase\n{out}")
        if code != 0:
            error = "git pull --rebase ist fehlgeschlagen."
            error += _abort_stuck_rebase(log)
            self.send_json({"ok": False, "stage": "pull", "error": error,
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

    def api_new_author(self, body):
        # Caught locally (not left to do_POST's handler) so this behaves
        # the same whether reached via HTTP dispatch or called directly, as
        # the test harness does — same pattern as api_edit_load et al.
        # Paths are resolved through publish_post.ROOT/AUTHORS/etc. at call
        # time (never the ROOT imported at module load) so the `repo` test
        # fixture's monkeypatching of publish_post reaches this handler.
        try:
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

            # Validate everything about an attached page *before* writing
            # anything. authors.json must never gain an entry for an
            # author whose page turned out to be un-renderable (bad
            # extension, broken base64) — that would leave them
            # permanently half-registered, since a retry would just hit
            # the "already registered" refusal above with no way back in.
            page = body.get("page")
            photo_bytes = photo_ext = None
            if page:
                photo_ext = (page.get("photo_ext") or ".png").lower()
                if photo_ext not in (".png", ".jpg", ".jpeg"):
                    raise PublishError("Autorenfoto muss .png oder .jpg sein.")
                try:
                    photo_bytes = base64.b64decode(page["photo_b64"], validate=True)
                except (KeyError, TypeError, ValueError, binascii.Error):
                    raise PublishError(
                        "Autorenfoto fehlt oder ist beschädigt — bitte erneut auswählen.")

            registry["authors"].append({
                "id": author_id, "canonical": name, "role": role,
                "names": body.get("names") or {}, "aliases": body.get("aliases") or [],
            })
            with open(publish_post.AUTHORS, "w", encoding="utf-8") as fh:
                json.dump(registry, fh, ensure_ascii=False, indent=2)
                fh.write("\n")
            files = [os.path.relpath(publish_post.AUTHORS, publish_post.ROOT)]

            if page:
                photo_dir = os.path.join(publish_post.ROOT, "assets", "autoren")
                os.makedirs(photo_dir, exist_ok=True)
                photo_path = os.path.join(photo_dir, author_id + photo_ext)
                with open(photo_path, "wb") as fh:
                    fh.write(photo_bytes)
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
        except PublishError as e:
            self.send_json({"ok": False, "error": str(e)})

    def log_message(self, fmt, *args):   # quieter console
        # send_error()/log_error() call this with args[0] being an HTTPStatus
        # (not a request-line string) — guard so a plain 404 never raises and
        # drops the connection before send_error can write the response.
        line = args[0] if args else ""
        if isinstance(line, str) and "/api/" in line:
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
