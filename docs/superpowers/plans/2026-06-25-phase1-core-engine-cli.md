# PDF Translator — Phase 1 (Core Engine + CLI) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Translate a digital PDF between Simplified Chinese, Portuguese, and English while preserving layout, images, and links, driven from a command line.

**Architecture:** A Python core library (`pdftranslator.core`) parses a PDF with PyMuPDF, extracts text line-by-line with positions, translates each line through a pluggable provider, erases the original text via redaction (leaving images untouched), and re-inserts the translation in place with auto-shrink to fit. A Typer CLI wraps the engine.

**Tech Stack:** Python 3.11+, PyMuPDF (`pymupdf`/`fitz`), `requests` (Google endpoint), Typer (CLI), pytest.

## Global Constraints

- Python `>=3.11`.
- Runtime dependencies limited to: `pymupdf>=1.24`, `requests>=2.31`, `typer>=0.12`.
- Internal language codes are exactly `en`, `pt`, `zh` (Simplified Chinese), and `auto` (source only). Valid targets: `en`, `pt`, `zh`.
- Phase 1 uses PyMuPDF's **built-in** fonts — `china-s` for Chinese targets, `helv` (Helvetica, Latin-1 covers Portuguese accents) for `en`/`pt`. No font files are bundled in Phase 1.
- Translation is **per text line** (never per span). One line = one translation unit.
- Tests must not hit the network. The Google provider takes an injectable HTTP session; tests pass a fake. Engine/CLI tests use a fake provider.
- `src/` package layout. TDD: every task is red → green → commit. Commit messages are plain Conventional Commits with no co-author trailer.

---

### Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `src/pdftranslator/__init__.py`
- Create: `src/pdftranslator/core/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/test_smoke.py`

**Interfaces:**
- Consumes: nothing.
- Produces: an installable `pdftranslator` package and a working `pytest` setup.

- [ ] **Step 1: Write the failing test**

`tests/test_smoke.py`:

```python
import importlib


def test_package_imports():
    mod = importlib.import_module("pdftranslator")
    assert mod is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_smoke.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pdftranslator'`

- [ ] **Step 3: Create the package and config**

`pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "pdftranslator"
version = "0.1.0"
description = "Format-preserving PDF translator (zh/pt/en)"
requires-python = ">=3.11"
dependencies = [
    "pymupdf>=1.24",
    "requests>=2.31",
    "typer>=0.12",
]

[project.optional-dependencies]
dev = ["pytest>=8"]

[project.scripts]
pdftranslate = "pdftranslator.cli:main"

[tool.setuptools.packages.find]
where = ["src"]
```

`src/pdftranslator/__init__.py`:

```python
__version__ = "0.1.0"
```

`src/pdftranslator/core/__init__.py`: empty file.
`tests/__init__.py`: empty file.

- [ ] **Step 4: Install the package (editable) and run the test**

Run:
```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
python -m pytest tests/test_smoke.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src tests
git commit -m "chore: scaffold pdftranslator package"
```

---

### Task 2: Language codes and data model

**Files:**
- Create: `src/pdftranslator/core/models.py`
- Create: `src/pdftranslator/core/lang.py`
- Create: `tests/test_lang.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `models.TextUnit` dataclass: fields `text: str`, `bbox: tuple[float, float, float, float]`, `size: float`, `color: int`.
  - `lang.to_google(code: str) -> str` — maps `en→en`, `pt→pt`, `zh→zh-CN`, `auto→auto`.
  - `lang.validate_target(code: str) -> None` — raises `ValueError` unless code in `{en, pt, zh}`.
  - `lang.validate_source(code: str) -> None` — raises `ValueError` unless code in `{en, pt, zh, auto}`.

- [ ] **Step 1: Write the failing test**

`tests/test_lang.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_lang.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pdftranslator.core.lang'`

- [ ] **Step 3: Write minimal implementation**

`src/pdftranslator/core/models.py`:

```python
from dataclasses import dataclass


@dataclass
class TextUnit:
    text: str
    bbox: tuple[float, float, float, float]
    size: float
    color: int
```

`src/pdftranslator/core/lang.py`:

```python
_TO_GOOGLE = {"en": "en", "pt": "pt", "zh": "zh-CN", "auto": "auto"}
_TARGETS = {"en", "pt", "zh"}
_SOURCES = {"en", "pt", "zh", "auto"}


def to_google(code: str) -> str:
    if code not in _TO_GOOGLE:
        raise ValueError(f"unsupported language code: {code}")
    return _TO_GOOGLE[code]


def validate_target(code: str) -> None:
    if code not in _TARGETS:
        raise ValueError(f"unsupported target language: {code} (use en, pt, zh)")


def validate_source(code: str) -> None:
    if code not in _SOURCES:
        raise ValueError(f"unsupported source language: {code} (use en, pt, zh, auto)")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_lang.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/pdftranslator/core/models.py src/pdftranslator/core/lang.py tests/test_lang.py
git commit -m "feat: add language codes and TextUnit model"
```

---

### Task 3: Translation provider interface + Google provider

**Files:**
- Create: `src/pdftranslator/core/providers.py`
- Create: `tests/test_providers.py`

**Interfaces:**
- Consumes: `lang.to_google`.
- Produces:
  - `providers.TranslationProvider` — Protocol with `translate(self, texts: list[str], source: str, target: str) -> list[str]`.
  - `providers.GoogleProvider(session=None)` — implements the protocol against the unofficial endpoint; caches identical strings; accepts an injectable `requests`-style session (`session.get(url, params=..., timeout=...)`).
  - `providers.build_provider(name: str) -> TranslationProvider` — returns `GoogleProvider()` for `"google"`, raises `ValueError` otherwise.

- [ ] **Step 1: Write the failing test**

`tests/test_providers.py`:

```python
import pytest
from pdftranslator.core import providers


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, payload):
        self._payload = payload
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        return FakeResponse(self._payload)


def test_google_parses_translated_segments():
    # Google returns nested arrays: data[0] is a list of [translated, original, ...]
    payload = [[["Olá", "Hello", None, None, 10], [" mundo", " world", None, None, 3]], None, "en"]
    session = FakeSession(payload)
    provider = providers.GoogleProvider(session=session)

    out = provider.translate(["Hello world"], source="en", target="pt")

    assert out == ["Olá mundo"]
    assert session.calls[0][1]["sl"] == "en"
    assert session.calls[0][1]["tl"] == "pt"


def test_google_caches_repeated_text():
    payload = [[["你好", "Hello", None, None, 10]], None, "en"]
    session = FakeSession(payload)
    provider = providers.GoogleProvider(session=session)

    provider.translate(["Hello", "Hello"], source="en", target="zh")

    assert len(session.calls) == 1  # second identical string served from cache


def test_build_provider_unknown_raises():
    with pytest.raises(ValueError):
        providers.build_provider("nope")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_providers.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pdftranslator.core.providers'`

- [ ] **Step 3: Write minimal implementation**

`src/pdftranslator/core/providers.py`:

```python
from typing import Protocol

import requests

from . import lang

_GOOGLE_URL = "https://translate.googleapis.com/translate_a/single"


class TranslationProvider(Protocol):
    def translate(self, texts: list[str], source: str, target: str) -> list[str]:
        ...


class GoogleProvider:
    def __init__(self, session=None):
        self._session = session or requests.Session()
        self._cache: dict[tuple[str, str, str], str] = {}

    def translate(self, texts: list[str], source: str, target: str) -> list[str]:
        sl = lang.to_google(source)
        tl = lang.to_google(target)
        return [self._one(t, sl, tl) for t in texts]

    def _one(self, text: str, sl: str, tl: str) -> str:
        if not text.strip():
            return text
        key = (text, sl, tl)
        if key in self._cache:
            return self._cache[key]
        params = {"client": "gtx", "sl": sl, "tl": tl, "dt": "t", "q": text}
        resp = self._session.get(_GOOGLE_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        segments = data[0] or []
        translated = "".join(seg[0] for seg in segments if seg and seg[0])
        self._cache[key] = translated
        return translated


def build_provider(name: str) -> TranslationProvider:
    if name == "google":
        return GoogleProvider()
    raise ValueError(f"unknown provider: {name}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_providers.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/pdftranslator/core/providers.py tests/test_providers.py
git commit -m "feat: add provider interface and Google translate provider"
```

---

### Task 4: Font selection

**Files:**
- Create: `src/pdftranslator/core/fonts.py`
- Create: `tests/test_fonts.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `fonts.font_for_language(target: str) -> str` — returns `"china-s"` for `zh`, `"helv"` for `en`/`pt`.

- [ ] **Step 1: Write the failing test**

`tests/test_fonts.py`:

```python
from pdftranslator.core import fonts


def test_chinese_uses_builtin_cjk_font():
    assert fonts.font_for_language("zh") == "china-s"


def test_latin_targets_use_helvetica():
    assert fonts.font_for_language("en") == "helv"
    assert fonts.font_for_language("pt") == "helv"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_fonts.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pdftranslator.core.fonts'`

- [ ] **Step 3: Write minimal implementation**

`src/pdftranslator/core/fonts.py`:

```python
def font_for_language(target: str) -> str:
    if target == "zh":
        return "china-s"
    return "helv"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_fonts.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/pdftranslator/core/fonts.py tests/test_fonts.py
git commit -m "feat: add target-language font selection"
```

---

### Task 5: Extract text units from a page

**Files:**
- Create: `src/pdftranslator/core/layout.py`
- Create: `tests/test_layout_extract.py`

**Interfaces:**
- Consumes: `models.TextUnit`.
- Produces: `layout.extract_units(page) -> list[TextUnit]` — one `TextUnit` per non-empty text line, with the line's combined text, bbox, max span size, and first span color.

- [ ] **Step 1: Write the failing test**

`tests/test_layout_extract.py`:

```python
import fitz
from pdftranslator.core import layout


def test_extract_units_finds_lines():
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Hello world", fontsize=12)
    page.insert_text((72, 100), "Second line", fontsize=12)

    units = layout.extract_units(page)

    texts = [u.text.strip() for u in units]
    assert "Hello world" in texts
    assert "Second line" in texts
    for u in units:
        assert u.size > 0
        assert len(u.bbox) == 4
    doc.close()


def test_extract_units_skips_blank_lines():
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "   ", fontsize=12)
    units = layout.extract_units(page)
    assert units == []
    doc.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_layout_extract.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pdftranslator.core.layout'`

- [ ] **Step 3: Write minimal implementation**

`src/pdftranslator/core/layout.py`:

```python
import fitz

from .models import TextUnit


def extract_units(page) -> list[TextUnit]:
    units: list[TextUnit] = []
    data = page.get_text("dict")
    for block in data.get("blocks", []):
        if block.get("type") != 0:  # 0 == text block
            continue
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            text = "".join(s.get("text", "") for s in spans)
            if not text.strip():
                continue
            size = max((s.get("size", 10.0) for s in spans), default=10.0)
            color = spans[0].get("color", 0) if spans else 0
            units.append(
                TextUnit(text=text, bbox=tuple(line["bbox"]), size=size, color=color)
            )
    return units
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_layout_extract.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/pdftranslator/core/layout.py tests/test_layout_extract.py
git commit -m "feat: extract per-line text units from a page"
```

---

### Task 6: Erase originals and re-insert translations (format-preserving rewrite)

**Files:**
- Modify: `src/pdftranslator/core/layout.py`
- Create: `tests/test_layout_rewrite.py`

**Interfaces:**
- Consumes: `models.TextUnit`, `extract_units`.
- Produces:
  - `layout.redact_units(page, units: list[TextUnit]) -> None` — redacts each unit's bbox and applies redactions without removing images (`images=fitz.PDF_REDACT_IMAGE_NONE`).
  - `layout._fit_fontsize(width: float, height: float, text: str, fontname: str, max_size: float) -> float` — largest size ≤ `max_size` (min 4.0) at which `text` fits a `width`×`height` box.
  - `layout.insert_translations(page, units: list[TextUnit], translations: list[str], fontname: str) -> None` — inserts each translation into its unit's box at the fitted size and original color.

- [ ] **Step 1: Write the failing test**

`tests/test_layout_rewrite.py`:

```python
import fitz
from pdftranslator.core import layout


def _make_pdf_with_text_and_image():
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Hello world", fontsize=12)
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 10, 10))
    pix.clear_with(128)
    page.insert_image(fitz.Rect(200, 200, 210, 210), pixmap=pix)
    return doc, page


def test_rewrite_replaces_text_and_keeps_image():
    doc, page = _make_pdf_with_text_and_image()
    assert len(page.get_images()) == 1

    units = layout.extract_units(page)
    layout.redact_units(page, units)
    layout.insert_translations(page, units, ["Olá mundo"], fontname="helv")

    text_after = page.get_text("text")
    assert "Hello" not in text_after
    assert "Olá mundo" in text_after
    assert len(page.get_images()) == 1  # image preserved
    doc.close()


def test_fit_fontsize_shrinks_long_text():
    big = layout._fit_fontsize(width=200, height=14, text="short", fontname="helv", max_size=12)
    small = layout._fit_fontsize(
        width=40, height=14, text="a very long line that will not fit", fontname="helv", max_size=12
    )
    assert big == 12
    assert small < 12
    assert small >= 4.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_layout_rewrite.py -v`
Expected: FAIL — `AttributeError: module 'pdftranslator.core.layout' has no attribute 'redact_units'`

- [ ] **Step 3: Write minimal implementation (append to `layout.py`)**

Append to `src/pdftranslator/core/layout.py`:

```python
def redact_units(page, units: list[TextUnit]) -> None:
    for u in units:
        page.add_redact_annot(fitz.Rect(u.bbox))
    if units:
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)


def _fit_fontsize(width: float, height: float, text: str, fontname: str, max_size: float) -> float:
    scratch = fitz.open()
    rect = fitz.Rect(0, 0, max(width, 1.0), height + 2)
    size = max_size
    try:
        while size >= 4.0:
            sp = scratch.new_page(width=max(width, 1.0) + 4, height=height + 10)
            leftover = sp.insert_textbox(rect, text, fontsize=size, fontname=fontname)
            if leftover >= 0:
                return size
            size -= 0.5
    finally:
        scratch.close()
    return 4.0


def insert_translations(page, units: list[TextUnit], translations: list[str], fontname: str) -> None:
    for u, text in zip(units, translations):
        if not text.strip():
            continue
        x0, y0, x1, y1 = u.bbox
        width = x1 - x0
        height = y1 - y0
        size = _fit_fontsize(width, height, text, fontname, u.size)
        color = fitz.sRGB_to_pdf(u.color)
        rect = fitz.Rect(x0, y0, x1, y1 + 2)
        page.insert_textbox(rect, text, fontsize=size, fontname=fontname, color=color, align=0)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_layout_rewrite.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/pdftranslator/core/layout.py tests/test_layout_rewrite.py
git commit -m "feat: redact originals and insert fitted translations"
```

---

### Task 7: Engine orchestration

**Files:**
- Create: `src/pdftranslator/core/engine.py`
- Create: `tests/test_engine.py`

**Interfaces:**
- Consumes: `layout.extract_units`, `layout.redact_units`, `layout.insert_translations`, `fonts.font_for_language`, `lang.validate_source`, `lang.validate_target`, `providers.TranslationProvider`.
- Produces: `engine.translate_pdf(input_path: str, output_path: str, source: str, target: str, provider, progress=None) -> None` — runs the full pipeline per page and saves the result. `progress`, if given, is called as `progress(page_index: int, page_count: int)` after each page.

- [ ] **Step 1: Write the failing test**

`tests/test_engine.py`:

```python
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


def test_translate_pdf_rejects_bad_target(tmp_path):
    src = tmp_path / "in.pdf"
    doc = fitz.open(); doc.new_page(); doc.save(str(src)); doc.close()
    import pytest
    with pytest.raises(ValueError):
        engine.translate_pdf(str(src), str(tmp_path / "o.pdf"),
                             source="auto", target="auto", provider=FakeProvider())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_engine.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pdftranslator.core.engine'`

- [ ] **Step 3: Write minimal implementation**

`src/pdftranslator/core/engine.py`:

```python
import fitz

from . import fonts, lang, layout


def translate_pdf(input_path, output_path, source, target, provider, progress=None) -> None:
    lang.validate_source(source)
    lang.validate_target(target)
    fontname = fonts.font_for_language(target)

    doc = fitz.open(input_path)
    try:
        count = len(doc)
        for index, page in enumerate(doc):
            units = layout.extract_units(page)
            if units:
                translations = provider.translate([u.text for u in units], source, target)
                layout.redact_units(page, units)
                layout.insert_translations(page, units, translations, fontname)
            if progress is not None:
                progress(index, count)
        doc.save(output_path, garbage=4, deflate=True)
    finally:
        doc.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_engine.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/pdftranslator/core/engine.py tests/test_engine.py
git commit -m "feat: add PDF translation engine orchestration"
```

---

### Task 8: CLI wrapper

**Files:**
- Create: `src/pdftranslator/cli.py`
- Create: `tests/test_cli.py`

**Interfaces:**
- Consumes: `engine.translate_pdf`, `providers.build_provider`.
- Produces:
  - `cli.app` — a Typer app with one default command `translate(input, to, from_="auto", output=None, provider="google")`. `--from`/`--to` are the option names; output defaults to `<input>.<target>.pdf`.
  - `cli.main()` — console-script entry that invokes `app()`.

- [ ] **Step 1: Write the failing test**

`tests/test_cli.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pdftranslator.cli'`

- [ ] **Step 3: Write minimal implementation**

`src/pdftranslator/cli.py`:

```python
from pathlib import Path
from typing import Optional

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
    typer.echo(f"Wrote {out_path}")


def main() -> None:
    app()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_cli.py -v`
Expected: PASS

- [ ] **Step 5: Run the whole suite and commit**

Run: `python -m pytest -v`
Expected: all tests PASS

```bash
git add src/pdftranslator/cli.py tests/test_cli.py
git commit -m "feat: add Typer CLI for PDF translation"
```

---

## Manual verification (after all tasks)

Translate a real digital PDF end-to-end with the live Google backend and eyeball formatting fidelity:

```bash
pdftranslate path/to/real.pdf --from en --to zh
open path/to/real.en.pdf  # macOS; compare layout/images/links against the original
```

Confirm: images and vector graphics are in place, layout is intact, links still work, and the text is translated. Note any fidelity issues (overflow, font fallback) for tuning before Phase 2.

## Self-Review Notes

- **Spec coverage:** digital-PDF in-place swap (Tasks 5–6), per-line grouping (Task 5, Global Constraints), provider abstraction + Google default (Task 3), language pairs + auto-detect (Task 2), built-in fonts for target script (Task 4 — Phase 1 deviation from bundled Noto, recorded in Global Constraints), text-fit auto-shrink (Task 6), CLI frontend (Task 8). LLM backend, web UI, desktop packaging, and OCR are out of Phase 1 scope by design.
- **Image/link preservation** is covered by `PDF_REDACT_IMAGE_NONE` and verified in Task 6's test; links are explicitly captured via `page.get_links()` before `apply_redactions` and any deleted links are restored afterward via `page.insert_link()`, guarded by xref comparison to avoid duplicates.
- **Type consistency:** `TextUnit` fields, `translate(texts, source, target)`, `extract_units`/`redact_units`/`insert_translations`/`_fit_fontsize`, and `translate_pdf(...)` signatures are used identically across tasks.
