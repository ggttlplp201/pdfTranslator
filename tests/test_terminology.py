from pdftranslator.core import terminology as T


def test_protect_and_restore_roundtrip():
    src = "Pladur® FON+ C12/25 meets EN 16516 by PLADUR GYPSUM S.A.U. (cert IACG-456-01-06-2025Arev)."
    masked, terms = T.protect(src)
    # protected spans are replaced by numeric placeholders
    assert "Pladur®" not in masked
    assert "C12/25" not in masked
    assert "EN 16516" not in masked
    assert "IACG-456-01-06-2025Arev" not in masked
    assert "S.A.U." not in masked
    assert "{0}" in masked
    # restoring puts every original span back verbatim
    assert T.restore(masked, terms) == src


def test_restore_survives_reordered_placeholders():
    # Translators may reorder placeholders; restoration is keyed by number.
    masked, terms = T.protect("Made by ACME-9 using EN 1234.")
    # simulate a translation that keeps placeholders but reorders them
    fake = "使用 {1} 由 {0} 制造。"
    out = T.restore(fake, terms)
    assert "ACME-9" in out and "EN 1234" in out


def test_plain_words_are_not_protected():
    masked, terms = T.protect("Products included in the certificate")
    assert masked == "Products included in the certificate"
    assert terms == []


def test_trademark_glyph_preserved():
    masked, terms = T.protect("Acme® and Beta™ products")
    assert T.restore(masked, terms) == "Acme® and Beta™ products"
