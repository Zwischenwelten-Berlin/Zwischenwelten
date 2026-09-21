"""Cover image optimisation for blog posts.

Every post's cover is stored as one JPEG plus WebP variants:

    <slug>-cover.jpg            at most MAX_W wide — the <img src>, og:image
    <slug>-cover-<width>.webp   one per entry in plan()["widths"] — the srcset

The JPEG stays the canonical file because some social-media crawlers still
cannot read WebP. Variant file names carry their real pixel width, so the
srcset can be rebuilt from a directory listing alone (see existing()).
"""
import glob
import os
import re

MAX_W = 1600
SMALL_W = 800
JPEG_QUALITY = 82
WEBP_QUALITY = 80


class CoverError(Exception):
    pass


def _pil():
    try:
        from PIL import Image, ImageOps
    except ImportError:
        raise CoverError(
            "Das Paket 'Pillow' fehlt. Bitte die Publish-App neu starten "
            "(sie installiert es selbst) oder 'pip install Pillow' ausführen.")
    return Image, ImageOps


def _open(src):
    Image, ImageOps = _pil()
    try:
        im = Image.open(src)
        im.load()
    except Exception as e:                      # noqa: BLE001 — PIL raises many types
        raise CoverError(f"Titelbild konnte nicht gelesen werden: {e}")
    # Phone photos are often stored sideways with an EXIF rotation flag.
    return ImageOps.exif_transpose(im)


def _widths(width):
    return sorted({min(SMALL_W, width), width})


def _plan_for(im):
    w, h = im.size
    if w > MAX_W:
        w, h = MAX_W, round(h * MAX_W / w)
    return {"width": w, "height": h, "widths": _widths(w)}


def plan(src):
    """Size of the JPEG and widths of the WebP variants write_set() would
    produce for src — without writing anything (used by previews)."""
    return _plan_for(_open(src))


def _variant_re(slug):
    return re.compile(re.escape(slug) + r"-cover-(\d+)\.webp$")


def all_files(slug, img_dir):
    """Every cover file that belongs to exactly this slug ('p', not 'p-de')."""
    files = glob.glob(os.path.join(img_dir, f"{slug}-cover.*"))
    rx = _variant_re(slug)
    files += [p for p in glob.glob(os.path.join(img_dir, f"{slug}-cover-*.webp"))
              if rx.match(os.path.basename(p))]
    return sorted(files)


def write_set(src, slug, img_dir):
    """Write the JPEG + WebP set for slug from src and remove any other cover
    file of that slug (an old .png, variants of a previous, wider cover).
    src may be the slug's own current cover. Returns the paths written."""
    Image, _ = _pil()
    im = _open(src)
    if im.mode in ("RGBA", "LA", "P"):
        # JPEG has no alpha channel; without this transparent areas turn black.
        rgba = im.convert("RGBA")
        flat = Image.new("RGB", rgba.size, (255, 255, 255))
        flat.paste(rgba, mask=rgba.split()[-1])
        im = flat
    else:
        im = im.convert("RGB")

    p = _plan_for(im)
    if im.size[0] != p["width"]:
        im = im.resize((p["width"], p["height"]), Image.LANCZOS)

    stale = all_files(slug, img_dir)
    written = []
    jpg = os.path.join(img_dir, f"{slug}-cover.jpg")
    # No exif= argument: metadata (GPS position, camera model) is dropped.
    im.save(jpg, "JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
    written.append(jpg)
    for width in p["widths"]:
        variant = im if width == p["width"] else im.resize(
            (width, round(p["height"] * width / p["width"])), Image.LANCZOS)
        path = os.path.join(img_dir, f"{slug}-cover-{width}.webp")
        variant.save(path, "WEBP", quality=WEBP_QUALITY, method=6)
        written.append(path)

    for path in stale:
        if path not in written:
            os.remove(path)
    return written


def existing(slug, img_dir):
    """The optimised set already on disk for slug, or None when there is no
    <slug>-cover.jpg with at least one WebP variant next to it."""
    jpg = os.path.join(img_dir, f"{slug}-cover.jpg")
    rx = _variant_re(slug)
    widths = sorted(int(rx.match(os.path.basename(p)).group(1))
                    for p in all_files(slug, img_dir)
                    if rx.match(os.path.basename(p)))
    if not os.path.exists(jpg) or not widths:
        return None
    Image, _ = _pil()
    with Image.open(jpg) as im:
        w, h = im.size
    return {"width": w, "height": h, "widths": widths,
            "files": [jpg] + [os.path.join(img_dir, f"{slug}-cover-{x}.webp")
                              for x in widths]}


def img_attrs(slug, widths, sizes):
    """The srcset/sizes attributes for an <img> showing slug's cover."""
    srcset = ", ".join(f"/assets/blog/{slug}-cover-{w}.webp {w}w" for w in widths)
    return f' srcset="{srcset}" sizes="{sizes}"'
