import fitz
from pdftranslator.core import layout


def test_extract_units_finds_lines():
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Hello world", fontsize=12)
    page.insert_text((72, 100), "Second line", fontsize=12)

    units = layout.extract_units(page)

    texts = [u.text.strip() for u in units]
    assert "Hello world" in texts
    assert "Second line" in texts
    for u in units:
        assert u.size > 0
        assert len(u.bbox) == 4
    doc.close()


def test_extract_units_skips_blank_lines():
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "   ", fontsize=12)
    units = layout.extract_units(page)
    assert units == []
    doc.close()


def test_extract_dehyphenates_and_joins_block():
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    # A single text block whose lines break a word with a soft hyphen.
    page.insert_text((72, 100), "recep-\ntors detect a fine vibra-\ntion.", fontsize=11)
    units = layout.extract_units(page)
    joined = " ".join(u.text for u in units)
    assert "receptors" in joined  # soft hyphen removed, word rejoined
    assert "vibration" in joined
    assert "recep-" not in joined
    doc.close()


def test_numeric_only_blocks_are_left_untouched():
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), "42", fontsize=11)          # standalone number
    page.insert_text((72, 140), "40–60", fontsize=11)  # numeric range
    page.insert_text((72, 180), "Hello world", fontsize=11)  # real text
    units = layout.extract_units(page)
    joined = " ".join(u.text for u in units)
    # numbers are not extracted for translation; only the real text is a unit
    assert "Hello world" in joined
    assert "42" not in joined and "40" not in joined

    # after the full rewrite the numbers survive verbatim, the text is replaced
    layout.redact_units(page, units)
    layout.insert_translations(page, units, ["你好世界"], "zh")
    after = page.get_text("text")
    assert "42" in after and "40" in after and "60" in after  # numbers untouched
    assert "Hello" not in after                       # text was translated/redacted
    doc.close()


def test_is_noop_translation_keeps_untranslatable_lists():
    # A product/code list returns the same alphanumeric tokens → keep original
    # (preserves ®, exact format).
    assert layout.is_noop_translation(
        "Pladur® N 10, Pladur® N 13", "Pladur® N 10、Pladur® N 13"
    )
    # A genuine sentence translation replaces the words → not a noop.
    assert not layout.is_noop_translation("Hello world friends", "你好世界朋友")
    # Too little content to judge → translate normally.
    assert not layout.is_noop_translation("OMNIA", "OMNIA")


def test_extract_detects_bold_and_italic():
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), "Bold heading", fontsize=14, fontname="hebo")   # Helvetica-Bold
    page.insert_text((72, 140), "Italic note", fontsize=12, fontname="heit")    # Helvetica-Oblique
    page.insert_text((72, 180), "Plain words", fontsize=12, fontname="helv")
    us = layout.extract_units(page)
    bold = next(u for u in us if "Bold" in u.text)
    ital = next(u for u in us if "Italic" in u.text)
    plain = next(u for u in us if "Plain" in u.text)
    assert bold.bold and not bold.italic
    assert ital.italic and not ital.bold
    assert not plain.bold and not plain.italic
    doc.close()
