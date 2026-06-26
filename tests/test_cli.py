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


def test_cli_network_error_exits_nonzero(tmp_path, monkeypatch):
    """A network/HTTP error must produce a clean message and non-zero exit, not a traceback."""
    import requests

    class FailProvider:
        def translate(self, texts, source, target):
            raise requests.RequestException("boom")

    monkeypatch.setattr(cli, "build_provider", lambda name: FailProvider())
    src = tmp_path / "in.pdf"
    doc = fitz.open(); page = doc.new_page()
    page.insert_text((72, 72), "hello", fontsize=12)
    doc.save(str(src)); doc.close()

    result = CliRunner().invoke(
        cli.app, [str(src), "--to", "en", "--from", "auto"]
    )

    import requests as req_mod
    assert result.exit_code != 0
    # The exception must be handled by the CLI: the output must contain a
    # human-readable failure message, and no raw RequestException should leak.
    assert "Translation failed" in result.output, f"Expected clean message in output; got: {result.output!r}"
    assert not isinstance(result.exception, req_mod.RequestException), (
        f"RequestException leaked as unhandled: {result.exception!r}"
    )


def test_cli_rejects_bad_target(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "build_provider", lambda name: FakeProvider())
    src = tmp_path / "in.pdf"
    doc = fitz.open(); doc.new_page(); doc.save(str(src)); doc.close()

    result = CliRunner().invoke(cli.app, [str(src), "--to", "fr"])
    assert result.exit_code != 0
