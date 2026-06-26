from pathlib import Path

from pdftranslator.core import fonts


def test_chinese_uses_bundled_noto_sc():
    name, path = fonts.font_for_language("zh")
    assert name == "NotoSansSC"
    assert path.endswith("NotoSansSC-Regular.ttf")
    assert Path(path).exists()  # the font is actually bundled


def test_latin_targets_use_bundled_noto():
    for target in ("en", "pt"):
        name, path = fonts.font_for_language(target)
        assert name == "NotoSans"
        assert path.endswith("NotoSans-Regular.ttf")
        assert Path(path).exists()
