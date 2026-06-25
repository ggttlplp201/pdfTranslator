# PDF Translator — Design

**Date:** 2026-06-25
**Status:** Approved (pending spec review)

## Goal

A PDF translator supporting translation in any direction among **Simplified
Chinese, Portuguese, and English**. The overriding success metric is
**preserving the original PDF formatting** — layout, fonts, images, links, and
graphics must look as close to the original as possible, with only the text
translated.

Delivered as a portable, downloadable **desktop app for Windows (primary) and
macOS (developer's test machine)**, plus a **CLI** and a **web app**. All three
are thin wrappers over one shared engine.

## Non-Goals (v1)

- Scanned / image-only PDFs (no text layer). Deferred to Phase 4 (OCR).
- Languages beyond Simplified Chinese, Portuguese, English.
- Editing the PDF beyond text translation.
- Server-hosted / multi-user SaaS. The web app runs locally.

## Architecture

One Python core library; three thin frontends over it.

```
pdftranslator/
├── core/        Engine: PDF parse, format-preserving rewrite, providers
├── cli/         Typer command-line wrapper
├── web/         FastAPI server + drag-drop browser UI
└── desktop/     pywebview native window wrapping the web UI + engine
```

**Python** is chosen for the best PDF + translation ecosystem (PyMuPDF). The
**desktop app reuses the web UI** (same screen in a local native window) so the
interface is built once. The CLI is a separate thin wrapper.

### Unit boundaries

- **`core.engine`** — orchestrates: load PDF → extract → group → translate →
  rewrite → save. Knows nothing about HTTP, CLI args, or windows.
- **`core.layout`** — PyMuPDF span extraction, grouping into translation units,
  text erasure, re-insertion, and text-fitting. The fidelity-critical unit.
- **`core.providers`** — `TranslationProvider` interface + `GoogleProvider`,
  `LLMProvider`. Pure text-in/text-out; no PDF knowledge.
- **`core.fonts`** — selects a bundled font that can render the target script.
- Each frontend depends only on `core.engine` (+ a settings object).

## Format-Preservation Engine

Built on **PyMuPDF (fitz)**, which preserves images, links, vector graphics,
and page layout automatically — we modify only text.

Per page:

1. **Extract** every text span via `page.get_text("dict")`: text, bbox, font,
   size, color, style flags (bold/italic).
2. **Group** spans into lines/paragraphs so whole sentences are translated
   together. Span-by-span translation destroys meaning and is forbidden.
3. **Translate** grouped units, batched, via the active provider.
4. **Erase** the original text in place using redaction over the text bbox only
   (images and graphics outside the text box are untouched).
5. **Re-insert** the translated text at the same position, matching font, size,
   color, and style as closely as the bundled fonts allow.
6. **Fit** the text to its box: target text often changes length (Chinese is
   compact; Portuguese runs ~25% longer than English). When the translation
   overflows its box, auto-shrink the font size until it fits. Links and
   bookmark destinations are remapped to the rewritten pages.

### Fonts

Bundle **Noto Sans CJK SC** (Simplified Chinese) and **Noto Sans** (Latin,
including Portuguese accents). The original PDF's font usually cannot render the
target language's glyphs (e.g. an English PDF's font has no Chinese
characters), so `core.fonts` picks a bundled font matching the target script,
mapping bold/italic to the corresponding variant where available.

### Known fidelity edge cases

- Multi-column layouts and tables: text-fitting is per-box, so columns/cells
  are preserved as long as PyMuPDF reports their spans correctly.
- Justified text / tight leading: re-inserted text uses the box; minor reflow
  within a box is acceptable.
- Right-to-left and vertical scripts: out of scope (not among the 3 languages).

## Translation Backend

One `TranslationProvider` interface, selected in settings.

- **GoogleProvider (default).** Uses the unofficial free Google Translate
  endpoint (the one the website uses) — no key, no setup. Unofficial: rate
  limited and may change without notice; this is an accepted tradeoff for a
  zero-config default. Advanced users can switch to an official key.
- **LLMProvider.** User pastes a **Claude or OpenAI** API key into settings.
  Sends batched text with an instruction to translate only, preserve any inline
  formatting markers, and return only the translation. Default model **Claude
  Haiku** (cheapest and highest quality for these language pairs).

Both expose the same method: translate a list of text units from a source to a
target language. Language pairs: any direction among zh-Hans, pt, en, plus
source auto-detection.

### Batching & rate limits

Group units into batches per request to cut call count and preserve context.
Respect provider rate limits with backoff. For the LLM provider, batch with
clear delimiters so units map back 1:1 after translation.

## Frontends

- **CLI** (Typer): `pdftranslate in.pdf --from en --to zh -o out.pdf`, with
  `--provider`, `--model`, progress output, and batch/folder support.
- **Web** (FastAPI + minimal HTML/JS): drag-drop upload, source/target language
  pick, provider/key settings, progress bar, download. Runs locally.
- **Desktop** (pywebview): the web UI in a native window, bundling the FastAPI
  app + engine. No separate UI codebase.

## Distribution

**PyInstaller** builds a Windows `.exe` and a macOS `.app`, bundling Python and
all native deps (PyMuPDF, fonts) so users need no Python install. **GitHub
Actions** produces both artifacts on each tagged release.

## Phasing

- **Phase 1 — Core engine + CLI.** Digital PDFs, Google backend,
  format-preserving rewrite, fonts, text-fitting. The testable heart.
- **Phase 2 — LLM backend + web UI.** Key entry, provider switching, browser UI.
- **Phase 3 — Desktop packaging.** pywebview wrapper, PyInstaller builds for
  Windows + macOS, GitHub Actions release pipeline.
- **Phase 4 (later) — OCR.** Scanned/image-only PDFs via an OCR step
  (e.g. Tesseract/PaddleOCR with Chinese support) feeding the same pipeline.

## Key Risks

- **Text fitting** is the main fidelity risk; length changes between languages
  can force font shrinkage or minor reflow. Mitigation: per-box auto-fit, tested
  against real documents early.
- **Unofficial Google endpoint** may break or rate-limit. Mitigation: the
  pluggable provider interface lets users switch to an LLM key.
- **PyInstaller cross-platform packaging** with native deps and bundled fonts
  can be fiddly. Mitigation: tackled in its own phase with CI on both OSes.
