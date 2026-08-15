import base64
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import publish_app
import publish_post

from test_build_post import repo, cover, MD, INDEX_MIN  # noqa: F401 (also used by new rich-text tests)


class FakeHandler(publish_app.Handler):
    """Bypass BaseHTTPRequestHandler's socket constructor."""
    def __init__(self):
        self.sent = None
    def send_json(self, payload, status=200):
        self.sent = (status, payload)


@pytest.fixture(autouse=True)
def clean_session():
    publish_app.SESSION.update(cover_path=None, cover_rel=None, preview=None,
                               publish_args=None, mode="new", translate_of=None,
                               edit_slug=None, cover_is_repo=False)


def published(repo, cover):
    publish_post.build_post(MD, cover, lang="de", date="2026-08-03", write=True)


def test_api_posts_groups_translations(repo, cover):
    published(repo, cover)
    publish_post.build_post(MD, cover, lang="tr", date="2026-08-04",
                            slug="ein-test-tr", original_slug="ein-test", write=True)
    h = FakeHandler()
    h.api_posts()
    status, payload = h.sent
    assert payload["ok"]
    assert [p["slug"] for p in payload["posts"]] == ["ein-test"]
    assert [t["slug"] for t in payload["posts"][0]["translations"]] == ["ein-test-tr"]
    # The list's author/language filters need a canonical author key per row
    # (resolved via the same fuzzy matcher publishing uses) and lang labels.
    assert payload["posts"][0]["author_id"] == "suleyman-bag"
    assert payload["posts"][0]["translations"][0]["author_id"] == "suleyman-bag"
    assert payload["langs"]["de"] == "Deutsch"


def test_edit_load_returns_manuscript_and_meta(repo, cover):
    published(repo, cover)
    h = FakeHandler()
    h.api_edit_load({"slug": "ein-test"})
    _, payload = h.sent
    assert payload["ok"]
    assert payload["markdown"] == MD
    assert payload["lang"] == "de"
    assert payload["slug"] == "ein-test"
    assert payload["subtitle"] == "Der Untertitel"
    assert publish_app.SESSION["mode"] == "edit"
    assert os.path.exists(publish_app.SESSION["cover_path"])


def test_edit_load_refuses_locked(repo, cover):
    published(repo, cover)
    reg = publish_post.load_posts()
    reg["posts"]["ein-test"]["locked"] = True
    publish_post.save_posts(reg)
    h = FakeHandler()
    h.api_edit_load({"slug": "ein-test"})
    _, payload = h.sent
    assert not payload["ok"]


def test_translation_init_lists_missing_langs(repo, cover):
    published(repo, cover)
    h = FakeHandler()
    h.api_translation_init({"slug": "ein-test"})
    _, payload = h.sent
    assert payload["ok"]
    assert "de" not in payload["available_langs"]
    assert "tr" in payload["available_langs"]
    assert publish_app.SESSION["mode"] == "translate"


def test_translation_init_unknown_slug_returns_error(repo, cover):
    h = FakeHandler()
    h.api_translation_init({"slug": "gibt-es-nicht"})
    _, payload = h.sent
    assert payload["ok"] is False


def test_preview_in_translate_mode_forces_slug(repo, cover):
    published(repo, cover)
    h = FakeHandler()
    h.api_translation_init({"slug": "ein-test"})
    h.api_preview({"markdown": MD, "lang": "tr", "date": "2026-08-05",
                   "slug": "ignoriert"})
    _, payload = h.sent
    assert payload["ok"] and payload["fidelity_ok"]
    assert payload["slug"] == "ein-test-tr"


def test_edit_publish_without_cover_replacement_does_not_crash(repo, cover):
    # Regression for C1: edit-mode publish without touching the cover must
    # not try to shutil.copyfile the repo cover onto itself.
    published(repo, cover)
    h = FakeHandler()
    h.api_edit_load({"slug": "ein-test"})
    changed = MD.replace("Erster Absatz", "Geänderter Absatz")
    h.api_preview({"markdown": changed, "lang": "de", "date": "2026-08-03"})
    _, payload = h.sent
    assert payload["ok"] and payload["fidelity_ok"], payload

    cover_path = repo / "assets" / "blog" / "ein-test-cover.png"
    assert cover_path.exists()
    r = publish_post.build_post(**publish_app.SESSION["publish_args"], write=True)
    assert cover_path.exists()
    assert r["cover_rel"] == "/assets/blog/ein-test-cover.png"
    page = (repo / "aktuelles" / "ein-test.html").read_text(encoding="utf-8")
    assert "Geänderter Absatz" in page


def test_translate_still_copies_inherited_cover_to_new_slug(repo, cover):
    # The C1 fix must not break translate mode: the inherited cover has to
    # be COPIED to the new slug's cover file, not passed through as None.
    published(repo, cover)
    h = FakeHandler()
    h.api_translation_init({"slug": "ein-test"})
    h.api_preview({"markdown": MD, "lang": "tr", "date": "2026-08-05"})
    _, payload = h.sent
    assert payload["ok"] and payload["fidelity_ok"], payload
    assert publish_app.SESSION["publish_args"]["image_path"] is not None

    r = publish_post.build_post(**publish_app.SESSION["publish_args"], write=True)
    assert (repo / "assets" / "blog" / "ein-test-tr-cover.png").exists()
    assert r["cover_rel"] == "/assets/blog/ein-test-tr-cover.png"


def test_replace_cover_swaps_session_cover_and_invalidates_preview(repo, cover):
    published(repo, cover)
    h = FakeHandler()
    h.api_edit_load({"slug": "ein-test"})
    h.api_preview({"markdown": MD, "lang": "de", "date": "2026-08-03"})
    assert publish_app.SESSION["preview"] is not None
    assert publish_app.SESSION["publish_args"] is not None

    new_bytes = b"fake-new-cover-bytes"
    h.api_replace_cover({"cover_name": "new-cover.jpg",
                         "cover_b64": base64.b64encode(new_bytes).decode()})
    _, payload = h.sent
    assert payload["ok"]
    assert publish_app.SESSION["preview"] is None
    assert publish_app.SESSION["publish_args"] is None
    assert os.path.exists(publish_app.SESSION["cover_path"])
    with open(publish_app.SESSION["cover_path"], "rb") as fh:
        assert fh.read() == new_bytes


def test_replace_cover_rejects_bad_extension(repo, cover):
    h = FakeHandler()
    h.api_replace_cover({"cover_name": "malware.exe",
                         "cover_b64": base64.b64encode(b"x").decode()})
    _, payload = h.sent
    assert payload["ok"] is False
    assert publish_app.SESSION["cover_path"] is None


COVER_PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGBgAAAABQABh6FO1AAAAABJRU5ErkJggg=="


def test_new_author_registers_and_builds_page(repo, monkeypatch):
    monkeypatch.setattr(publish_app, "git_flow", lambda files, msg: (True, "", "ok"))
    (repo / "assets" / "autoren").mkdir(parents=True)
    h = FakeHandler()
    h.api_new_author({"canonical": "Ayşe Örnek", "role": "Journalistin",
                      "page": {"bio": "Absatz eins.\n\nAbsatz zwei.",
                               "photo_b64": COVER_PNG_B64, "photo_ext": ".png"}})
    _, payload = h.sent
    assert payload["ok"] and payload["id"] == "ayse-ornek"
    reg = json.loads((repo / "assets" / "blog" / "authors.json").read_text())
    assert any(a["id"] == "ayse-ornek" for a in reg["authors"])
    assert (repo / "journalistennetzwerk" / "ayse-ornek.html").exists()
    assert (repo / "assets" / "autoren" / "ayse-ornek.png").exists()


def test_new_author_refuses_known_person(repo, monkeypatch):
    monkeypatch.setattr(publish_app, "git_flow", lambda files, msg: (True, "", "ok"))
    h = FakeHandler()
    h.api_new_author({"canonical": "Сулейман Баг", "role": "x"})
    _, payload = h.sent
    assert not payload["ok"]
    assert "Süleyman Bağ" in payload["error"]


def test_new_author_rejects_bad_photo_ext_without_registering(repo, monkeypatch):
    monkeypatch.setattr(publish_app, "git_flow", lambda files, msg: (True, "", "ok"))
    before = (repo / "assets" / "blog" / "authors.json").read_text()
    h = FakeHandler()
    h.api_new_author({"canonical": "Ayşe Örnek", "role": "Journalistin",
                      "page": {"bio": "Absatz eins.", "photo_b64": COVER_PNG_B64,
                               "photo_ext": ".gif"}})
    _, payload = h.sent
    assert not payload["ok"]
    after = (repo / "assets" / "blog" / "authors.json").read_text()
    assert before == after
    assert not (repo / "journalistennetzwerk" / "ayse-ornek.html").exists()


def test_new_author_missing_photo_b64_gives_german_error(repo, monkeypatch):
    monkeypatch.setattr(publish_app, "git_flow", lambda files, msg: (True, "", "ok"))
    before = (repo / "assets" / "blog" / "authors.json").read_text()
    h = FakeHandler()
    h.api_new_author({"canonical": "Ayşe Örnek", "role": "Journalistin",
                      "page": {"bio": "Absatz eins.", "photo_ext": ".png"}})
    _, payload = h.sent
    assert not payload["ok"]
    assert "foto" in payload["error"].lower()
    after = (repo / "assets" / "blog" / "authors.json").read_text()
    assert before == after


def test_new_author_broken_photo_b64_gives_german_error(repo, monkeypatch):
    monkeypatch.setattr(publish_app, "git_flow", lambda files, msg: (True, "", "ok"))
    before = (repo / "assets" / "blog" / "authors.json").read_text()
    h = FakeHandler()
    h.api_new_author({"canonical": "Ayşe Örnek", "role": "Journalistin",
                      "page": {"bio": "Absatz eins.", "photo_b64": "not-valid-base64!!",
                               "photo_ext": ".png"}})
    _, payload = h.sent
    assert not payload["ok"]
    assert "foto" in payload["error"].lower()
    after = (repo / "assets" / "blog" / "authors.json").read_text()
    assert before == after


def test_api_authors_lists_registry_with_assets_and_counts(repo, cover):
    published(repo, cover)
    publish_post.build_post(MD, cover, lang="tr", date="2026-08-04",
                            slug="ein-test-tr", original_slug="ein-test", write=True)
    (repo / "assets" / "autoren").mkdir(parents=True)
    (repo / "assets" / "autoren" / "suleyman-bag.png").write_bytes(b"png")
    (repo / "journalistennetzwerk" / "suleyman-bag.html").write_text("<html>", encoding="utf-8")
    h = FakeHandler()
    h.api_authors()
    _, payload = h.sent
    assert payload["ok"]
    by_id = {a["id"]: a for a in payload["authors"]}
    sb = by_id["suleyman-bag"]
    assert sb["canonical"] == "Süleyman Bağ"
    assert sb["photo"] == "/assets/autoren/suleyman-bag.png"
    assert sb["page"] == "/journalistennetzwerk/suleyman-bag.html"
    assert sb["post_count"] == 2  # original + translation
    dh = by_id["dominique-hensel"]
    assert dh["photo"] is None and dh["page"] is None and dh["post_count"] == 0
    assert dh["role"] and isinstance(dh["aliases"], list)


def test_update_author_role_and_aliases_only(repo, monkeypatch):
    seen = {}
    monkeypatch.setattr(publish_app, "git_flow",
                        lambda files, msg: seen.update(files=files, msg=msg) or (True, "", "ok"))
    h = FakeHandler()
    h.api_update_author({"id": "dominique-hensel", "role": "Neue Rolle",
                         "aliases": ["D. Hensel", "  ", ""]})
    _, payload = h.sent
    assert payload["ok"], payload
    reg = json.loads((repo / "assets" / "blog" / "authors.json").read_text())
    entry = next(a for a in reg["authors"] if a["id"] == "dominique-hensel")
    assert entry["role"] == "Neue Rolle"
    assert entry["aliases"] == ["D. Hensel"]
    assert seen["files"] == ["assets/blog/authors.json"]
    assert "Dominique Hensel" in seen["msg"]
    assert not (repo / "journalistennetzwerk" / "dominique-hensel.html").exists()


def test_update_author_with_page_regenerates_and_replaces_old_photo(repo, monkeypatch):
    monkeypatch.setattr(publish_app, "git_flow", lambda files, msg: (True, "", "ok"))
    (repo / "assets" / "autoren").mkdir(parents=True)
    (repo / "assets" / "autoren" / "dominique-hensel.jpg").write_bytes(b"old")
    h = FakeHandler()
    h.api_update_author({"id": "dominique-hensel", "role": "Chefredakteurin",
                         "page": {"bio": "Absatz eins.\n\nAbsatz zwei.",
                                  "photo_b64": COVER_PNG_B64, "photo_ext": ".png"}})
    _, payload = h.sent
    assert payload["ok"], payload
    page = (repo / "journalistennetzwerk" / "dominique-hensel.html").read_text(encoding="utf-8")
    assert "Dominique Hensel" in page
    assert "Chefredakteurin" in page
    assert "Absatz eins." in page and "Absatz zwei." in page
    assert "/assets/autoren/dominique-hensel.png" in page
    assert (repo / "assets" / "autoren" / "dominique-hensel.png").exists()
    assert not (repo / "assets" / "autoren" / "dominique-hensel.jpg").exists()


def test_update_author_page_reuses_existing_photo(repo, monkeypatch):
    monkeypatch.setattr(publish_app, "git_flow", lambda files, msg: (True, "", "ok"))
    (repo / "assets" / "autoren").mkdir(parents=True)
    (repo / "assets" / "autoren" / "dominique-hensel.jpg").write_bytes(b"jpg")
    h = FakeHandler()
    h.api_update_author({"id": "dominique-hensel", "role": "Chefredakteurin",
                         "page": {"bio": "Nur ein Absatz."}})
    _, payload = h.sent
    assert payload["ok"], payload
    page = (repo / "journalistennetzwerk" / "dominique-hensel.html").read_text(encoding="utf-8")
    assert "/assets/autoren/dominique-hensel.jpg" in page
    assert (repo / "assets" / "autoren" / "dominique-hensel.jpg").read_bytes() == b"jpg"


def test_update_author_unknown_id_errors(repo, monkeypatch):
    monkeypatch.setattr(publish_app, "git_flow", lambda files, msg: (True, "", "ok"))
    h = FakeHandler()
    h.api_update_author({"id": "gibt-es-nicht", "role": "x"})
    _, payload = h.sent
    assert payload["ok"] is False


def test_update_author_empty_role_errors(repo, monkeypatch):
    monkeypatch.setattr(publish_app, "git_flow", lambda files, msg: (True, "", "ok"))
    before = (repo / "assets" / "blog" / "authors.json").read_text()
    h = FakeHandler()
    h.api_update_author({"id": "dominique-hensel", "role": "  "})
    _, payload = h.sent
    assert payload["ok"] is False
    assert (repo / "assets" / "blog" / "authors.json").read_text() == before


def test_update_author_bad_photo_leaves_registry_unchanged(repo, monkeypatch):
    monkeypatch.setattr(publish_app, "git_flow", lambda files, msg: (True, "", "ok"))
    before = (repo / "assets" / "blog" / "authors.json").read_text()
    h = FakeHandler()
    h.api_update_author({"id": "dominique-hensel", "role": "Neue Rolle",
                         "page": {"bio": "Absatz.", "photo_b64": "not-base64!!",
                                  "photo_ext": ".png"}})
    _, payload = h.sent
    assert payload["ok"] is False
    assert "foto" in payload["error"].lower()
    assert (repo / "assets" / "blog" / "authors.json").read_text() == before
    assert not (repo / "journalistennetzwerk" / "dominique-hensel.html").exists()


def test_update_author_page_without_any_photo_errors(repo, monkeypatch):
    monkeypatch.setattr(publish_app, "git_flow", lambda files, msg: (True, "", "ok"))
    h = FakeHandler()
    h.api_update_author({"id": "dominique-hensel", "role": "Neue Rolle",
                         "page": {"bio": "Absatz."}})
    _, payload = h.sent
    assert payload["ok"] is False
    assert "foto" in payload["error"].lower()


def test_md_to_html_and_back_round_trips(repo, cover):
    h = FakeHandler()
    h.api_md_to_html({"markdown": MD, "lang": "de"})
    _, payload = h.sent
    assert payload["ok"]
    assert payload["html"].startswith("<h1>Ein Test</h1>")
    assert "<em>Der Untertitel</em>" in payload["html"]
    assert "Author: Süleyman Bağ" in payload["html"]

    h2 = FakeHandler()
    h2.api_html_to_md({"html": payload["html"]})
    _, p2 = h2.sent
    assert p2["ok"]
    # word-identical: rebuilding from the round-tripped md must satisfy fidelity
    r = publish_post.build_post(p2["markdown"], cover, lang="de",
                                date="2026-08-03", slug="rt", author=None,
                                write=False)
    assert r["title"] == "Ein Test"
    assert r["subtitle"] == "Der Untertitel"
    assert r["author"] == "Süleyman Bağ"


def test_md_to_html_missing_title_still_editable(repo):
    # Superseded behavior: a missing '# Titel' used to be an error here, but
    # that made the rich-text tab unusable for plain-text drafts. Now the
    # fragment simply has no <h1>; the title requirement bites at preview.
    h = FakeHandler()
    h.api_md_to_html({"markdown": "Kein Titel hier.\n", "lang": "de"})
    _, payload = h.sent
    assert payload["ok"] is True
    assert "<h1>" not in payload["html"]
    assert "Kein Titel hier." in payload["html"]


def test_html_to_md_preserves_structure_markers():
    h = FakeHandler()
    html = ('<h1>Ein Test</h1>\n<p><em>Der Untertitel</em></p>\n'
            '<p>Author: Süleyman Bağ</p>\n'
            '<p>Erster Absatz mit <strong>wichtig</strong>.</p>\n'
            '<h2>Zwischentitel</h2>\n'
            '<ul><li>eins</li><li>zwei</li></ul>\n'
            '<blockquote class="pull-quote"><p>Ein schönes Zitat.</p></blockquote>')
    h.api_html_to_md({"html": html})
    _, payload = h.sent
    assert payload["ok"]
    md = payload["markdown"]
    assert "# Ein Test" in md
    assert "*Der Untertitel*" in md
    assert "Author: Süleyman Bağ" in md
    assert "**wichtig**" in md
    assert "## Zwischentitel" in md
    assert "- eins" in md
    assert "> Ein schönes Zitat." in md


def _convert_body(**extra):
    body = {"manuscript_name": "post.md",
            "manuscript_b64": base64.b64encode(MD.encode()).decode()}
    body.update(extra)
    return body


def test_convert_without_translate_flag_resets_leaked_translate_mode(repo, cover):
    # Regression for C2: an abandoned/completed translation must not leak
    # into the next "Neuer Beitrag" convert.
    published(repo, cover)
    h = FakeHandler()
    h.api_translation_init({"slug": "ein-test"})
    assert publish_app.SESSION["mode"] == "translate"

    h.api_convert(_convert_body(
        cover_name="cover.jpg",
        cover_b64=base64.b64encode(b"fake-cover-bytes").decode()))
    _, payload = h.sent
    assert payload["ok"], payload
    assert publish_app.SESSION["mode"] == "new"
    assert publish_app.SESSION["translate_of"] is None
    assert publish_app.SESSION["edit_slug"] is None

    h2 = FakeHandler()
    h2.api_preview({"markdown": MD, "lang": "de", "date": "2026-08-05",
                    "slug": "frischer-slug"})
    _, payload2 = h2.sent
    assert payload2["ok"] and payload2["fidelity_ok"], payload2
    assert payload2["slug"] == "frischer-slug"  # not force-overridden


def test_convert_with_translate_flag_preserves_translate_mode(repo, cover):
    published(repo, cover)
    h = FakeHandler()
    h.api_translation_init({"slug": "ein-test"})
    h.api_convert(_convert_body(translate=True))
    _, payload = h.sent
    assert payload["ok"], payload
    assert publish_app.SESSION["mode"] == "translate"
    assert publish_app.SESSION["translate_of"] == "ein-test"

    h2 = FakeHandler()
    h2.api_preview({"markdown": MD, "lang": "tr", "date": "2026-08-05",
                    "slug": "ignoriert"})
    _, payload2 = h2.sent
    assert payload2["ok"] and payload2["fidelity_ok"], payload2
    assert payload2["slug"] == "ein-test-tr"


def test_publish_success_resets_translate_mode(repo, cover, monkeypatch):
    published(repo, cover)
    monkeypatch.setattr(publish_app, "_pull", lambda log: True)
    monkeypatch.setattr(publish_app, "_add_commit_push", lambda files, msg, log: "")
    h = FakeHandler()
    h.api_translation_init({"slug": "ein-test"})
    h.api_preview({"markdown": MD, "lang": "tr", "date": "2026-08-05"})
    _, payload = h.sent
    assert payload["ok"] and payload["fidelity_ok"], payload

    h.api_publish()
    _, payload = h.sent
    assert payload["ok"], payload
    assert publish_app.SESSION["mode"] == "new"
    assert publish_app.SESSION["translate_of"] is None
    assert publish_app.SESSION["edit_slug"] is None
    assert publish_app.SESSION["cover_is_repo"] is False


def test_origin_allowed_no_origin_header():
    assert publish_app._origin_allowed({})


def test_origin_allowed_matching_localhost_origins():
    assert publish_app._origin_allowed({"Origin": "http://localhost:8765"})
    assert publish_app._origin_allowed({"Origin": "http://127.0.0.1:8765"})


def test_origin_allowed_rejects_foreign_origin():
    assert not publish_app._origin_allowed({"Origin": "https://evil.example"})


def test_git_flow_pull_failure_log_has_no_raw_sentinel(monkeypatch):
    def fake_run_git(*args):
        if args[0] == "pull":
            return 1, "pull failed output"
        if args[:2] == ("rebase", "--abort"):
            return 1, "abort also failed"
        return 0, ""
    monkeypatch.setattr(publish_app, "run_git", fake_run_git)
    monkeypatch.setattr(publish_app, "_rebase_in_progress", lambda: True)
    ok, stage, log = publish_app.git_flow(["f.txt"], "msg")
    assert not ok and stage == "pull"
    assert "\x00" not in log
    assert "Außerdem konnte der Rebase" in log


def test_md_to_html_without_title_falls_back_to_body(repo):
    # A plain-text manuscript (no '# Titel' line) must still open in the
    # rich-text tab; the title requirement is enforced at preview/publish.
    h = FakeHandler()
    h.api_md_to_html({"markdown": "Nur ein Absatz.\n\nZweiter Absatz.",
                      "lang": "de"})
    _, payload = h.sent
    assert payload["ok"], payload
    assert "<h1>" not in payload["html"]
    assert "Nur ein Absatz." in payload["html"]
    h2 = FakeHandler()
    h2.api_html_to_md({"html": payload["html"]})
    _, p2 = h2.sent
    assert p2["ok"]
    assert "Nur ein Absatz." in p2["markdown"]
    assert "Zweiter Absatz." in p2["markdown"]


def test_pull_skipped_when_branch_has_no_upstream(monkeypatch):
    calls = []

    def fake_run_git(*args):
        calls.append(args)
        if args[0] == "rev-parse":
            return 128, "fatal: no upstream configured for branch"
        return 0, ""

    monkeypatch.setattr(publish_app, "run_git", fake_run_git)
    log = []
    assert publish_app._pull(log) is True
    assert not any(a[0] == "pull" for a in calls)
    assert "keinen Upstream" in "\n".join(log)
