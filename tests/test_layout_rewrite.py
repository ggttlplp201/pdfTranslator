import fitz
from pdftranslator.core import layout


def _make_pdf_with_text_and_image():
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Hello world", fontsize=12)
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 10, 10))
    pix.clear_with(128)
    page.insert_image(fitz.Rect(200, 200, 210, 210), pixmap=pix)
    return doc, page


def test_rewrite_replaces_text_and_keeps_image():
    doc, page = _make_pdf_with_text_and_image()
    assert len(page.get_images()) == 1

    units = layout.extract_units(page)
    layout.redact_units(page, units)
    layout.insert_translations(page, units, ["Olá mundo"], fontname="helv")

    text_after = page.get_text("text")
    assert "Hello" not in text_after
    assert "Olá mundo" in text_after
    assert len(page.get_images()) == 1  # image preserved
    doc.close()


def test_fit_fontsize_shrinks_long_text():
    big = layout._fit_fontsize(width=200, height=14, text="short", fontname="helv", max_size=12)
    small = layout._fit_fontsize(
        width=40, height=14, text="a very long line that will not fit", fontname="helv", max_size=12
    )
    assert big == 12
    assert small < 12
    assert small >= 4.0
