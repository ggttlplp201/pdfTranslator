from pdftranslator.core import fonts


def test_chinese_uses_builtin_cjk_font():
    assert fonts.font_for_language("zh") == "china-s"


def test_latin_targets_use_helvetica():
    assert fonts.font_for_language("en") == "helv"
    assert fonts.font_for_language("pt") == "helv"
