#!/usr/bin/env python3
"""Browser publishing app for the ZWISCHENWELTEN blog.

    python3 scripts/publish_app.py

Opens http://localhost:8765 — drop a manuscript (.md/.docx/.doc) and a cover
image, review the pre-filled metadata, preview the exact page, publish to
GitHub Pages. All rendering goes through publish_post.build_post, so the app
can never produce different HTML than the CLI, and the fidelity gate always
runs before anything is written.
"""

import base64
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
SESSION = {"cover_path": None, "cover_rel": None, "preview": None, "publish_args": None}


def run_git(*args):
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip()


def current_branch():
    _, out = run_git("rev-parse", "--abbrev-ref", "HEAD")
    return out


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
            else:
                self.send_error(404)
        except (ManuscriptError, PublishError) as e:
            self.send_json({"ok": False, "error": str(e)})
        except Exception as e:                     # noqa: BLE001 — show, don't crash
            self.send_json({"ok": False, "error": f"{type(e).__name__}: {e}"}, status=500)

    def api_convert(self, body):
        # A new manuscript invalidates any prior preview/publish state — never
        # let a stale draft be published after a fresh conversion.
        SESSION["preview"] = None
        SESSION["publish_args"] = None
        md, warnings = load_manuscript(body["manuscript_name"],
                                       base64.b64decode(body["manuscript_b64"]))
        # cover -> temp file, remember the future URL for the preview
        cover_ext = os.path.splitext(body["cover_name"])[1].lower() or ".jpg"
        if cover_ext not in (".jpg", ".jpeg", ".png"):
            raise ManuscriptError(f"Cover muss .jpg oder .png sein, nicht {cover_ext}.")
        fd, SESSION["cover_path"] = tempfile.mkstemp(suffix=cover_ext)
        with os.fdopen(fd, "wb") as fh:
            fh.write(base64.b64decode(body["cover_b64"]))

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

    def api_preview(self, body):
        kwargs = dict(
            md_text=body["markdown"], image_path=SESSION["cover_path"],
            lang=body["lang"], date=body["date"],
            author=body.get("author") or None, slug=body.get("slug") or None,
            tag=body.get("tag") or None, highlight=body.get("highlight") or None,
            alt=body.get("alt") or None, caption=body.get("caption") or None,
            new_author=bool(body.get("new_author")),
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
            "slug_exists": os.path.exists(
                os.path.join(ROOT, "aktuelles", r["slug"] + ".html")),
            "branch": current_branch(),
        })

    def api_publish(self):
        if not SESSION["publish_args"]:
            raise PublishError("Bitte zuerst die Vorschau erzeugen.")
        log = []

        code, out = run_git("pull", "--rebase")
        log.append(f"$ git pull --rebase\n{out}")
        if code != 0:
            error = "git pull --rebase ist fehlgeschlagen — nichts wurde veröffentlicht."
            abort_code, abort_out = run_git("rebase", "--abort")
            log.append(f"$ git rebase --abort\n{abort_out}")
            if abort_code != 0:
                error += (" Außerdem konnte der Rebase nicht automatisch abgebrochen werden — "
                          "das Repository steckt möglicherweise noch mitten in einem Rebase und "
                          "braucht manuelle Aufmerksamkeit im Terminal (git status, git rebase --abort).")
            self.send_json({"ok": False, "stage": "pull", "error": error,
                            "git_output": "\n\n".join(log)})
            return

        try:
            r = build_post(**SESSION["publish_args"], write=True)
        except PublishError as e:
            self.send_json({"ok": False, "stage": "write", "error": str(e),
                            "git_output": "\n\n".join(log)})
            return

        code, out = run_git("add", "--", *r["files"])
        log.append(f"$ git add {' '.join(r['files'])}\n{out}")
        if code != 0:
            self.send_json({"ok": False, "stage": "add",
                            "error": "git add ist fehlgeschlagen. Die Beitragsdateien wurden bereits "
                                     "geschrieben — bitte im Terminal prüfen.",
                            "git_output": "\n\n".join(log), "files": r["files"]})
            return

        msg = f"content: add {r['title']}"
        code, out = run_git("commit", "-m", msg)
        log.append(f"$ git commit -m {msg!r}\n{out}")
        if code != 0:
            self.send_json({"ok": False, "stage": "commit",
                            "error": "git commit ist fehlgeschlagen. Die Dateien des Beitrags sind "
                                     "bereits geschrieben und mit git add vorgemerkt (im Index) — "
                                     "bitte im Terminal beheben (z. B. Git-Identität oder ein "
                                     "Pre-Commit-Hook) und dort manuell committen und pushen.",
                            "git_output": "\n\n".join(log), "files": r["files"]})
            return

        code, out = run_git("push", "origin", "HEAD")
        log.append(f"$ git push origin HEAD\n{out}")
        if code != 0:
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

        self.send_json({"ok": True,
                        "url": f"https://zwischenwelten-berlin.de/aktuelles/{r['slug']}",
                        "commit": msg, "git_output": "\n\n".join(log)})

    def api_retry_push(self):
        log = []
        code, out = run_git("pull", "--rebase")
        log.append(f"$ git pull --rebase\n{out}")
        if code != 0:
            error = "git pull --rebase ist fehlgeschlagen."
            abort_code, abort_out = run_git("rebase", "--abort")
            log.append(f"$ git rebase --abort\n{abort_out}")
            if abort_code != 0:
                error += (" Außerdem konnte der Rebase nicht automatisch abgebrochen werden — "
                          "das Repository steckt möglicherweise noch mitten in einem Rebase und "
                          "braucht manuelle Aufmerksamkeit im Terminal (git status, git rebase --abort).")
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
