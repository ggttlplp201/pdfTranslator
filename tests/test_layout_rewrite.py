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


def test_links_preserved_after_redaction(tmp_path):
    """Links whose rects overlap a redacted text line must survive the rewrite."""
    # Build a PDF with text and a URI link over that text, then save so links
    # are accessible via page.get_links() on reload.
    src = tmp_path / "with_link.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Visit site", fontsize=12)
    data = page.get_text("dict")
    text_bbox = fitz.Rect(data["blocks"][0]["lines"][0]["bbox"])
    page.insert_link({"kind": fitz.LINK_URI, "from": text_bbox, "uri": "https://example.com"})
    doc.save(str(src))
    doc.close()

    # Open saved PDF and run the full rewrite pipeline (same path as engine.py)
    doc = fitz.open(str(src))
    page = doc[0]
    units = layout.extract_units(page)
    layout.redact_units(page, units)
    layout.insert_translations(page, units, ["Visit site"], fontname="helv")

    out = tmp_path / "out.pdf"
    doc.save(str(out))
    doc.close()

    # Verify link survived — count must be 1 (not 0, not 2)
    result = fitz.open(str(out))
    links = result[0].get_links()
    result.close()
    assert len(links) == 1, f"Expected 1 link, got {len(links)}: {links}"
    assert links[0]["uri"] == "https://example.com"


def test_fit_textbox_shrinks_long_text():
    big = layout._fit_textbox(width=200, height=20, text="short", fontname="helv", max_size=12)
    small = layout._fit_textbox(
        width=40, height=14, text="a very long paragraph that will not fit on one short line",
        fontname="helv", max_size=12,
    )
    assert big == 12
    assert small < 12
    assert small >= 4.0


def test_mixed_cjk_latin_does_not_overflow_column():
    """A long Chinese+Latin translation must stay within the original column width.

    Regression for the built-in CJK font under-measuring Latin glyphs, which let
    mixed-script lines run off the right edge of the page.
    """
    doc = fitz.open()
    page = doc.new_page()
    # An English source line occupying a fixed-width column.
    page.insert_text((72, 100), "For more examples see the docs.", fontsize=10)
    units = layout.extract_units(page)
    box_right = units[0].bbox[2]

    long_mixed = "用于纸质的 HTML 和 CSS 发布，请参阅 css4.pub 了解更多信息内容内容内容内容"
    layout.redact_units(page, units)
    layout.insert_translations(page, units, [long_mixed], fontname="china-s")

    data = page.get_text("dict")
    rights = [
        span["bbox"][2]
        for block in data["blocks"] if block.get("type") == 0
        for line in block["lines"]
        for span in line["spans"] if span["text"].strip()
    ]
    assert rights, "no translated text was inserted"
    # Inserted text must not extend past the original column's right edge.
    assert max(rights) <= box_right + 2, (max(rights), box_right)
    doc.close()
