import fitz
from pdftranslator.core import engine


class FakeProvider:
    def translate(self, texts, source, target):
        return [t.upper() for t in texts]


def test_translate_pdf_writes_translated_output(tmp_path):
    src = tmp_path / "in.pdf"
    out = tmp_path / "out.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "hello", fontsize=12)
    doc.save(str(src))
    doc.close()

    seen = []
    engine.translate_pdf(
        str(src), str(out), source="auto", target="en",
        provider=FakeProvider(), progress=lambda i, n: seen.append((i, n)),
    )

    result = fitz.open(str(out))
    text = result[0].get_text("text")
    assert "HELLO" in text
    assert "hello" not in text
    result.close()
    assert seen == [(0, 1)]


def test_translate_pdf_zh_target(tmp_path):
    """Translating to zh uses china-s font through the full pipeline without error."""

    class ChineseProvider:
        def translate(self, texts, source, target):
            return ["你好" for _ in texts]

    src = tmp_path / "in.pdf"
    out = tmp_path / "out.zh.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "hello", fontsize=12)
    doc.save(str(src))
    doc.close()

    engine.translate_pdf(
        str(src), str(out), source="auto", target="zh",
        provider=ChineseProvider(),
    )

    result = fitz.open(str(out))
    text = result[0].get_text("text")
    result.close()
    assert "你好" in text


def test_translate_pdf_rejects_bad_target(tmp_path):
    src = tmp_path / "in.pdf"
    doc = fitz.open(); doc.new_page(); doc.save(str(src)); doc.close()
    import pytest
    with pytest.raises(ValueError):
        engine.translate_pdf(str(src), str(tmp_path / "o.pdf"),
                             source="auto", target="auto", provider=FakeProvider())
