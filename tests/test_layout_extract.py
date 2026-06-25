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
