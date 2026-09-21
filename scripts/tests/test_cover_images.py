import os
import sys

import pytest
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import cover_images


def make_image(path, size, mode="RGB", color=(200, 30, 30)):
    Image.new(mode, size, color).save(path)
    return str(path)


def test_plan_scales_large_source_down_to_max_width(tmp_path):
    src = make_image(tmp_path / "big.png", (3200, 1600))
    plan = cover_images.plan(src)
    assert (plan["width"], plan["height"]) == (1600, 800)
    assert plan["widths"] == [800, 1600]


def test_plan_never_upscales(tmp_path):
    src = make_image(tmp_path / "mid.png", (1200, 600))
    plan = cover_images.plan(src)
    assert (plan["width"], plan["height"]) == (1200, 600)
    assert plan["widths"] == [800, 1200]


def test_plan_small_source_has_single_variant(tmp_path):
    src = make_image(tmp_path / "small.png", (640, 480))
    plan = cover_images.plan(src)
    assert plan["widths"] == [640]


def test_write_set_creates_jpg_and_webp_variants(tmp_path):
    src = make_image(tmp_path / "big.png", (3200, 1600))
    out = tmp_path / "blog"
    out.mkdir()
    written = cover_images.write_set(src, "mein-beitrag", str(out))

    assert sorted(os.listdir(out)) == [
        "mein-beitrag-cover-1600.webp",
        "mein-beitrag-cover-800.webp",
        "mein-beitrag-cover.jpg",
    ]
    assert sorted(os.path.basename(p) for p in written) == sorted(os.listdir(out))
    with Image.open(out / "mein-beitrag-cover.jpg") as im:
        assert im.format == "JPEG" and im.size == (1600, 800)
    with Image.open(out / "mein-beitrag-cover-800.webp") as im:
        assert im.format == "WEBP" and im.size == (800, 400)


def test_write_set_flattens_transparency_onto_white(tmp_path):
    src = make_image(tmp_path / "alpha.png", (900, 600), mode="RGBA", color=(0, 0, 0, 0))
    out = tmp_path / "blog"
    out.mkdir()
    cover_images.write_set(src, "p", str(out))
    with Image.open(out / "p-cover.jpg") as im:
        r, g, b = im.convert("RGB").getpixel((10, 10))
    assert min(r, g, b) > 245          # white, not the black JPEG default


def test_write_set_replaces_stale_files_of_the_same_slug_only(tmp_path):
    out = tmp_path / "blog"
    out.mkdir()
    (out / "p-cover.png").write_bytes(b"old")
    (out / "p-cover-1600.webp").write_bytes(b"old")
    (out / "p-de-cover.png").write_bytes(b"other post")
    src = make_image(tmp_path / "mid.png", (1200, 600))

    cover_images.write_set(src, "p", str(out))

    assert sorted(os.listdir(out)) == [
        "p-cover-1200.webp", "p-cover-800.webp", "p-cover.jpg", "p-de-cover.png"]


def test_write_set_accepts_the_repo_cover_itself_as_source(tmp_path):
    out = tmp_path / "blog"
    out.mkdir()
    src = make_image(out / "p-cover.jpg", (2000, 1000))
    cover_images.write_set(src, "p", str(out))
    with Image.open(out / "p-cover.jpg") as im:
        assert im.size == (1600, 800)


def test_existing_reports_files_and_widths(tmp_path):
    out = tmp_path / "blog"
    out.mkdir()
    assert cover_images.existing("p", str(out)) is None
    cover_images.write_set(make_image(tmp_path / "s.png", (3200, 1600)), "p", str(out))
    (out / "p-de-cover-800.webp").write_bytes(b"other post")

    found = cover_images.existing("p", str(out))

    assert (found["width"], found["height"]) == (1600, 800)
    assert found["widths"] == [800, 1600]
    assert sorted(os.path.basename(p) for p in found["files"]) == [
        "p-cover-1600.webp", "p-cover-800.webp", "p-cover.jpg"]


def test_img_attrs_builds_srcset_from_widths():
    attrs = cover_images.img_attrs("p", [800, 1600], "SIZES")
    assert attrs == (' srcset="/assets/blog/p-cover-800.webp 800w, '
                     '/assets/blog/p-cover-1600.webp 1600w" sizes="SIZES"')


def test_unreadable_image_raises_cover_error(tmp_path):
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not an image")
    with pytest.raises(cover_images.CoverError):
        cover_images.plan(str(bad))
