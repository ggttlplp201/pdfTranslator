import fitz
from pdftranslator.core import ocr


def test_page_is_garbled_detects_mojibake():
    doc = fitz.open(); page = doc.new_page()
    page.insert_text((50, 50), "ß°°»²¼·¨ ¬± Ý»®¬·º·½¿¬» ×²¼±±® ß·® Ý±³º±®¬ Ù±´¼", fontsize=12)
    assert ocr.page_is_garbled(page)
    doc.close()


def test_clean_english_not_garbled():
    doc = fitz.open(); page = doc.new_page()
    page.insert_text((50, 50), "This is perfectly normal certificate text in English here.", fontsize=12)
    assert not ocr.page_is_garbled(page)
    doc.close()


def test_portuguese_accents_not_flagged():
    doc = fitz.open(); page = doc.new_page()
    page.insert_text((50, 50), "Acabamento branco com proteccao avancada para edificacao e construcao civil.", fontsize=12)
    assert not ocr.page_is_garbled(page)
    doc.close()


def test_over_text_filters_graphics():
    blocks = [(100, 100, 300, 140)]  # a text block
    assert ocr.over_text((110, 105, 290, 135), blocks)       # inside the block -> keep
    assert not ocr.over_text((100, 40, 300, 80), blocks)     # above it (title graphic) -> drop


def test_enabled_returns_bool():
    assert isinstance(ocr.enabled(), bool)
