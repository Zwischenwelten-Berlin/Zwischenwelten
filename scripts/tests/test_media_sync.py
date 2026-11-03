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
    monkeypatch.setattr(sync_podcasts, "COVERS", str(tmp_path / "assets" / "podcasts" / "covers"))
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
    assert '<meta name="robots" content="index,follow">' in page


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


def test_podcast_resync_reports_changed_and_removed_episodes(pod_site):
    sync_podcasts.sync()
    feed = pod_site / "feed.xml"
    xml = feed.read_text(encoding="utf-8")
    xml = xml.replace("<title>Wem gehört Berlin?</title>", "<title>Wem gehört Berlin? (neu)</title>")
    start = xml.index("<item>\n    <title>ماذا")
    xml = xml[:start] + xml[xml.index("</item>", start) + len("</item>"):]
    feed.write_text(xml, encoding="utf-8")
    r = sync_podcasts.sync()
    assert r["added"] == [] and r["updated"] == ["Wem gehört Berlin? (neu)"]
    assert r["removed"] == ["ماذا بقي من الثالث من أكتوبر؟"]
    page = (pod_site / "podcasts.html").read_text(encoding="utf-8")
    assert "Wem gehört Berlin? (neu)" in page and "ep1.mp3" not in page
    assert sync_podcasts.sync()["updated"] == []


def _jpeg(path, color, size=900):
    from PIL import Image
    Image.new("RGB", (size, size), color).save(path, "JPEG")
    return path.as_uri()


def test_podcast_sync_saves_covers_and_follows_changes(pod_site):
    feed = pod_site / "feed.xml"
    ep_img = _jpeg(pod_site / "ep2.jpg", "orange")
    show_img = _jpeg(pod_site / "show.jpg", "navy")
    xml = feed.read_text(encoding="utf-8")
    xml = xml.replace("<language>de-de</language>",
                      f'<language>de-de</language>\n  <itunes:image href="{show_img}"/>')
    xml = xml.replace("<guid>ep-2</guid>", f'<guid>ep-2</guid>\n    <itunes:image href="{ep_img}"/>')
    feed.write_text(xml, encoding="utf-8")

    r = sync_podcasts.sync()
    covers = sorted(p for p in r["files"] if p.startswith("assets/podcasts/covers/"))
    assert len(covers) == 2  # own cover for ep-2, the show's for ep-1
    from PIL import Image
    with Image.open(pod_site / covers[0]) as im:
        assert im.width == sync_podcasts.COVER_W
    page = (pod_site / "podcasts.html").read_text(encoding="utf-8")
    assert page.count('class="episode-play has-cover"') == 2
    assert 'data-cover="/assets/podcasts/covers/' in page

    assert sync_podcasts.sync()["files"] == []  # unchanged covers are not rewritten

    _jpeg(pod_site / "ep2.jpg", "green")
    r = sync_podcasts.sync()
    assert r["updated"] == ["Wem gehört Berlin?"] and len(r["files"]) == 1


def test_podcast_sync_deletes_cover_of_removed_episode(pod_site):
    feed = pod_site / "feed.xml"
    img = _jpeg(pod_site / "show.jpg", "navy")
    xml = feed.read_text(encoding="utf-8").replace(
        "<language>de-de</language>", f'<language>de-de</language>\n  <itunes:image href="{img}"/>')
    feed.write_text(xml, encoding="utf-8")
    sync_podcasts.sync()
    gone = sync_podcasts.cover_path({"guid": "ep-1"})
    assert os.path.exists(gone)
    start = xml.index("<item>\n    <title>ماذا")
    feed.write_text(xml[:start] + xml[xml.index("</item>", start) + len("</item>"):], encoding="utf-8")
    r = sync_podcasts.sync()
    assert not os.path.exists(gone)
    assert os.path.relpath(gone, pod_site) in r["files"]


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
    # What YouTube currently says per id; unknown ids answer like a bot check.
    watch = {v["id"]: {"status": "ok", "duration": v["duration"], "date": v["date"],
                       "title": v["title"], "description": v["description"]} for v in known}
    monkeypatch.setattr(sync_videos, "watch_info", lambda vid: dict(watch.get(vid) or {
        "status": "unknown", "duration": 0, "date": "", "title": vid, "description": ""}))
    return tmp_path, feed, watch


def _videos(root):
    return {v["id"]: v for v in json.loads((root / "assets" / "media" / "videos.json").read_text())["videos"]}


def test_video_sync_without_new_uploads_changes_nothing(vid_site):
    sync_videos.sync()  # normalise the copied page once
    assert sync_videos.sync()["files"] == []


def test_video_sync_adds_new_upload(vid_site, monkeypatch):
    root, feed, watch = vid_site
    feed.insert(0, {"id": "NEWVIDEO123", "title": "Neues Video #berlin #medien",
                    "date": "2026-10-27", "description": "Erster Absatz.\n\nwww.zwischenwelten-berlin.de"})
    watch["NEWVIDEO123"] = {"status": "ok", "duration": 125, "date": "2026-10-27",
                            "title": "", "description": ""}
    monkeypatch.setattr(sync_videos, "is_short", lambda vid: False)
    r = sync_videos.sync()
    assert r["added"] == ["Neues Video"]
    assert sorted(r["files"]) == ["assets/media/videos.json", "videos.html"]
    page = (root / "videos.html").read_text(encoding="utf-8")
    assert 'data-yt="NEWVIDEO123"' in page and "Erster Absatz." in page
    assert '<span class="video-duration">2:05</span>' in page
    assert _videos(root)["NEWVIDEO123"]["source"] == {"title": "Neues Video", "description": "Erster Absatz."}


def test_video_sync_records_source_but_keeps_older_hand_edits(vid_site):
    root, feed, watch = vid_site
    data_path = root / "assets" / "media" / "videos.json"
    data = json.loads(data_path.read_text())
    for v in data["videos"]:  # an entry from before "source" existed, edited by hand
        v.pop("source", None)
        if v["id"] == "T50Ep0B75wk":
            v["title"] = "Wer wir sind – und wie wir arbeiten"
    data_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    watch["T50Ep0B75wk"]["title"] = "Zwischenwelten Medienprojekt"
    r = sync_videos.sync()
    v = _videos(root)["T50Ep0B75wk"]
    assert v["title"] == "Wer wir sind – und wie wir arbeiten"
    assert v["source"]["title"] == "Zwischenwelten Medienprojekt"
    assert r["updated"] == [] and r["removed"] == []


def test_video_sync_follows_youtube_edits(vid_site):
    root, feed, watch = vid_site
    sync_videos.sync()  # record "source" for every video
    data_path = root / "assets" / "media" / "videos.json"
    data = json.loads(data_path.read_text())
    for v in data["videos"]:
        if v["id"] == "1fvlYqL5SLA":
            v["title"] = "Von Hand geändert"
            v["description"] = "Beschreibung von Hand"
        if v["id"] == "yzbi8As-Kh4":
            v["title"] = "Titel von Hand"
    data_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    watch["9NjMJKKekcg"].update(title="Medienpreis 2026 – neu #berlin", duration=75,
                                description="Neue Beschreibung.\n\nhttps://example.org")
    watch["1fvlYqL5SLA"].update(title="YouTube-Titel neu", description="YouTube-Beschreibung neu")
    r = sync_videos.sync()
    videos = _videos(root)
    assert videos["9NjMJKKekcg"]["title"] == "Medienpreis 2026 – neu"
    assert videos["9NjMJKKekcg"]["description"] == "Neue Beschreibung."
    assert videos["9NjMJKKekcg"]["duration"] == 75
    assert videos["9NjMJKKekcg"]["kicker"] == "Medienpreis"
    # a title changed on YouTube wins over a hand edit; a description does not
    assert videos["1fvlYqL5SLA"]["title"] == "YouTube-Titel neu"
    assert videos["1fvlYqL5SLA"]["description"] == "Beschreibung von Hand"
    assert videos["1fvlYqL5SLA"]["source"]["description"] == "YouTube-Beschreibung neu"
    # a hand-edited title stays while YouTube's title is unchanged
    assert videos["yzbi8As-Kh4"]["title"] == "Titel von Hand"
    assert sorted(r["updated"]) == ["Medienpreis 2026 – neu", "YouTube-Titel neu"]
    page = (root / "videos.html").read_text(encoding="utf-8")
    assert "Medienpreis 2026 – neu" in page and "Neue Beschreibung." in page


def test_video_sync_hides_deleted_video_and_brings_it_back(vid_site):
    root, feed, watch = vid_site
    sync_videos.sync()
    watch["yzbi8As-Kh4"]["status"] = "gone"
    r = sync_videos.sync()
    assert r["removed"] == ["Zwischenwelten Berlin"]
    assert _videos(root)["yzbi8As-Kh4"]["gone"] is True
    assert 'data-yt="yzbi8As-Kh4"' not in (root / "videos.html").read_text(encoding="utf-8")
    assert sync_videos.sync()["files"] == []  # stays gone quietly
    watch["yzbi8As-Kh4"]["status"] = "ok"
    r = sync_videos.sync()
    assert r["updated"] == ["Zwischenwelten Berlin"] and "gone" not in _videos(root)["yzbi8As-Kh4"]
    assert 'data-yt="yzbi8As-Kh4"' in (root / "videos.html").read_text(encoding="utf-8")


def test_video_sync_ignores_pages_it_does_not_understand(vid_site):
    root, feed, watch = vid_site
    sync_videos.sync()
    watch.clear()  # every watch page now looks like a bot check
    assert sync_videos.sync()["files"] == []


def test_parse_watch_page():
    ok = ('<meta name="title" content="Titel &amp; mehr">"playabilityStatus":{"status":"OK"}'
          '"lengthSeconds":"61""shortDescription":"Zeile 1\\nZeile \\"2\\""')
    info = sync_videos.parse_watch_page(ok)
    assert info["status"] == "ok" and info["title"] == "Titel & mehr" and info["duration"] == 61
    assert info["description"] == 'Zeile 1\nZeile "2"'
    gone = '<meta name="title" content="">"playabilityStatus":{"status":"ERROR","reason":"Dieses Video ist nicht verfügbar"}'
    assert sync_videos.parse_watch_page(gone)["status"] == "gone"
    private = '"playabilityStatus":{"status":"LOGIN_REQUIRED","reason":"Dieses Video ist privat"}'
    assert sync_videos.parse_watch_page(private)["status"] == "gone"
    assert sync_videos.parse_watch_page("<html>Bevor Sie zu YouTube weitergehen</html>")["status"] == "unknown"


def test_save_thumb_replaces_only_changed_images(tmp_path, monkeypatch):
    monkeypatch.setattr(sync_videos, "THUMBS", str(tmp_path))
    monkeypatch.setattr(sync_videos, "_shrink", lambda data, width: data)
    image = {"bytes": b"one"}
    monkeypatch.setattr(sync_videos, "_get", lambda url, raw=False: image["bytes"])
    video = {"id": "abc", "kind": "video"}
    assert sync_videos.save_thumb(video) is True
    assert sync_videos.save_thumb(video) is False
    image["bytes"] = b"two"
    assert sync_videos.save_thumb(video) is True
    assert (tmp_path / "abc.jpg").read_bytes() == b"two"


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
