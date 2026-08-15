import base64
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import publish_app
import publish_post

from test_build_post import repo, cover, MD, INDEX_MIN  # noqa: F401


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
                               edit_slug=None)


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
