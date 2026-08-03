import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from manuscript_import import html_to_md, detect_lang


# ---- html_to_md ---------------------------------------------------------

def test_headings():
    md, _ = html_to_md("<h1>Titel</h1><h2>Sub</h2><h3>Tief</h3><h4>Tiefer</h4>")
    assert md == "# Titel\n\n## Sub\n\n### Tief\n\n### Tiefer"

def test_second_h1_demoted():
    md, _ = html_to_md("<h1>Titel</h1><p>x</p><h1>Noch eins</h1>")
    assert md == "# Titel\n\nx\n\n## Noch eins"

def test_paragraph_emphasis():
    md, _ = html_to_md("<p>Ein <strong>fettes</strong> und <em>kursives</em> Wort.</p>")
    assert md == "Ein **fettes** und *kursives* Wort."

def test_unordered_list():
    md, _ = html_to_md("<ul><li>eins</li><li>zwei <strong>fett</strong></li></ul>")
    assert md == "- eins\n- zwei **fett**"

def test_ordered_list_degrades_to_bullets():
    md, _ = html_to_md("<ol><li>erstens</li><li>zweitens</li></ol>")
    assert md == "- erstens\n- zweitens"

def test_blockquote_with_paragraphs():
    md, _ = html_to_md("<blockquote><p>Weise Worte.</p><p>Noch mehr.</p></blockquote>")
    assert md == "> Weise Worte.\n> Noch mehr."

def test_blockquote_bare_text():
    md, _ = html_to_md("<blockquote>Weise Worte.</blockquote>")
    assert md == "> Weise Worte."

def test_link():
    md, _ = html_to_md('<p>Siehe <a href="https://x.de">hier</a>.</p>')
    assert md == "Siehe [hier](https://x.de)."

def test_table():
    md, _ = html_to_md(
        "<table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>")
    assert md == "| A | B |\n| --- | --- |\n| 1 | 2 |"

def test_image_dropped_with_warning():
    md, warnings = html_to_md('<p>Davor</p><img src="data:image/png;base64,xx"><p>Danach</p>')
    assert md == "Davor\n\nDanach"
    assert any("Bild" in w or "image" in w.lower() for w in warnings)

def test_whitespace_collapsed():
    md, _ = html_to_md("<p>Ein\n   Wort\n mehr</p>")
    assert md == "Ein Wort mehr"

def test_empty_input():
    md, _ = html_to_md("  <p>  </p> ")
    assert md == ""

def test_unknown_tags_keep_text():
    md, _ = html_to_md("<p><span>Text in</span> <sup>Spans</sup></p>")
    assert md == "Text in Spans"


# ---- detect_lang --------------------------------------------------------

def test_detect_de():
    assert detect_lang("Das ist ein Text über die Stadt und das Leben der Menschen.") == "de"

def test_detect_en():
    assert detect_lang("This is a text about the city and the people who live in it.") == "en"

def test_detect_tr():
    assert detect_lang("Bu, şehir ve içinde yaşayan insanlar hakkında bir yazı.") == "tr"

def test_detect_ku():
    assert detect_lang("Ev nivîsek e li ser bajar û mirovên ku lê dijîn.") == "ku"

def test_detect_ru():
    assert detect_lang("Это текст о городе и людях, которые в нём живут.") == "ru"

def test_detect_uk():
    assert detect_lang("Це текст про місто і людей, які в ньому живуть.") == "uk"

def test_detect_ar():
    assert detect_lang("هذا نص عن المدينة والناس الذين يعيشون فيها.") == "ar"

def test_detect_fa():
    assert detect_lang("این متنی درباره شهر و مردمی است که در آن زندگی می‌کنند.") == "fa"

def test_detect_default_de():
    assert detect_lang("xyzzy 123") == "de"
