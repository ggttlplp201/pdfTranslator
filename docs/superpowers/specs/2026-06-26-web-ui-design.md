# PDF Translator — Web UI (Phase 2a) Design

**Date:** 2026-06-26
**Status:** Approved (pending spec review)
**Builds on:** Phase 1 (core engine + CLI), already on `main`.

## Goal

A local web app, run in the browser, where a user can drag-drop (or browse to)
a PDF, pick source/target languages, watch live translation progress, preview
the original and translated PDFs side by side, and download the result. It
reuses the Phase-1 engine unchanged and the Google backend.

## Non-Goals (this iteration)

- LLM/OpenAI-Claude API-key backend (the immediate next step after this).
- Native desktop packaging (pywebview / `.exe` / `.app`) — a later phase.
- Multi-user hosting, auth, persistence across restarts. This is a local,
  single-user tool; jobs live in memory.
- Scanned/OCR PDFs (Phase 4).

## Architecture

A FastAPI server serves one vanilla HTML page plus a small JSON API and calls
the existing `pdftranslator.core.engine.translate_pdf`. New code only:

```
src/pdftranslator/web/
├── __init__.py
├── app.py        FastAPI app + routes
├── jobs.py       in-memory job store + background runner
├── __main__.py   launch uvicorn, open the browser
└── static/       index.html, app.js, styles.css
```

- **New runtime dependencies:** `fastapi`, `uvicorn`, `python-multipart`.
- **Launch:** a new console script `pdftranslate-web` (and `python -m
  pdftranslator.web`). The existing `pdftranslate` CLI is untouched.
- The engine, providers, fonts, layout, and lang modules are reused as-is. No
  changes to Phase-1 code are required.

### Unit boundaries

- **`web.jobs`** — owns job lifecycle and state. A `Job` carries `id`, `status`
  (`running`/`done`/`error`), `page`, `page_count`, `error`, and the temp paths
  for the original and result PDFs. A `JobStore` holds jobs by id and starts a
  background thread per job that runs `translate_pdf` with a progress callback
  that updates the job. Knows nothing about HTTP.
- **`web.app`** — HTTP only: request parsing, validation, wiring the store,
  streaming files, serving static assets. No translation logic.
- **`web/static`** — the browser UI; talks to the API only.

## API and Data Flow

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Serve `index.html` |
| GET | `/static/*` | Serve JS/CSS |
| POST | `/api/translate` | multipart `file`, `source`, `target` → start job → `{ "job_id": ... }` |
| GET | `/api/jobs/{id}` | `{ status, page, page_count, error }` |
| GET | `/api/jobs/{id}/original` | stream the uploaded PDF (left preview) |
| GET | `/api/jobs/{id}/result` | stream the translated PDF (right preview + download) |

Flow:

1. User drops/browses a PDF, picks From (auto/en/pt/zh) and To (en/pt/zh),
   clicks Translate.
2. Frontend POSTs the file + languages to `/api/translate`. The server validates
   languages (`lang.validate_source`/`validate_target`) — a bad code returns
   `400` before any work — saves the upload to a per-job temp directory, creates
   a `Job`, starts the background thread, and returns `job_id`.
3. The left preview immediately points at `/api/jobs/{id}/original`.
4. Frontend polls `/api/jobs/{id}` ~once per second and updates a progress bar
   from `page`/`page_count`.
5. On `done`, the right preview points at `/api/jobs/{id}/result` and the
   Download button is enabled.
6. On `error`, the message is shown inline; the bar stops.

### Background execution

`translate_pdf` is synchronous and network-bound, so the job runs in a
`threading.Thread` to keep the event loop responsive. The progress callback
(`progress(page_index, page_count)`) updates the job's `page`/`page_count`
(store `page = page_index + 1`). The translation uses
`providers.build_provider("google")`.

## Error Handling

- **Bad language code:** `400` at submit (`/api/translate`), shown inline; no job
  is created.
- **Failure during the job** (Google rate-limit/network via
  `requests.RequestException`, or any unexpected error): caught in the background
  runner; the job is marked `error` with a readable message (e.g. "Translation
  failed: …"). The frontend surfaces it instead of spinning forever.
- **Unknown job id / result not ready:** `404`.
- **Non-PDF or empty upload:** `400` with a clear message.

## Resource Management

Each job gets a temp directory holding `input.pdf` and `output.pdf`. To bound
disk use, the `JobStore` keeps at most a small number of recent jobs (e.g. 20);
when exceeded, the oldest job's temp directory is removed. Everything is in
memory and cleared on process exit.

## Frontend (vanilla HTML/CSS/JS)

One page, no build step:

- A drag-drop zone that is also click-to-browse (hidden `<input type="file"
  accept="application/pdf">`).
- Two `<select>` dropdowns: From (auto, en, pt, zh) and To (en, pt, zh).
- A Translate button (disabled until a file is chosen).
- A determinate progress bar showing "page X / Y".
- A side-by-side preview: two `<iframe>`s (Original | Translated) using the
  browser's native PDF viewer (free scroll/zoom), with a Download button under
  the translated side.
- An inline error area.

Visual intent: clean, uncluttered, drop-zone-centered; intentional typography
and spacing rather than a generic template look. No frameworks.

## Testing

- **API (FastAPI `TestClient`)**, with `build_provider` monkeypatched to a fake
  provider (uppercases text) on a PDF built in-memory with fitz:
  - `POST /api/translate` → returns a `job_id`; polling `/api/jobs/{id}` reaches
    `done`; `GET /api/jobs/{id}/result` returns a PDF whose extracted text is the
    translated (uppercased) text.
  - `GET /api/jobs/{id}/original` returns the original PDF.
  - Bad target language → `400`.
  - Provider raises `requests.RequestException` → job ends `error` with a message.
  - Unknown job id → `404`.
  - `GET /` returns HTML.
- **`jobs.JobStore`** unit tests: a job runs to `done` and records progress; a
  job whose runner raises ends `error`; the store evicts the oldest job past the
  cap and removes its temp dir.
- **Frontend JS:** verified manually by running the app live and exercising
  drop → translate → preview → download (screenshots), as in Phase 1.

## Phasing

Single implementation plan. Tasks roughly: (1) add deps + FastAPI app skeleton
serving `GET /` and static; (2) `jobs.JobStore` + background runner with progress
(unit-tested); (3) `POST /api/translate` + validation; (4) status + file-serving
endpoints; (5) the vanilla frontend page; (6) the `pdftranslate-web` launch
entry. Each task ends with an independently testable deliverable.

## Key Risks

- **Blocking the event loop** if translation isn't threaded — mitigated by the
  background thread design and an API test that submits then immediately polls.
- **Google rate-limiting on large PDFs** (per-line requests) — surfaced as a
  clean job `error`; the LLM-key backend (next step) is the path for heavy docs.
- **Browser PDF-viewer differences** — using `<iframe>` to the served PDF relies
  on the browser's built-in viewer (standard in current Chrome/Safari/Firefox);
  acceptable for a local tool.
