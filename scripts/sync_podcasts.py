"""Keep /podcasts in step with the podcast's RSS feed.

    python3 scripts/sync_podcasts.py              # read the feed, then render
    python3 scripts/sync_podcasts.py --offline    # only re-render from the JSON

assets/media/podcasts.json is the source of truth: "feed" is the hoster's
public RSS address, "links" the Spotify/Apple/YouTube pages for the
subscribe buttons. Every feed item becomes an episode keyed by its <guid>;
title, audio address, date and duration follow the feed on every sync, while
"lang", "guests", "summary" and "hidden" are editorial and never overwritten.
podcasts.html is rewritten only between its <!-- PODCASTS:… --> markers; the
first real sync replaces the placeholder episodes and the preview notice.
"""
import argparse
import email.utils
import html
import json
import os
import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from publish_post import LANGS
from manuscript_import import detect_lang
from sync_videos import SyncError, fmt_date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "assets", "media", "podcasts.json")
PAGE = os.path.join(ROOT, "podcasts.html")

NS = {"itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
      "content": "http://purl.org/rss/1.0/modules/content/"}
UA = {"User-Agent": "Mozilla/5.0 (zwischenwelten.berlin podcast sync)"}
EDITORIAL = ("lang", "guests", "summary", "hidden")


# --------------------------------------------------------------------------
# Feed
# --------------------------------------------------------------------------
def fetch_feed(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20) as r:
        return r.read()


def parse_duration(text):
    """itunes:duration is either seconds or [HH:]MM:SS."""
    text = (text or "").strip()
    if not text:
        return 0
    parts = [int(p) for p in text.split(":") if p.isdigit()]
    total = 0
    for p in parts:
        total = total * 60 + p
    return total


def plain_text(markup):
    text = re.sub(r"<br\s*/?>|</p>", "\n", markup or "", flags=re.I)
    text = html.unescape(re.sub(r"<[^>]+>", "", text))
    return re.sub(r"[ \t]+", " ", text).strip()


def first_paragraph(text):
    return next((p.strip() for p in re.split(r"\n\s*\n|\n", text) if p.strip()), "")


def parse_feed(xml_bytes):
    """Episodes from an RSS 2.0 podcast feed, newest first, plus the feed's
    own language (two letters, "" if absent)."""
    channel = ET.fromstring(xml_bytes).find("channel")
    if channel is None:
        raise SyncError("Die Feed-Adresse liefert keinen Podcast-Feed (RSS).")
    feed_lang = (channel.findtext("language") or "")[:2].lower()
    episodes = []
    for item in channel.findall("item"):
        enclosure = item.find("enclosure")
        if enclosure is None or not enclosure.get("url"):
            continue  # trailers or posts without audio
        guid = (item.findtext("guid") or enclosure.get("url")).strip()
        date = item.findtext("pubDate")
        try:
            date = email.utils.parsedate_to_datetime(date).date().isoformat() if date else ""
        except (TypeError, ValueError):
            date = ""
        desc = (item.findtext("itunes:summary", namespaces=NS)
                or item.findtext("description") or "")
        number = item.findtext("itunes:episode", namespaces=NS)
        episodes.append({
            "guid": guid,
            "title": (item.findtext("itunes:title", namespaces=NS)
                      or item.findtext("title") or "").strip(),
            "number": int(number) if number and number.strip().isdigit() else None,
            "date": date,
            "duration": parse_duration(item.findtext("itunes:duration", namespaces=NS)),
            "src": enclosure.get("url"),
            "description": first_paragraph(plain_text(desc)),
        })
    episodes.sort(key=lambda e: e["date"], reverse=True)
    return episodes, feed_lang


def merge(existing, fresh, feed_lang):
    """Feed fields from `fresh`, editorial fields from `existing` (by guid).
    Episodes the feed no longer lists are dropped."""
    old = {e["guid"]: e for e in existing}
    merged, added = [], []
    for ep in fresh:
        prev = old.get(ep["guid"])
        if prev:
            for key in EDITORIAL:
                if key in prev:
                    ep[key] = prev[key]
        else:
            guess = detect_lang(ep["title"] + "\n" + ep["description"])
            ep["lang"] = guess if guess != "de" or not feed_lang else feed_lang
            if ep["lang"] not in LANGS:
                ep["lang"] = "de"
            ep["guests"] = []
            added.append(ep["title"])
        merged.append(ep)
    return merged, added


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------
PLAY = ('<svg class="icon-play" viewBox="0 0 24 24" width="{s}" height="{s}" fill="currentColor" '
        'aria-hidden="true" focusable="false"><path d="M8 5v14l11-7z"/></svg>')
PAUSE = ('<svg class="icon-pause" viewBox="0 0 24 24" width="{s}" height="{s}" fill="currentColor" '
         'aria-hidden="true" focusable="false"><path d="M6 5h4v14H6zM14 5h4v14h-4z"/></svg>')
SUBSCRIBE = [("spotify", "Spotify"), ("apple", "Apple Podcasts"), ("youtube", "YouTube Music")]


def fmt_clock(sec):
    h, rest = divmod(sec, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def episode(ep, featured=False):
    e = html.escape
    lang = ep.get("lang") or "de"
    dir_attr = ' dir="rtl"' if LANGS.get(lang, {}).get("rtl") else ""
    title = ep["title"]
    label = f"Folge {ep['number']}" if ep.get("number") else ""
    full_title = f"{label}: {title}" if label else title
    meta = [label, fmt_date(ep["date"]) if ep.get("date") else ""]
    if featured and ep.get("duration"):
        meta.append(f"{round(ep['duration'] / 60)} Min.")
    meta.append(LANGS.get(lang, {}).get("label", lang))
    icon = 28 if featured else 22
    out = [
        f'<li class="episode{" is-featured" if featured else ""}" data-lang="{e(lang)}" lang="{e(lang)}"'
        f'{dir_attr} data-src="{e(ep["src"])}"'
        f' data-duration="{ep.get("duration") or 0}" data-title="{e(full_title)}">',
        f'  <button type="button" class="episode-play" aria-label="Abspielen: {e(full_title)}">',
        f"    {PLAY.format(s=icon)}",
        f"    {PAUSE.format(s=icon)}",
        "  </button>",
        "  <div>",
        f'    <p class="episode-meta" lang="de" dir="ltr">{e(" · ".join(x for x in meta if x))}</p>',
        f'    <h3 class="episode-title">{e(title)}</h3>',
    ]
    summary = ep.get("summary") or ep.get("description")
    if summary:
        out.append(f'    <p class="episode-desc">{e(summary)}</p>')
    guests = ep.get("guests") or []
    if guests:
        names = ", ".join(
            f'<a href="{e(g["href"])}">{e(g["name"])}</a>' if g.get("href") else e(g["name"])
            for g in guests)
        out.append(f'    <p class="episode-guests" lang="de" dir="ltr">Zu Gast: {names}</p>')
    out.append("  </div>")
    if not featured and ep.get("duration"):
        out.append(f'  <span class="episode-duration">{fmt_clock(ep["duration"])}</span>')
    out.append("</li>")
    return out


def subscribe(data):
    out = []
    for key, name in SUBSCRIBE:
        url = (data.get("links") or {}).get(key)
        if url:
            out.append(f'<a class="btn-ghost" href="{html.escape(url)}" target="_blank" rel="noopener">{name}</a>')
    out.append(f'<a class="btn-ghost" href="{html.escape(data["feed"])}">RSS-Feed</a>')
    return out


def _indent(lines, n):
    return "\n".join((" " * n + l) if l else l for l in lines)


def render(data):
    visible = [ep for ep in data["episodes"] if not ep.get("hidden")]
    blocks = {
        "NOTICE": [],
        "SUBSCRIBE": subscribe(data),
        "FEATURED": episode(visible[0], featured=True) if visible else [],
        "EPISODES": [l for ep in visible[1:] for l in episode(ep)],
    }
    with open(PAGE, encoding="utf-8") as fh:
        page = fh.read()
    for name, lines in blocks.items():
        pattern = re.compile(rf"([ \t]*)<!-- PODCASTS:{name} -->\n.*?<!-- /PODCASTS:{name} -->", re.S)
        m = pattern.search(page)
        if not m:
            raise SyncError(f"podcasts.html: Markierung PODCASTS:{name} fehlt")
        pad = m.group(1)
        body = _indent(lines, len(pad))
        repl = f"{pad}<!-- PODCASTS:{name} -->\n{body + chr(10) if body else ''}{pad}<!-- /PODCASTS:{name} -->"
        page = page[:m.start()] + repl + page[m.end():]
    with open(PAGE, "w", encoding="utf-8") as fh:
        fh.write(page)
    return len(visible)


# --------------------------------------------------------------------------
def _read(path):
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except FileNotFoundError:
        return None


def sync(offline=False):
    """Read the feed (unless `offline`) and re-render podcasts.html. Returns
    {"added": [titles], "files": [repo-relative changed paths], "count": n}."""
    tracked = [DATA, PAGE]
    before = {p: _read(p) for p in tracked}
    with open(DATA, encoding="utf-8") as fh:
        data = json.load(fh)
    if not (data.get("feed") or "").strip():
        raise SyncError("Es ist noch kein Podcast-Feed eingetragen. Die RSS-Adresse des "
                        "Podcast-Hosters gehört in assets/media/podcasts.json unter \"feed\".")
    added = []
    if not offline:
        try:
            fresh, feed_lang = parse_feed(fetch_feed(data["feed"]))
        except (urllib.error.URLError, OSError) as e:
            raise SyncError(f"Der Podcast-Feed ist gerade nicht erreichbar ({e}). "
                            "Bitte später noch einmal versuchen.") from e
        except ET.ParseError as e:
            raise SyncError(f"Der Podcast-Feed ist kein gültiges RSS ({e}).") from e
        if not fresh:
            raise SyncError("Der Podcast-Feed enthält noch keine Folge mit Audiodatei.")
        data["episodes"], added = merge(data.get("episodes", []), fresh, feed_lang)
        with open(DATA, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
    count = render(data)
    changed = [p for p in tracked if _read(p) != before[p]]
    return {"added": added, "count": count,
            "files": [os.path.relpath(p, ROOT) for p in changed]}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--offline", action="store_true", help="nichts herunterladen, nur neu rendern")
    args = ap.parse_args(argv)
    try:
        r = sync(offline=args.offline)
    except SyncError as e:
        raise SystemExit(str(e))
    for title in r["added"]:
        print(f"+ neu: {title}")
    print(f"podcasts.html aktualisiert ({r['count']} Folgen, {len(r['files'])} Dateien geändert)")


if __name__ == "__main__":
    main()
