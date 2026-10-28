import json
import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import publish_app
import sync_podcasts
import sync_videos

REAL_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
<channel>
  <title>Zwischenwelten</title>
  <language>de-de</language>
  <item>
    <title>Wem gehört Berlin?</title>
    <guid>ep-2</guid>
    <pubDate>Tue, 20 Oct 2026 08:00:00 +0200</pubDate>
    <itunes:episode>2</itunes:episode>
    <itunes:duration>42:10</itunes:duration>
    <description><![CDATA[<p>Mieten und Verdrängung in Berlin.</p><p>Shownotes …</p>]]></description>
    <enclosure url="https://cdn.example.eu/ep2.mp3" type="audio/mpeg" length="1"/>
  </item>
  <item>
    <title>ماذا بقي من الثالث من أكتوبر؟</title>
    <guid>ep-1</guid>
    <pubDate>Tue, 22 Sep 2026 08:00:00 +0200</pubDate>
    <itunes:duration>1980</itunes:duration>
    <description>حوار حول الوحدة الألمانية</description>
    <enclosure url="https://cdn.example.eu/ep1.mp3" type="audio/mpeg" length="1"/>
  </item>
  <item>
    <title>Trailer ohne Audio</title>
    <guid>trailer</guid>
  </item>
</channel>
</rss>
"""


# ---- podcasts --------------------------------------------------------------
@pytest.fixture
def pod_site(tmp_path, monkeypatch):
    (tmp_path / "assets" / "media").mkdir(parents=True)
    shutil.copyfile(os.path.join(REAL_ROOT, "podcasts.html"), tmp_path / "podcasts.html")
    feed = tmp_path / "feed.xml"
    feed.write_text(FEED, encoding="utf-8")
    data = {"feed": feed.as_uri(), "links": {"spotify": "https://open.spotify.com/show/x"},
            "episodes": []}
    (tmp_path / "assets" / "media" / "podcasts.json").write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(sync_podcasts, "ROOT", str(tmp_path))
    monkeypatch.setattr(sync_podcasts, "DATA", str(tmp_path / "assets" / "media" / "podcasts.json"))
    monkeypatch.setattr(sync_podcasts, "PAGE", str(tmp_path / "podcasts.html"))
    return tmp_path


def test_parse_feed_skips_items_without_audio():
    episodes, lang = sync_podcasts.parse_feed(FEED.encode())
    assert lang == "de"
    assert [e["guid"] for e in episodes] == ["ep-2", "ep-1"]
    assert episodes[0]["duration"] == 42 * 60 + 10
    assert episodes[0]["date"] == "2026-10-20"
    assert episodes[0]["number"] == 2
    assert episodes[0]["description"] == "Mieten und Verdrängung in Berlin."


def test_podcast_sync_replaces_placeholders(pod_site):
    r = sync_podcasts.sync()
    assert r["added"] == ["Wem gehört Berlin?", "ماذا بقي من الثالث من أكتوبر؟"]
    assert sorted(r["files"]) == ["assets/media/podcasts.json", "podcasts.html"]
    page = (pod_site / "podcasts.html").read_text(encoding="utf-8")
    assert "demo-folge.m4a" not in page and "Platzhalterdaten" not in page
    assert 'data-src="https://cdn.example.eu/ep2.mp3"' in page
    assert 'class="episode is-featured" data-lang="de"' in page
    assert 'data-lang="ar" lang="ar" dir="rtl"' in page
    assert 'href="https://open.spotify.com/show/x"' in page
    assert 'aria-disabled' not in page
    assert '<meta name="robots" content="noindex,nofollow">' in page


def test_podcast_resync_keeps_editorial_fields(pod_site):
    sync_podcasts.sync()
    data_path = pod_site / "assets" / "media" / "podcasts.json"
    data = json.loads(data_path.read_text(encoding="utf-8"))
    data["episodes"][0]["guests"] = [{"name": "Süleyman Bağ", "href": "/journalistennetzwerk/suleyman-bag"}]
    data["episodes"][0]["lang"] = "tr"
    data_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    r = sync_podcasts.sync()
    assert r["added"] == []
    ep = json.loads(data_path.read_text(encoding="utf-8"))["episodes"][0]
    assert ep["lang"] == "tr" and ep["guests"][0]["name"] == "Süleyman Bağ"
    page = (pod_site / "podcasts.html").read_text(encoding="utf-8")
    assert '<a href="/journalistennetzwerk/suleyman-bag">Süleyman Bağ</a>' in page
    # nothing new and nothing edited → nothing to commit
    assert sync_podcasts.sync()["files"] == []


def test_podcast_sync_without_feed_refuses(pod_site):
    data_path = pod_site / "assets" / "media" / "podcasts.json"
    data_path.write_text(json.dumps({"feed": "", "links": {}, "episodes": []}), encoding="utf-8")
    before = (pod_site / "podcasts.html").read_text(encoding="utf-8")
    with pytest.raises(sync_videos.SyncError, match="kein Podcast-Feed"):
        sync_podcasts.sync()
    assert (pod_site / "podcasts.html").read_text(encoding="utf-8") == before


# ---- videos ----------------------------------------------------------------
@pytest.fixture
def vid_site(tmp_path, monkeypatch):
    (tmp_path / "assets" / "media").mkdir(parents=True)
    (tmp_path / "assets" / "videos").mkdir()
    shutil.copyfile(os.path.join(REAL_ROOT, "videos.html"), tmp_path / "videos.html")
    shutil.copyfile(os.path.join(REAL_ROOT, "assets", "media", "videos.json"),
                    tmp_path / "assets" / "media" / "videos.json")
    monkeypatch.setattr(sync_videos, "ROOT", str(tmp_path))
    monkeypatch.setattr(sync_videos, "DATA", str(tmp_path / "assets" / "media" / "videos.json"))
    monkeypatch.setattr(sync_videos, "PAGE", str(tmp_path / "videos.html"))
    monkeypatch.setattr(sync_videos, "THUMBS", str(tmp_path / "assets" / "videos"))
    known = json.loads((tmp_path / "assets" / "media" / "videos.json").read_text())["videos"]
    feed = [{"id": v["id"], "title": v["title"], "date": v["date"], "description": ""} for v in known]
    monkeypatch.setattr(sync_videos, "feed_entries", lambda channel_id: feed)
    monkeypatch.setattr(sync_videos, "save_thumb", lambda v: False)
    return tmp_path, feed


def test_video_sync_without_new_uploads_changes_nothing(vid_site):
    sync_videos.sync()  # normalise the copied page once
    assert sync_videos.sync()["files"] == []


def test_video_sync_adds_new_upload(vid_site, monkeypatch):
    root, feed = vid_site
    feed.insert(0, {"id": "NEWVIDEO123", "title": "Neues Video #berlin #medien",
                    "date": "2026-10-27", "description": "Erster Absatz.\n\nwww.zwischenwelten-berlin.de"})
    monkeypatch.setattr(sync_videos, "watch_info", lambda vid: {"duration": 125, "date": "2026-10-27",
                                                                "title": "", "description": ""})
    monkeypatch.setattr(sync_videos, "is_short", lambda vid: False)
    r = sync_videos.sync()
    assert r["added"] == ["Neues Video"]
    assert sorted(r["files"]) == ["assets/media/videos.json", "videos.html"]
    page = (root / "videos.html").read_text(encoding="utf-8")
    assert 'data-yt="NEWVIDEO123"' in page and "Erster Absatz." in page
    assert '<span class="video-duration">2:05</span>' in page


# ---- Publish-App endpoints -------------------------------------------------
class FakeHandler(publish_app.Handler):
    def __init__(self):
        self.sent = None
    def send_json(self, payload, status=200):
        self.sent = (status, payload)


@pytest.fixture
def git_calls(monkeypatch):
    calls = {}
    monkeypatch.setattr(publish_app, "_pull", lambda log: True)
    def fake_acp(files, msg, log):
        calls["files"], calls["msg"] = files, msg
        return ""
    monkeypatch.setattr(publish_app, "_add_commit_push", fake_acp)
    return calls


def test_sync_endpoint_commits_changed_files(git_calls, monkeypatch):
    monkeypatch.setattr(sync_videos, "sync", lambda: {"added": ["Neues Video"], "count": 7,
                                                      "files": ["videos.html"]})
    h = FakeHandler()
    h.api_sync_media("videos")
    _, payload = h.sent
    assert payload["ok"] and payload["added"] == ["Neues Video"]
    assert git_calls == {"files": ["videos.html"], "msg": "content: sync videos (+ Neues Video)"}


def test_sync_endpoint_without_changes_does_not_commit(git_calls, monkeypatch):
    monkeypatch.setattr(sync_podcasts, "sync", lambda: {"added": [], "count": 3, "files": []})
    h = FakeHandler()
    h.api_sync_media("podcasts")
    _, payload = h.sent
    assert payload["ok"] and payload["commit"] == ""
    assert git_calls == {}


def test_sync_endpoint_reports_sync_error_without_git(git_calls, monkeypatch):
    def boom():
        raise sync_videos.SyncError("Es ist noch kein Podcast-Feed eingetragen.")
    monkeypatch.setattr(sync_podcasts, "sync", boom)
    h = FakeHandler()
    h.api_sync_media("podcasts")
    _, payload = h.sent
    assert not payload["ok"] and payload["stage"] == "sync"
    assert "Podcast-Feed" in payload["error"]
    assert git_calls == {}


def test_sync_endpoint_failed_pull_skips_sync(monkeypatch):
    monkeypatch.setattr(publish_app, "_pull", lambda log: False)
    monkeypatch.setattr(sync_videos, "sync", lambda: pytest.fail("sync must not run"))
    h = FakeHandler()
    h.api_sync_media("videos")
    _, payload = h.sent
    assert not payload["ok"] and payload["stage"] == "pull"


def test_sync_endpoint_push_failure_offers_retry(monkeypatch):
    monkeypatch.setattr(publish_app, "_pull", lambda log: True)
    monkeypatch.setattr(publish_app, "_add_commit_push", lambda files, msg, log: "push")
    monkeypatch.setattr(sync_videos, "sync", lambda: {"added": [], "count": 6, "files": ["videos.html"]})
    h = FakeHandler()
    h.api_sync_media("videos")
    _, payload = h.sent
    assert not payload["ok"] and payload["stage"] == "push"
