import fitz
from typer.testing import CliRunner
from pdftranslator import cli


class FakeProvider:
    def translate(self, texts, source, target):
        return [t.upper() for t in texts]


def test_cli_translates_pdf(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "build_provider", lambda name: FakeProvider())
    src = tmp_path / "in.pdf"
    out = tmp_path / "out.pdf"
    doc = fitz.open(); page = doc.new_page()
    page.insert_text((72, 72), "hello", fontsize=12)
    doc.save(str(src)); doc.close()

    result = CliRunner().invoke(
        cli.app, [str(src), "--to", "en", "--from", "auto", "--output", str(out)]
    )

    assert result.exit_code == 0, result.output
    assert out.exists()
    res = fitz.open(str(out))
    assert "HELLO" in res[0].get_text("text")
    res.close()


def test_cli_rejects_bad_target(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "build_provider", lambda name: FakeProvider())
    src = tmp_path / "in.pdf"
    doc = fitz.open(); doc.new_page(); doc.save(str(src)); doc.close()

    result = CliRunner().invoke(cli.app, [str(src), "--to", "fr"])
    assert result.exit_code != 0
