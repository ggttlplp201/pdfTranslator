import pytest
from pdftranslator.core import lang
from pdftranslator.core.models import TextUnit


def test_to_google_maps_zh_to_zh_cn():
    assert lang.to_google("zh") == "zh-CN"
    assert lang.to_google("en") == "en"
    assert lang.to_google("pt") == "pt"
    assert lang.to_google("auto") == "auto"


def test_validate_target_rejects_auto():
    lang.validate_target("zh")
    with pytest.raises(ValueError):
        lang.validate_target("auto")


def test_validate_source_allows_auto():
    lang.validate_source("auto")
    with pytest.raises(ValueError):
        lang.validate_source("fr")


def test_textunit_holds_fields():
    u = TextUnit(text="hi", bbox=(0.0, 0.0, 1.0, 1.0), size=12.0, color=0)
    assert u.text == "hi"
    assert u.bbox == (0.0, 0.0, 1.0, 1.0)
