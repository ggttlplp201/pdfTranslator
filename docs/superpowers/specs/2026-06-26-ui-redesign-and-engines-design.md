# PDF Translator — UI Redesign + Engine Selection Design

**Date:** 2026-06-26
**Status:** Approved (pending spec review)
**Builds on:** Phase 1 (engine + CLI) and Phase 2a (web app), both on `main`.

## Goal

Two combined changes to the web app:

1. **Redesign the single page** to match the hi-fi handoff
   (`docs/design/redesign-handoff.md`, prototype `docs/design/redesign-prototype.dc.html`):
   light `#F8F9FA` canvas, blue accent `#1B66C9`, squared corners, a header with a
   文 wordmark + History, a dashed dropzone, From·swap·To·Translate controls, a
   multi-state status bar, and two **side-by-side text-reader panes** (original vs
   translated text, not page images).
2. **Engine selection** as a menu option: **Google** (free, no key, default),
   **Claude** (Anthropic), or **OpenAI** (ChatGPT). For Claude/OpenAI the user
   pastes an API key in the UI; the server saves it locally and uses it.

## Non-Goals (this iteration)

- Desktop packaging / downloadable app (separate, deferred — brainstormed already).
- Persistent History across restarts (this redesign ships **session-only** history).
- OCR / scanned PDFs.
- Per-model picker in the UI (smart default per engine; changeable in code).

## Decisions (from brainstorming)

- Panes show **extracted text** (reading view), not rendered page images. The
  format-preserved PDF remains available via **Download**.
- **History is session-only** — backed by the existing in-memory `JobStore`; no
  database or disk persistence.
- **Engines:** Google (no key) / Claude / OpenAI, chosen via a UI menu. Key entered
  in the UI, **saved locally** to a config file. **Default model per engine:**
  Claude → `claude-haiku-4-5`, OpenAI → `gpt-4o-mini`.

## Backend

Reuses the Phase-1 engine and `JobStore` (in-memory, threaded). Additions:

### `core.providers` — LLM providers
- `AnthropicProvider(api_key, model="claude-haiku-4-5", ...)` and
  `OpenAIProvider(api_key, model="gpt-4o-mini", ...)`, both implementing
  `translate(texts, source, target) -> list[str]`.
- The engine already calls `provider.translate([all lines of a page], …)`, so each
  provider **batches** that page's lines: send the list (numbered/JSON), ask the
  model to return a same-length JSON array of translations, parse it, and **fall
  back to per-line** translation for any batch whose response count doesn't match.
  System instruction: translate each line from source→target, output only the
  translations as a JSON array, preserve inline numbers/symbols, no commentary.
- Anthropic via the official `anthropic` SDK; OpenAI via the official `openai` SDK.
  New runtime deps: `anthropic>=0.40`, `openai>=1.40`.
- `build_provider(engine: str, *, api_key: str | None = None) -> TranslationProvider`:
  `"google"` → `GoogleProvider()`; `"claude"` → `AnthropicProvider(api_key)`;
  `"openai"` → `OpenAIProvider(api_key)`; unknown → `ValueError`. Raises a clear
  error if an LLM engine is selected without a key.

### `web.settings` — local key storage
- A small module that reads/writes `~/.config/pdftranslator/config.json` (path
  override via `PDFTRANSLATOR_CONFIG_DIR` for tests), storing
  `{"claude_api_key": "...", "openai_api_key": "..."}`.
- `get_key(engine)`, `set_key(engine, key)`, `has_key(engine)`. Keys are written
  with `0600` permissions where supported. The file lives on the user's own machine.

### Endpoints (added to `web.app`)
- `POST /api/translate` — now also accepts `engine` (form field; default `google`).
  Validates languages (400) and, for an LLM engine, that a key is saved (400 with a
  clear message). Captures `filename` and `size_bytes`; computes `page_count` from
  the uploaded PDF. Builds the provider via `build_provider(engine, api_key=...)`.
- `GET /api/jobs/{id}` — returns `status, page, page_count, error, filename,
  size_bytes, source, target, engine`.
- `GET /api/jobs` — list of the session's jobs (id, filename, source, target,
  status, page_count, created_at), newest first, for History.
- `GET /api/jobs/{id}/text?which=original|result` — `{pages: [text, …]}`, per-page
  text read from the input PDF (original) or output PDF (translated; requires
  `done`). 404 unknown / not-ready.
- `GET /api/jobs/{id}/result` — unchanged (Download the formatted PDF).
- `GET/POST /api/settings` — `GET` returns which engines have a saved key
  (`{"claude": bool, "openai": bool}`); `POST {engine, api_key}` saves a key. Key
  values are never returned by `GET`.
- The image endpoints (`/pages`, `/page/...`) remain but are unused by the new UI.

### `Job` (in `web.jobs`)
Gains `filename: str`, `size_bytes: int`, `created_at: float`, `engine: str`, and
`page_count` set at creation (from the input PDF) in addition to the live `page`.
`JobStore.create(...)` takes the new fields and the resolved provider.

## Frontend (full rewrite of `web/static/`)

Rebuild `index.html`, `styles.css`, `app.js` to the handoff. Vanilla, no build step.
All exact values (colors, sizes, spacing, shadows, fonts) come from
`docs/design/redesign-handoff.md`; inline SVG icons are copied from
`docs/design/redesign-prototype.dc.html` (do **not** copy its `<x-dc>`/`<sc-if>`
prototype scaffolding). Fonts load from Google Fonts.

Components: header (文 wordmark + History button), dashed dropzone with file
sub-line (name · size · pages), controls row (From select · swap button · To select
· **Engine menu** · Translate), status bar with four states (idle / translating with
page progress / done with green bar + Download / **error with a friendly message +
Retry**), and two text panes (ORIGINAL/TRANSLATED labels + EN/ZH badges, scrollable
bodies, per-page "PAGE n / 第 n 页" markers, Noto Sans SC for the translated pane,
custom scrollbar).

**Engine menu behavior:** an Engine `<select>` (Google / Claude / OpenAI) styled like
the other controls. Choosing Claude or OpenAI reveals an API-key input + Save; on
Save, `POST /api/settings`. If the user starts a translation with an LLM engine and
no saved key, show the friendly error prompting them to add a key. Google needs no
key. The chosen engine is sent with the translate request.

**History panel:** the History button opens a panel listing `GET /api/jobs` (filename,
langs, status, time); clicking an entry reloads that job's panes (via the text
endpoint) and Download. Session-only (cleared when the server restarts).

**Swap:** exchanges From/To, updates the EN/ZH badges, and invalidates a shown result.

## Error Handling

- Bad language / missing LLM key / non-PDF / empty upload → `400` with a clear
  `detail`, surfaced as the status bar's friendly error state with **Retry**.
- Translation failure during the job (Google 5xx after retries, LLM API error) →
  job `error` with a readable message; UI shows the error state + Retry. No raw
  "500 Server Error" text.
- Unknown job / result-not-ready → `404`.

## Testing

- **Providers:** `AnthropicProvider`/`OpenAIProvider` tested with the SDK client
  injected/mocked (no network) — batch happy path returns a same-length list; a
  malformed/short response falls back to per-line; `build_provider` routes engines
  and errors without a key.
- **Settings:** `set_key`/`get_key`/`has_key` round-trip against a temp config dir
  (`PDFTRANSLATOR_CONFIG_DIR`); `GET /api/settings` reports booleans, never values.
- **Endpoints:** `/api/jobs/{id}/text` returns per-page original and translated text
  (translated extracted from the output PDF); `/api/jobs` lists jobs; status carries
  filename/size/pages/langs/engine; translate with an LLM engine but no key → 400.
  All via the fake provider + in-memory PDFs (no network).
- **Frontend:** assert the served HTML/JS contain the redesigned structure (wordmark,
  dropzone, swap, engine select, panes with labels/badges, history button) and call
  the text + settings endpoints. **Visual fidelity is verified by the user live** (a
  dynamic browser UI can't be screenshotted here); values are matched to the handoff.

## Phasing (one plan, sequenced)

1. `Job` enrichment + `JobStore` changes (filename/size/created_at/engine/page_count).
2. `/api/jobs/{id}/text` + `/api/jobs` + enriched `GET /api/jobs/{id}`.
3. `web.settings` (local key storage) + `GET/POST /api/settings`.
4. `AnthropicProvider` + `OpenAIProvider` + `build_provider(engine, api_key=)` (deps).
5. `POST /api/translate` accepts `engine`, resolves key, builds provider.
6. Frontend rewrite to the handoff: layout/tokens/components + text-reader panes.
7. Frontend: engine menu + key entry + history panel + swap + four status states.

## Key Risks

- **LLM batch alignment** (response count ≠ input count) — mitigated by JSON-array
  output + per-line fallback, covered by tests.
- **Visual fidelity** can't be auto-screenshotted here — mitigated by matching exact
  handoff values and user live-review.
- **OpenAI default model name** (`gpt-4o-mini`) may need adjusting to the account's
  available models — it's a one-line default, documented.
