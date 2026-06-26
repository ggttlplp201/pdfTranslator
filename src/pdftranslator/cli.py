from pathlib import Path
from typing import Optional

import requests
import typer

from .core.engine import translate_pdf
from .core.providers import build_provider

app = typer.Typer(add_completion=False, help="Translate PDFs (zh/pt/en), preserving formatting.")


@app.command()
def translate(
    input: Path = typer.Argument(..., exists=True, dir_okay=False, help="Source PDF"),
    to: str = typer.Option(..., "--to", help="Target language: en, pt, zh"),
    from_: str = typer.Option("auto", "--from", help="Source language: en, pt, zh, auto"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output PDF path"),
    provider: str = typer.Option("google", "--provider", help="Translation backend"),
) -> None:
    out_path = output or input.with_suffix(f".{to}.pdf")
    prov = build_provider(provider)

    def _progress(index: int, count: int) -> None:
        typer.echo(f"page {index + 1}/{count}")

    try:
        translate_pdf(str(input), str(out_path), source=from_, target=to,
                      provider=prov, progress=_progress)
    except ValueError as exc:
        raise typer.BadParameter(str(exc))
    except requests.RequestException as exc:
        typer.echo(f"Translation failed: {exc}", err=True)
        raise typer.Exit(1)
    typer.echo(f"Wrote {out_path}")


def main() -> None:
    app()
