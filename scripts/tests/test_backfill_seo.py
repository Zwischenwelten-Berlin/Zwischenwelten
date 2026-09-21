import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import backfill_seo

POST = """<html lang="tr">
<head>
  <title>Keine Panik – ZWISCHENWELTEN</title>
  <meta name="description" content="Bir &quot;sürgün&quot; hikayesi.">

  <link rel="icon" href="/favicon.ico">

  <meta property="og:type" content="article">
  <meta property="og:title" content="Keine Panik">
  <meta property="og:description" content="Bir &quot;sürgün&quot; hikayesi.">
  <meta property="og:image" content="https://zwischenwelten.berlin/assets/blog/keine-panik-cover.png">

  <link rel="stylesheet" href="/assets/fonts.css">
  <script type="application/ld+json">
  {"image":"https://zwischenwelten.berlin/assets/blog/keine-panik-cover.png"}
  </script>
</head>
<body>
              <img src="/assets/blog/keine-panik-cover.png" alt="Keine Panik" width="1536" height="1024">
</body></html>"""

COVER = {"width": 1536, "height": 1024, "widths": [800, 1536]}


def test_post_head_gains_canonical_og_url_and_twitter_card():
    out = backfill_seo.upsert_post_head(POST, "keine-panik")
    url = "https://zwischenwelten.berlin/aktuelles/keine-panik"
    assert f'<link rel="canonical" href="{url}">' in out
    assert f'<meta property="og:url" content="{url}">' in out
    assert '<meta name="twitter:card" content="summary_large_image">' in out
    assert '<meta name="twitter:title" content="Keine Panik">' in out
    # values are copied as they stand — already-escaped text is not escaped twice
    assert '<meta name="twitter:description" content="Bir &quot;sürgün&quot; hikayesi.">' in out
    assert out.index('rel="canonical"') < out.index('rel="icon"')


def test_post_head_upsert_is_idempotent():
    once = backfill_seo.upsert_post_head(POST, "keine-panik")
    assert backfill_seo.upsert_post_head(once, "keine-panik") == once


def test_cover_refs_switch_to_jpg_and_img_gets_srcset():
    out = backfill_seo.upgrade_cover_refs(POST, "keine-panik", COVER, "SIZES")
    assert "keine-panik-cover.png" not in out
    assert out.count("https://zwischenwelten.berlin/assets/blog/keine-panik-cover.jpg") == 2
    assert ('<img src="/assets/blog/keine-panik-cover.jpg" alt="Keine Panik" '
            'width="1536" height="1024" '
            'srcset="/assets/blog/keine-panik-cover-800.webp 800w, '
            '/assets/blog/keine-panik-cover-1536.webp 1536w" sizes="SIZES">') in out


def test_cover_refs_update_dimensions_when_the_image_was_scaled_down():
    html = POST.replace('width="1536" height="1024"', 'width="3072" height="2048"')
    out = backfill_seo.upgrade_cover_refs(html, "keine-panik", COVER, "SIZES")
    assert 'width="1536" height="1024"' in out
    assert "3072" not in out


def test_cover_refs_leave_other_posts_alone_and_are_idempotent():
    html = POST + '<img src="/assets/blog/keine-panik-de-cover.png" alt="x" width="1" height="1">'
    once = backfill_seo.upgrade_cover_refs(html, "keine-panik", COVER, "SIZES")
    assert "/assets/blog/keine-panik-de-cover.png" in once
    assert backfill_seo.upgrade_cover_refs(once, "keine-panik", COVER, "SIZES") == once


def test_add_canonical_only_when_missing():
    out = backfill_seo.add_canonical(POST, "https://zwischenwelten.berlin/kontakt")
    assert '<link rel="canonical" href="https://zwischenwelten.berlin/kontakt">' in out
    assert backfill_seo.add_canonical(out, "https://example.invalid/") == out
