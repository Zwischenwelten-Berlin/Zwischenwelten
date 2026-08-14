import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import backfill_manuscripts
import publish_post

# Reuse the repo/cover fixtures and MD from test_build_post.
from test_build_post import repo, cover, MD, INDEX_MIN  # noqa: F401


def test_backfill_recovers_written_post(repo, cover):
    publish_post.build_post(MD, cover, lang="de", date="2026-08-03", write=True)
    # wipe store+registry, keep the page — the pre-v2 state
    os.remove(repo / "assets" / "blog" / "manuscripts" / "ein-test.md")
    os.remove(repo / "assets" / "blog" / "posts.json")

    results = backfill_manuscripts.backfill()
    assert ("ein-test", "ok") in results
    assert (repo / "assets" / "blog" / "manuscripts" / "ein-test.md").exists()
    reg = json.loads((repo / "assets" / "blog" / "posts.json").read_text())
    assert reg["posts"]["ein-test"]["author"] == "Süleyman Bağ"


def test_backfill_is_idempotent(repo, cover):
    publish_post.build_post(MD, cover, lang="de", date="2026-08-03", write=True)
    results = backfill_manuscripts.backfill()
    assert results == [("ein-test", "skipped")]


def test_unrecoverable_page_is_locked(repo, cover):
    publish_post.build_post(MD, cover, lang="de", date="2026-08-03", write=True)
    os.remove(repo / "assets" / "blog" / "posts.json")
    page = repo / "aktuelles" / "ein-test.html"
    # inject a hand-built element whose words a recovered manuscript cannot contain
    html = page.read_text(encoding="utf-8").replace(
        '<div class="article-back">',
        '<div class="podium">Handgebauter Sonderblock</div><div class="article-back">')
    page.write_text(html, encoding="utf-8")

    results = backfill_manuscripts.backfill()
    assert ("ein-test", "locked") in results
    reg = json.loads((repo / "assets" / "blog" / "posts.json").read_text())
    assert reg["posts"]["ein-test"]["locked"] is True
    assert not (repo / "assets" / "blog" / "manuscripts" / "ein-test.md").exists()


def test_translation_suffix_sets_original_slug(repo, cover):
    publish_post.build_post(MD, cover, lang="de", date="2026-08-03", write=True)
    publish_post.build_post(MD, cover, lang="tr", date="2026-08-03",
                            slug="ein-test-tr", write=True)
    os.remove(repo / "assets" / "blog" / "posts.json")
    backfill_manuscripts.backfill()
    reg = json.loads((repo / "assets" / "blog" / "posts.json").read_text())
    assert reg["posts"]["ein-test-tr"]["original_slug"] == "ein-test"
    assert reg["posts"]["ein-test"]["original_slug"] is None
