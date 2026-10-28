"""Keep /videos in step with the YouTube channel.

    python3 scripts/sync_videos.py              # fetch new uploads, then render
    python3 scripts/sync_videos.py --offline    # only re-render from the JSON
    python3 scripts/sync_videos.py --add ID     # add an (unlisted) video by id

assets/media/videos.json is the source of truth. New uploads from the
channel's public RSS feed (no API key) are appended there with a cleaned-up
title; kicker, description and language stay editable by hand and are never
overwritten. Thumbnails are saved to assets/videos/ so the page shows them
without contacting YouTube before consent. videos.html is rewritten only
between its <!-- VIDEOS:… --> markers.
"""
import argparse
import html
import json
import os
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "assets", "media", "videos.json")
THUMBS = os.path.join(ROOT, "assets", "videos")
PAGE = os.path.join(ROOT, "videos.html")
SITE = "https://zwischenwelten.berlin"

THUMB_W = {"video": 960, "short": 540}
NS = {"atom": "http://www.w3.org/2005/Atom",
      "yt": "http://www.youtube.com/xml/schemas/2015",
      "media": "http://search.yahoo.com/mrss/"}
UA = {"User-Agent": "Mozilla/5.0 (zwischenwelten.berlin video sync)",
      "Accept-Language": "de"}


# --------------------------------------------------------------------------
# Fetching
# --------------------------------------------------------------------------
class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def _get(url, raw=False):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20) as r:
        body = r.read()
    return body if raw else body.decode("utf-8", "replace")


def is_short(vid):
    """YouTube answers /shorts/<id> with 200 for Shorts and redirects otherwise."""
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(urllib.request.Request(f"https://www.youtube.com/shorts/{vid}", headers=UA), timeout=20) as r:
            return r.status == 200
    except urllib.error.HTTPError:
        return False


def watch_info(vid):
    page = _get(f"https://www.youtube.com/watch?v={vid}")
    length = re.search(r'"lengthSeconds":"(\d+)"', page)
    date = re.search(r'"uploadDate":"(\d{4}-\d\d-\d\d)', page)
    title = re.search(r'<meta name="title" content="([^"]*)"', page)
    desc = re.search(r'<meta name="description" content="([^"]*)"', page)
    return {
        "duration": int(length.group(1)) if length else 0,
        "date": date.group(1) if date else "",
        "title": html.unescape(title.group(1)) if title else vid,
        "description": html.unescape(desc.group(1)) if desc else "",
    }


def feed_entries(channel_id):
    xml = _get(f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}")
    out = []
    for e in ET.fromstring(xml).findall("atom:entry", NS):
        desc = e.find("media:group/media:description", NS)
        out.append({
            "id": e.findtext("yt:videoId", namespaces=NS),
            "title": e.findtext("atom:title", namespaces=NS) or "",
            "date": (e.findtext("atom:published", namespaces=NS) or "")[:10],
            "description": desc.text if desc is not None and desc.text else "",
        })
    return out


def clean_title(title):
    """Drop hashtags and the space YouTube titles often leave before ! or ?."""
    title = re.sub(r"\s*#\S+", "", title).strip()
    return re.sub(r"\s+([!?.,])", r"\1", title)


def clean_description(text):
    """First paragraph without links or hashtags, or "" if nothing is left."""
    lines = []
    for line in text.strip().splitlines():
        line = re.sub(r"https?://\S+|www\.\S+|#\S+", "", line).strip()
        if not line:
            if lines:
                break
            continue
        if line.lower().startswith(("mehr erfahren", "erfahren sie mehr", "mehr darüber")):
            continue
        lines.append(line)
    return " ".join(lines)


def new_entry(vid, title, date, description, kind, duration):
    return {
        "id": vid,
        "kind": kind,
        "title": clean_title(title),
        "date": date,
        "duration": duration,
        "lang": "de",
        "kicker": "Short" if kind == "short" else "Video",
        "description": "" if kind == "short" else clean_description(description),
    }


def save_thumb(video):
    path = os.path.join(THUMBS, f"{video['id']}.jpg")
    if os.path.exists(path):
        return False
    names = (["oar2.jpg", "hqdefault.jpg"] if video["kind"] == "short"
             else ["maxresdefault.jpg", "sddefault.jpg", "hqdefault.jpg"])
    for name in names:
        try:
            data = _get(f"https://i.ytimg.com/vi/{video['id']}/{name}", raw=True)
            break
        except urllib.error.HTTPError:
            continue
    else:
        print(f"  ! kein Vorschaubild für {video['id']}", file=sys.stderr)
        return False
    os.makedirs(THUMBS, exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)
    _shrink(path, THUMB_W[video["kind"]])
    return True


def _shrink(path, width):
    try:
        from PIL import Image
    except ImportError:
        return  # keep YouTube's original size; fine, just heavier
    with Image.open(path) as im:
        im = im.convert("RGB")
        # YouTube bakes black letter-/pillarbox bars into some thumbnails.
        box = im.convert("L").point(lambda p: 255 if p > 24 else 0).getbbox()
        if box and (box[2] - box[0] < im.width * 0.97 or box[3] - box[1] < im.height * 0.97):
            im = im.crop(box)
        if im.width > width:
            im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
        im.save(path, "JPEG", quality=82, optimize=True, progressive=True)


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------
MONTHS = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
          "August", "September", "Oktober", "November", "Dezember"]
PLAY = ('<span class="video-play" aria-hidden="true"><svg viewBox="0 0 24 24" width="22" height="22" '
        'fill="currentColor" focusable="false"><path d="M8 5v14l11-7z"/></svg></span>')


def fmt_date(iso):
    y, m, d = (int(x) for x in iso.split("-"))
    return f"{d}. {MONTHS[m - 1]} {y}"


def fmt_duration(sec):
    h, rest = divmod(sec, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def iso_duration(sec):
    m, s = divmod(sec, 60)
    return f"PT{m}M{s}S" if m else f"PT{s}S"


def thumb_size(video):
    path = os.path.join(THUMBS, f"{video['id']}.jpg")
    try:
        from PIL import Image
        with Image.open(path) as im:
            return im.size
    except Exception:
        return (540, 960) if video["kind"] == "short" else (960, 540)


def card(video, extra_class=""):
    e = html.escape
    vid, title = video["id"], video["title"]
    w, h = thumb_size(video)
    cls = "video-card" + (" is-short" if video["kind"] == "short" else "") + extra_class
    heading = "h2" if extra_class else "h3"
    meta = " · ".join(x for x in (video.get("kicker"), fmt_date(video["date"])) if x)
    out = [
        f'<article class="{cls}" data-lang="{e(video["lang"])}" lang="{e(video["lang"])}">',
        f'  <a class="video-thumb" href="https://www.youtube.com/watch?v={vid}" data-yt="{vid}"'
        f' aria-label="Video abspielen: {e(title)}">',
        f'    <img src="/assets/videos/{vid}.jpg" alt="" loading="{"eager" if extra_class else "lazy"}" width="{w}" height="{h}">',
        f'    <span class="video-duration">{fmt_duration(video["duration"])}</span>',
        f"    {PLAY}",
        "  </a>",
        '  <div class="video-info">',
        f'    <p class="video-kicker">{e(meta)}</p>',
        f'    <{heading} class="video-title">{e(title)}</{heading}>',
    ]
    if video.get("description"):
        out.append(f'    <p class="video-desc">{e(video["description"])}</p>')
    out += ["  </div>", "</article>"]
    return out


def jsonld(videos):
    items = []
    for i, v in enumerate(videos, 1):
        items.append({
            "@type": "ListItem",
            "position": i,
            "item": {
                "@type": "VideoObject",
                "name": v["title"],
                "description": v.get("description") or v["title"],
                "thumbnailUrl": f"{SITE}/assets/videos/{v['id']}.jpg",
                "uploadDate": v["date"],
                "duration": iso_duration(v["duration"]),
                "contentUrl": f"https://www.youtube.com/watch?v={v['id']}",
                "embedUrl": f"https://www.youtube-nocookie.com/embed/{v['id']}",
                "inLanguage": v["lang"],
            },
        })
    data = {"@context": "https://schema.org", "@type": "ItemList", "itemListElement": items}
    body = json.dumps(data, ensure_ascii=False, indent=2).replace("</", "<\\/")
    return ['<script type="application/ld+json">', *body.splitlines(), "</script>"]


def _indent(lines, n):
    return "\n".join((" " * n + l) if l else l for l in lines)


def render(data):
    visible = sorted((v for v in data["videos"] if not v.get("hidden")),
                     key=lambda v: (v["date"], v["id"]), reverse=True)
    featured = next((v for v in visible if v["id"] == data.get("featured")), None)
    if featured is None:
        featured = next((v for v in visible if v["kind"] == "video"), None)
    grid = [v for v in visible if v["kind"] == "video" and v is not featured]
    shorts = [v for v in visible if v["kind"] == "short"]

    blocks = {
        "FEATURED": card(featured, " is-featured") if featured else [],
        "GRID": [l for v in grid for l in card(v)],
        "SHORTS": [l for v in shorts for l in card(v)],
        "JSONLD": jsonld(visible),
    }
    with open(PAGE, encoding="utf-8") as fh:
        page = fh.read()
    for name, lines in blocks.items():
        pattern = re.compile(rf"([ \t]*)<!-- VIDEOS:{name} -->\n.*?<!-- /VIDEOS:{name} -->", re.S)
        m = pattern.search(page)
        if not m:
            raise SystemExit(f"videos.html: Markierung VIDEOS:{name} fehlt")
        pad = m.group(1)
        body = _indent(lines, len(pad))
        repl = f"{pad}<!-- VIDEOS:{name} -->\n{body + chr(10) if body else ''}{pad}<!-- /VIDEOS:{name} -->"
        page = page[:m.start()] + repl + page[m.end():]
    # The shorts row disappears entirely while there are no Shorts.
    page = re.sub(r'(<section class="section video-shorts")( hidden)?',
                  lambda m: m.group(1) + ("" if shorts else " hidden"), page)
    with open(PAGE, "w", encoding="utf-8") as fh:
        fh.write(page)
    return len(visible)


# --------------------------------------------------------------------------
class SyncError(Exception):
    """A sync that cannot run (channel unreachable, page markers missing).
    The message is German: the Publish-App shows it as is."""


def _read(path):
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except FileNotFoundError:
        return None


def sync(offline=False, add=()):
    """Fetch new uploads (unless `offline`), save thumbnails, re-render
    videos.html. Returns {"added": [titles], "files": [repo-relative paths
    that changed], "count": visible videos}."""
    tracked = [DATA, PAGE]
    before = {p: _read(p) for p in tracked}
    with open(DATA, encoding="utf-8") as fh:
        data = json.load(fh)
    known = {v["id"] for v in data["videos"]}
    added, thumbs = [], []

    if not offline:
        try:
            candidates = [(e["id"], e) for e in feed_entries(data["channel_id"])]
            candidates += [(vid, None) for vid in add]
            for vid, entry in candidates:
                if vid in known:
                    continue
                info = watch_info(vid)
                entry = entry or info
                kind = "short" if is_short(vid) else "video"
                video = new_entry(vid, entry["title"], entry["date"] or info["date"],
                                  entry["description"], kind, info["duration"])
                data["videos"].append(video)
                known.add(vid)
                added.append(video["title"])
            for v in data["videos"]:
                if save_thumb(v):
                    thumbs.append(os.path.join(THUMBS, f"{v['id']}.jpg"))
        except (urllib.error.URLError, OSError, ET.ParseError) as e:
            raise SyncError(f"YouTube ist gerade nicht erreichbar ({e}). "
                            "Bitte später noch einmal versuchen.") from e
        data["videos"].sort(key=lambda v: (v["date"], v["id"]), reverse=True)
        with open(DATA, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
            fh.write("\n")

    try:
        count = render(data)
    except SystemExit as e:
        raise SyncError(str(e)) from e
    changed = [p for p in tracked if _read(p) != before[p]] + thumbs
    return {"added": added, "count": count,
            "files": [os.path.relpath(p, ROOT) for p in changed]}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--offline", action="store_true", help="nichts herunterladen, nur neu rendern")
    ap.add_argument("--add", metavar="ID", action="append", default=[], help="Video per ID hinzufügen")
    args = ap.parse_args(argv)
    try:
        r = sync(offline=args.offline, add=args.add)
    except SyncError as e:
        raise SystemExit(str(e))
    for title in r["added"]:
        print(f"+ neu: {title}")
    print(f"videos.html aktualisiert ({r['count']} Videos, {len(r['files'])} Dateien geändert)")


if __name__ == "__main__":
    main()
