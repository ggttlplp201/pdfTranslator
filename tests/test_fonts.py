from pathlib import Path

from pdftranslator.core import fonts


def test_chinese_uses_bundled_noto_sc():
    name, path = fonts.font_for_language("zh")
    assert name == "NotoSansSCRegular"
    assert path.endswith("NotoSansSC-Regular.ttf")
    assert Path(path).exists()  # the font is actually bundled


def test_latin_targets_use_bundled_noto():
    for target in ("en", "pt"):
        name, path = fonts.font_for_language(target)
        assert name == "NotoSansRegular"
        assert path.endswith("NotoSans-Regular.ttf")
        assert Path(path).exists()


def test_style_variants_resolve_to_bundled_files():
    # Latin has all four faces; CJK ships Regular + Bold (no italic form).
    assert fonts.font_variant("en", bold=True)[1].endswith("NotoSans-Bold.ttf")
    assert fonts.font_variant("en", italic=True)[1].endswith("NotoSans-Italic.ttf")
    assert fonts.font_variant("en", bold=True, italic=True)[1].endswith("NotoSans-BoldItalic.ttf")
    assert fonts.font_variant("zh", bold=True)[1].endswith("NotoSansSC-Bold.ttf")
    assert fonts.font_variant("zh", italic=True)[1].endswith("NotoSansSC-Regular.ttf")
    for target, bold, italic in [("en", True, False), ("zh", True, False)]:
        assert Path(fonts.font_variant(target, bold=bold, italic=italic)[1]).exists()
