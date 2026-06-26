# PDF Translator — Phase 2a (Web UI) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A local browser web app to drag-drop a PDF, pick languages, watch live progress, preview original vs. translated side by side, and download the result — reusing the Phase-1 engine and the Google backend.

**Architecture:** A FastAPI app serves one vanilla HTML page and a small JSON API. Uploads start an in-memory background job (a thread running `engine.translate_pdf` with a progress callback); the frontend polls job status and points two `<iframe>`s at server-streamed original/result PDFs.

**Tech Stack:** Python 3.11+, FastAPI, uvicorn, python-multipart, the existing PyMuPDF engine; vanilla HTML/CSS/JS; pytest + Starlette `TestClient` (httpx).

## Global Constraints

- Python `>=3.11`. New **runtime** deps: `fastapi>=0.110`, `uvicorn>=0.29`, `python-multipart>=0.0.9`. New **dev** dep: `httpx>=0.27` (required by `TestClient`).
- Reuse Phase-1 modules unchanged: `pdftranslator.core.engine.translate_pdf(input_path, output_path, source, target, provider, progress=None)`, `pdftranslator.core.providers.build_provider(name)`, `pdftranslator.core.lang.validate_source/validate_target`.
- Internal language codes: source ∈ {`auto`,`en`,`pt`,`zh`}, target ∈ {`en`,`pt`,`zh`}.
- Jobs are in-memory, run in a `threading.Thread`, store files under a per-job temp dir; the store keeps at most 20 jobs and removes the oldest job's temp dir when exceeded.
- Tests must not hit the network: monkeypatch `pdftranslator.core.providers.build_provider` to a fake provider, and build PDFs in-memory with `fitz`. `JobStore` tests inject a fake `runner`.
- New code lives under `src/pdftranslator/web/`. Launch via console script `pdftranslate-web` and `python -m pdftranslator.web`. The existing `pdftranslate` CLI is untouched.
- `src/` layout; pytest already configured with `pythonpath = ["src"]`. TDD: red → green → commit. Plain Conventional Commits, NO co-author trailer.
- Work from the project dir `pdfTranslator/`; activate `.venv` (`. .venv/bin/activate`). The git repo root is the parent `Development/` directory shared with other projects — only `git add` specific files under `pdfTranslator/`.

---

### Task 1: Web dependencies + FastAPI app skeleton

**Files:**
- Modify: `pyproject.toml`
- Create: `src/pdftranslator/web/__init__.py`
- Create: `src/pdftranslator/web/app.py`
- Create: `src/pdftranslator/web/static/index.html`
- Create: `src/pdftranslator/web/static/styles.css`
- Create: `src/pdftranslator/web/static/app.js`
- Create: `tests/test_web_app.py`

**Interfaces:**
- Consumes: nothing from earlier Phase-2 tasks.
- Produces: `web.app.create_app(store=None) -> FastAPI` and module-level `web.app.app`. Serves `GET /` (HTML) and mounts static files at `/static`. `create_app` accepts an optional store (used by later tasks); for now it may ignore it or set `app.state.store = store`.

- [ ] **Step 1: Add dependencies and install**

Edit `pyproject.toml` — add the runtime deps and the dev dep:

```toml
dependencies = [
    "pymupdf>=1.24",
    "requests>=2.31",
    "typer>=0.12",
    "fastapi>=0.110",
    "uvicorn>=0.29",
    "python-multipart>=0.0.9",
]

[project.optional-dependencies]
dev = ["pytest>=8", "httpx>=0.27"]
```

Also add the new console script under the existing `[project.scripts]` (the launch entry is implemented in Task 4, but declare it now alongside the existing one):

```toml
[project.scripts]
pdftranslate = "pdftranslator.cli:main"
pdftranslate-web = "pdftranslator.web.__main__:main"
```

Run:
```bash
. .venv/bin/activate
pip install -e ".[dev]" -q
```
Expected: installs fastapi, uvicorn, python-multipart, httpx with no errors.

- [ ] **Step 2: Write the failing test**

`tests/test_web_app.py`:

```python
from fastapi.testclient import TestClient
from pdftranslator.web.app import create_app


def test_index_served():
    client = TestClient(create_app())
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


def test_static_mounted():
    client = TestClient(create_app())
    resp = client.get("/static/styles.css")
    assert resp.status_code == 200
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_web_app.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pdftranslator.web'`

- [ ] **Step 4: Create the package, app factory, and minimal static files**

`src/pdftranslator/web/__init__.py`: empty file.

`src/pdftranslator/web/app.py`:

```python
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

STATIC_DIR = Path(__file__).parent / "static"


def create_app(store=None) -> FastAPI:
    app = FastAPI(title="PDF Translator")
    app.state.store = store
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return (STATIC_DIR / "index.html").read_text(encoding="utf-8")

    return app


app = create_app()
```

`src/pdftranslator/web/static/index.html` (minimal placeholder; replaced in Task 5):

```html
<!doctype html>
<html lang="en">
  <head><meta charset="utf-8"><title>PDF Translator</title>
  <link rel="stylesheet" href="/static/styles.css"></head>
  <body><div id="dropzone">PDF Translator</div>
  <script src="/static/app.js"></script></body>
</html>
```

`src/pdftranslator/web/static/styles.css`:

```css
body { font-family: system-ui, sans-serif; margin: 0; }
```

`src/pdftranslator/web/static/app.js`:

```javascript
// Frontend logic is implemented in Task 5.
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_web_app.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/pdftranslator/web tests/test_web_app.py
git commit -m "feat: add FastAPI web app skeleton and deps"
```

---

### Task 2: In-memory job store with background runner

**Files:**
- Create: `src/pdftranslator/web/jobs.py`
- Create: `tests/test_web_jobs.py`

**Interfaces:**
- Consumes: `pdftranslator.core.engine.translate_pdf`, `pdftranslator.core.providers.build_provider`.
- Produces:
  - `jobs.Job` dataclass: `id: str`, `source: str`, `target: str`, `provider_name: str`, `input_path: Path`, `output_path: Path`, `tmpdir: Path`, `status: str = "running"`, `page: int = 0`, `page_count: int = 0`, `error: str | None = None`, `thread` (background thread handle, not compared/repr).
  - `jobs.JobStore(max_jobs: int = 20, runner=None)` with:
    - `create(data: bytes, source: str, target: str, provider_name: str = "google") -> Job` — writes `data` to `tmpdir/input.pdf`, registers the job, evicts the oldest beyond `max_jobs` (removing its tmpdir), starts a daemon thread, returns the job.
    - `get(job_id: str) -> Job | None`.
  - The background thread runs `runner(job)` (default: build provider + `translate_pdf` with a progress callback) and sets `status="done"`, or `status="error"` + `error="Translation failed: ..."` if it raises.

- [ ] **Step 1: Write the failing test**

`tests/test_web_jobs.py`:

```python
import requests
from pdftranslator.web.jobs import JobStore


def test_job_runs_to_done_and_records_progress():
    def fake_runner(job):
        job.page_count = 2
        job.page = 2

    store = JobStore(runner=fake_runner)
    job = store.create(b"%PDF-1.4 fake", "auto", "en")
    job.thread.join(timeout=5)

    got = store.get(job.id)
    assert got.status == "done"
    assert got.page == 2 and got.page_count == 2
    assert job.input_path.read_bytes() == b"%PDF-1.4 fake"


def test_job_runner_failure_sets_error():
    def boom(job):
        raise requests.RequestException("rate limited")

    store = JobStore(runner=boom)
    job = store.create(b"%PDF", "auto", "en")
    job.thread.join(timeout=5)

    got = store.get(job.id)
    assert got.status == "error"
    assert "rate limited" in got.error


def test_store_evicts_oldest_and_removes_tmpdir():
    def fake_runner(job):
        job.page_count = 1
        job.page = 1

    store = JobStore(max_jobs=2, runner=fake_runner)
    jobs = [store.create(b"%PDF", "auto", "en") for _ in range(3)]
    for j in jobs:
        j.thread.join(timeout=5)

    assert store.get(jobs[0].id) is None
    assert not jobs[0].tmpdir.exists()
    assert store.get(jobs[2].id) is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_web_jobs.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pdftranslator.web.jobs'`

- [ ] **Step 3: Write minimal implementation**

`src/pdftranslator/web/jobs.py`:

```python
import shutil
import tempfile
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from ..core import engine, providers


@dataclass
class Job:
    id: str
    source: str
    target: str
    provider_name: str
    input_path: Path
    output_path: Path
    tmpdir: Path
    status: str = "running"
    page: int = 0
    page_count: int = 0
    error: Optional[str] = None
    thread: Optional[threading.Thread] = field(default=None, repr=False, compare=False)


class JobStore:
    def __init__(self, max_jobs: int = 20, runner: Optional[Callable[[Job], None]] = None):
        self._jobs: dict[str, Job] = {}
        self._order: list[str] = []
        self._lock = threading.Lock()
        self._max_jobs = max_jobs
        self._runner = runner or self._translate

    def create(self, data: bytes, source: str, target: str, provider_name: str = "google") -> Job:
        job_id = uuid.uuid4().hex
        tmpdir = Path(tempfile.mkdtemp(prefix="pdftr-"))
        input_path = tmpdir / "input.pdf"
        output_path = tmpdir / "output.pdf"
        input_path.write_bytes(data)
        job = Job(
            id=job_id, source=source, target=target, provider_name=provider_name,
            input_path=input_path, output_path=output_path, tmpdir=tmpdir,
        )
        with self._lock:
            self._jobs[job_id] = job
            self._order.append(job_id)
            self._evict_locked()
        thread = threading.Thread(target=self._execute, args=(job,), daemon=True)
        job.thread = thread
        thread.start()
        return job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def _evict_locked(self) -> None:
        while len(self._order) > self._max_jobs:
            old_id = self._order.pop(0)
            old = self._jobs.pop(old_id, None)
            if old is not None:
                shutil.rmtree(old.tmpdir, ignore_errors=True)

    def _execute(self, job: Job) -> None:
        try:
            self._runner(job)
            job.status = "done"
        except Exception as exc:  # surfaced to the user as a job error
            job.status = "error"
            job.error = f"Translation failed: {exc}"

    def _translate(self, job: Job) -> None:
        provider = providers.build_provider(job.provider_name)

        def progress(index: int, count: int) -> None:
            job.page = index + 1
            job.page_count = count

        engine.translate_pdf(
            str(job.input_path), str(job.output_path),
            source=job.source, target=job.target,
            provider=provider, progress=progress,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_web_jobs.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/pdftranslator/web/jobs.py tests/test_web_jobs.py
git commit -m "feat: add in-memory job store with background runner"
```

---

### Task 3: API endpoints (translate, status, original, result)

**Files:**
- Modify: `src/pdftranslator/web/app.py`
- Modify: `tests/test_web_app.py`

**Interfaces:**
- Consumes: `web.jobs.JobStore`/`Job`, `core.lang.validate_source`/`validate_target`, and (via the default runner) `core.providers.build_provider`.
- Produces these routes on the app:
  - `POST /api/translate` — multipart `file` (UploadFile), `source` (Form), `target` (Form). Validates languages (`400` on bad code), requires a non-empty PDF (`400` otherwise), creates a job via `app.state.store.create(...)`, returns `{"job_id": <id>}`.
  - `GET /api/jobs/{job_id}` — `{"status", "page", "page_count", "error"}`; `404` if unknown.
  - `GET /api/jobs/{job_id}/original` — streams the uploaded PDF; `404` if unknown.
  - `GET /api/jobs/{job_id}/result` — streams the translated PDF; `404` if unknown or not yet `done`.
- `create_app` now defaults `store` to a real `JobStore()` when none is passed.

- [ ] **Step 1: Write the failing test (append to `tests/test_web_app.py`)**

Add these imports at the top of `tests/test_web_app.py` (keep the existing two tests):

```python
import time

import fitz
import requests
import pytest
from pdftranslator.core import providers


def _pdf_bytes(text="hello world"):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text, fontsize=12)
    data = doc.tobytes()
    doc.close()
    return data


def _wait(client, job_id, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        s = client.get(f"/api/jobs/{job_id}").json()
        if s["status"] != "running":
            return s
        time.sleep(0.05)
    raise AssertionError("job did not finish in time")


@pytest.fixture
def fake_google(monkeypatch):
    class Fake:
        def translate(self, texts, source, target):
            return [t.upper() for t in texts]
    monkeypatch.setattr(providers, "build_provider", lambda name: Fake())


def test_translate_then_result_has_translation(fake_google):
    client = TestClient(create_app())
    resp = client.post(
        "/api/translate",
        files={"file": ("in.pdf", _pdf_bytes("hello"), "application/pdf")},
        data={"source": "auto", "target": "en"},
    )
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]

    status = _wait(client, job_id)
    assert status["status"] == "done", status

    result = client.get(f"/api/jobs/{job_id}/result")
    assert result.status_code == 200
    assert result.content[:5].startswith(b"%PDF")
    doc = fitz.open(stream=result.content, filetype="pdf")
    text = doc[0].get_text("text")
    doc.close()
    assert "HELLO" in text


def test_original_is_served(fake_google):
    client = TestClient(create_app())
    job_id = client.post(
        "/api/translate",
        files={"file": ("in.pdf", _pdf_bytes("hello"), "application/pdf")},
        data={"source": "auto", "target": "en"},
    ).json()["job_id"]
    resp = client.get(f"/api/jobs/{job_id}/original")
    assert resp.status_code == 200
    assert resp.content[:5].startswith(b"%PDF")


def test_result_404_before_done(fake_google):
    client = TestClient(create_app())
    # unknown job id → 404
    assert client.get("/api/jobs/nope/result").status_code == 404
    assert client.get("/api/jobs/nope").status_code == 404


def test_bad_target_is_400(fake_google):
    client = TestClient(create_app())
    resp = client.post(
        "/api/translate",
        files={"file": ("in.pdf", _pdf_bytes(), "application/pdf")},
        data={"source": "auto", "target": "fr"},
    )
    assert resp.status_code == 400


def test_non_pdf_is_400(fake_google):
    client = TestClient(create_app())
    resp = client.post(
        "/api/translate",
        files={"file": ("in.txt", b"not a pdf", "text/plain")},
        data={"source": "auto", "target": "en"},
    )
    assert resp.status_code == 400


def test_job_error_surfaces(monkeypatch):
    class Boom:
        def translate(self, texts, source, target):
            raise requests.RequestException("rate limited")
    monkeypatch.setattr(providers, "build_provider", lambda name: Boom())

    client = TestClient(create_app())
    job_id = client.post(
        "/api/translate",
        files={"file": ("in.pdf", _pdf_bytes(), "application/pdf")},
        data={"source": "auto", "target": "en"},
    ).json()["job_id"]
    status = _wait(client, job_id)
    assert status["status"] == "error"
    assert "rate limited" in status["error"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_web_app.py -v`
Expected: FAIL — `POST /api/translate` returns 404/405 (route not defined).

- [ ] **Step 3: Implement the routes**

Rewrite `src/pdftranslator/web/app.py`:

```python
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from ..core import lang
from .jobs import JobStore

STATIC_DIR = Path(__file__).parent / "static"


def create_app(store: JobStore | None = None) -> FastAPI:
    app = FastAPI(title="PDF Translator")
    app.state.store = store or JobStore()
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return (STATIC_DIR / "index.html").read_text(encoding="utf-8")

    @app.post("/api/translate")
    async def translate(
        file: UploadFile = File(...),
        source: str = Form(...),
        target: str = Form(...),
    ) -> dict:
        try:
            lang.validate_source(source)
            lang.validate_target(target)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        data = await file.read()
        if not data:
            raise HTTPException(status_code=400, detail="empty file")
        if not data[:5].startswith(b"%PDF"):
            raise HTTPException(status_code=400, detail="not a PDF file")
        job = app.state.store.create(data, source, target)
        return {"job_id": job.id}

    @app.get("/api/jobs/{job_id}")
    def job_status(job_id: str) -> dict:
        job = app.state.store.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="unknown job")
        return {
            "status": job.status,
            "page": job.page,
            "page_count": job.page_count,
            "error": job.error,
        }

    @app.get("/api/jobs/{job_id}/original")
    def job_original(job_id: str):
        job = app.state.store.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="unknown job")
        return FileResponse(job.input_path, media_type="application/pdf", filename="original.pdf")

    @app.get("/api/jobs/{job_id}/result")
    def job_result(job_id: str):
        job = app.state.store.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="unknown job")
        if job.status != "done":
            raise HTTPException(status_code=404, detail="result not ready")
        return FileResponse(job.output_path, media_type="application/pdf", filename="translated.pdf")

    return app


app = create_app()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_web_app.py -v`
Expected: PASS (all tests in the file)

- [ ] **Step 5: Commit**

```bash
git add src/pdftranslator/web/app.py tests/test_web_app.py
git commit -m "feat: add translate/status/original/result API endpoints"
```

---

### Task 4: Launch entry (console script + `python -m`)

**Files:**
- Create: `src/pdftranslator/web/__main__.py`
- Create: `tests/test_web_main.py`

**Interfaces:**
- Consumes: `web.app.app`.
- Produces: `web.__main__.main()` — opens the default browser to the local URL (shortly after startup) and runs uvicorn on `127.0.0.1:8000`. The `pdftranslate-web` console script (declared in Task 1) and `python -m pdftranslator.web` both call it.

- [ ] **Step 1: Write the failing test**

`tests/test_web_main.py`:

```python
import pdftranslator.web.__main__ as web_main


def test_main_starts_server(monkeypatch):
    calls = {}

    def fake_run(app, host=None, port=None, **kwargs):
        calls["app"] = app
        calls["host"] = host
        calls["port"] = port

    opened = {}
    monkeypatch.setattr(web_main.uvicorn, "run", fake_run)
    monkeypatch.setattr(web_main.webbrowser, "open", lambda url: opened.setdefault("url", url))
    # Prevent the real timer from firing the browser open during the test.
    monkeypatch.setattr(web_main.threading, "Timer", lambda delay, fn: type("T", (), {"start": lambda self: fn()})())

    web_main.main()

    assert calls["host"] == "127.0.0.1"
    assert calls["port"] == 8000
    assert opened["url"] == "http://127.0.0.1:8000"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_web_main.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pdftranslator.web.__main__'`

- [ ] **Step 3: Write minimal implementation**

`src/pdftranslator/web/__main__.py`:

```python
import threading
import webbrowser

import uvicorn

from .app import app

HOST = "127.0.0.1"
PORT = 8000


def main() -> None:
    url = f"http://{HOST}:{PORT}"
    # Open the browser shortly after the server starts accepting connections.
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host=HOST, port=PORT)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_web_main.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/pdftranslator/web/__main__.py tests/test_web_main.py
git commit -m "feat: add web launch entry (console script + python -m)"
```

---

### Task 5: Vanilla frontend (drop, translate, progress, side-by-side preview, download)

**Files:**
- Modify: `src/pdftranslator/web/static/index.html`
- Modify: `src/pdftranslator/web/static/styles.css`
- Modify: `src/pdftranslator/web/static/app.js`
- Modify: `tests/test_web_app.py`

**Interfaces:**
- Consumes: the API routes from Task 3.
- Produces: the full single-page UI. No new Python interfaces.

- [ ] **Step 1: Write the failing test (append to `tests/test_web_app.py`)**

```python
def test_index_has_ui_elements():
    client = TestClient(create_app())
    html = client.get("/").text
    assert 'id="dropzone"' in html
    assert 'id="translateBtn"' in html
    assert 'id="origFrame"' in html
    assert 'id="transFrame"' in html
    assert "/static/app.js" in html


def test_app_js_served_with_logic():
    client = TestClient(create_app())
    js = client.get("/static/app.js").text
    assert "/api/translate" in js
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_web_app.py::test_index_has_ui_elements tests/test_web_app.py::test_app_js_served_with_logic -v`
Expected: FAIL — placeholder index/app.js lack these markers.

- [ ] **Step 3: Write the frontend**

`src/pdftranslator/web/static/index.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>PDF Translator</title>
    <link rel="stylesheet" href="/static/styles.css" />
  </head>
  <body>
    <header><h1>PDF Translator</h1></header>
    <main>
      <section class="controls">
        <div id="dropzone" class="dropzone">
          <p>Drag &amp; drop a PDF here, or <span class="link">browse</span></p>
          <p id="filename" class="filename"></p>
          <input id="fileInput" type="file" accept="application/pdf" hidden />
        </div>
        <div class="langs">
          <label>From
            <select id="from">
              <option value="auto" selected>Auto-detect</option>
              <option value="en">English</option>
              <option value="pt">Portuguese</option>
              <option value="zh">Chinese (Simplified)</option>
            </select>
          </label>
          <label>To
            <select id="to">
              <option value="zh" selected>Chinese (Simplified)</option>
              <option value="en">English</option>
              <option value="pt">Portuguese</option>
            </select>
          </label>
          <button id="translateBtn" disabled>Translate</button>
        </div>
        <div id="error" class="error hidden"></div>
        <div id="progressWrap" class="progress-wrap hidden">
          <div id="progressBar" class="progress-bar"></div>
          <span id="progressText" class="progress-text"></span>
        </div>
      </section>
      <section class="previews">
        <div class="pane">
          <h2>Original</h2>
          <iframe id="origFrame" title="Original PDF"></iframe>
        </div>
        <div class="pane">
          <h2>Translated</h2>
          <iframe id="transFrame" title="Translated PDF"></iframe>
          <a id="download" class="download hidden" download="translated.pdf">Download</a>
        </div>
      </section>
    </main>
    <script src="/static/app.js"></script>
  </body>
</html>
```

`src/pdftranslator/web/static/styles.css`:

```css
:root { --bg: #f4f1ea; --ink: #23201b; --accent: #b5532a; --line: #ddd6c8; }
* { box-sizing: border-box; }
body { margin: 0; font-family: system-ui, -apple-system, sans-serif; color: var(--ink); background: var(--bg); }
header { padding: 1rem 1.5rem; border-bottom: 1px solid var(--line); }
h1 { margin: 0; font-size: 1.25rem; letter-spacing: 0.01em; }
main { padding: 1.5rem; max-width: 1100px; margin: 0 auto; }
.dropzone { border: 2px dashed var(--line); border-radius: 12px; padding: 2rem; text-align: center; cursor: pointer; background: #fffdf8; transition: border-color .15s, background .15s; }
.dropzone.over { border-color: var(--accent); background: #fff7f0; }
.dropzone .link { color: var(--accent); text-decoration: underline; }
.filename { font-size: .9rem; color: #6b6457; margin: .5rem 0 0; }
.langs { display: flex; gap: 1rem; align-items: end; margin: 1rem 0; flex-wrap: wrap; }
.langs label { display: flex; flex-direction: column; font-size: .8rem; gap: .25rem; }
select { padding: .4rem .5rem; border: 1px solid var(--line); border-radius: 6px; background: #fff; }
button { padding: .55rem 1.1rem; border: none; border-radius: 6px; background: var(--accent); color: #fff; cursor: pointer; font-size: .95rem; }
button:disabled { opacity: .5; cursor: not-allowed; }
.error { color: #a12; background: #fde8e6; border: 1px solid #f3c4bf; padding: .6rem .8rem; border-radius: 6px; margin: .5rem 0; }
.progress-wrap { display: flex; align-items: center; gap: .75rem; margin: .5rem 0; }
.progress-bar { height: 8px; background: var(--accent); border-radius: 4px; width: 0; transition: width .3s; flex: 0 0 auto; min-width: 2px; }
.progress-text { font-size: .85rem; color: #6b6457; }
.previews { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-top: 1rem; }
.pane h2 { font-size: .9rem; margin: 0 0 .4rem; color: #6b6457; font-weight: 600; }
iframe { width: 100%; height: 70vh; border: 1px solid var(--line); border-radius: 8px; background: #fff; }
.download { display: inline-block; margin-top: .6rem; padding: .5rem 1rem; background: var(--ink); color: #fff; border-radius: 6px; text-decoration: none; font-size: .9rem; }
.hidden { display: none; }
@media (max-width: 760px) { .previews { grid-template-columns: 1fr; } }
```

`src/pdftranslator/web/static/app.js`:

```javascript
const state = { file: null, jobId: null, poll: null };
const $ = (id) => document.getElementById(id);

function showError(msg) { const e = $("error"); e.textContent = msg; e.classList.remove("hidden"); }
function clearError() { $("error").classList.add("hidden"); }
function stopPoll() { if (state.poll) { clearInterval(state.poll); state.poll = null; } }
function fail(msg) { stopPoll(); $("progressWrap").classList.add("hidden"); $("translateBtn").disabled = false; showError(msg); }

function setProgress(page, count, text) {
  $("progressWrap").classList.remove("hidden");
  const pct = count > 0 ? Math.round((page / count) * 100) : 5;
  $("progressBar").style.width = pct + "%";
  $("progressText").textContent = text;
}

function setFile(f) {
  if (!f) return;
  const isPdf = f.type === "application/pdf" || f.name.toLowerCase().endsWith(".pdf");
  if (!isPdf) { showError("Please choose a PDF file."); return; }
  clearError();
  state.file = f;
  $("filename").textContent = f.name;
  $("translateBtn").disabled = false;
}

async function safeDetail(res) {
  try { const j = await res.json(); return j.detail; } catch { return null; }
}

async function startTranslate() {
  if (!state.file) return;
  clearError();
  $("download").classList.add("hidden");
  $("transFrame").removeAttribute("src");
  $("translateBtn").disabled = true;
  setProgress(0, 0, "Uploading…");

  const fd = new FormData();
  fd.append("file", state.file);
  fd.append("source", $("from").value);
  fd.append("target", $("to").value);

  let res;
  try { res = await fetch("/api/translate", { method: "POST", body: fd }); }
  catch { return fail("Network error during upload."); }
  if (!res.ok) { return fail((await safeDetail(res)) || "Upload failed."); }

  const { job_id } = await res.json();
  state.jobId = job_id;
  $("origFrame").src = `/api/jobs/${job_id}/original`;
  pollStatus();
}

function pollStatus() {
  stopPoll();
  state.poll = setInterval(async () => {
    let res;
    try { res = await fetch(`/api/jobs/${state.jobId}`); } catch { return; }
    if (!res.ok) return;
    const s = await res.json();
    if (s.status === "running") {
      setProgress(s.page, s.page_count, s.page_count ? `Translating page ${s.page} / ${s.page_count}…` : "Starting…");
    } else if (s.status === "done") {
      stopPoll();
      setProgress(1, 1, "Done");
      const url = `/api/jobs/${state.jobId}/result`;
      $("transFrame").src = url;
      const dl = $("download");
      dl.href = url;
      dl.classList.remove("hidden");
      $("translateBtn").disabled = false;
    } else if (s.status === "error") {
      fail(s.error || "Translation failed.");
    }
  }, 1000);
}

function wireUp() {
  const drop = $("dropzone");
  drop.addEventListener("click", () => $("fileInput").click());
  $("fileInput").addEventListener("change", (e) => setFile(e.target.files[0]));
  ["dragover", "dragenter"].forEach((ev) =>
    drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach((ev) =>
    drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
  drop.addEventListener("drop", (e) => setFile(e.dataTransfer.files[0]));
  $("translateBtn").addEventListener("click", startTranslate);
}

document.addEventListener("DOMContentLoaded", wireUp);
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_web_app.py -v`
Expected: PASS (all tests in the file, including the two new ones)

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -q`
Expected: all tests pass (Phase-1 21 + the new web tests).

- [ ] **Step 6: Manual verification**

```bash
. .venv/bin/activate
PYTHONPATH=src pdftranslate-web
```
In the browser that opens: drop a digital PDF, pick From/To, click Translate, watch the progress bar, confirm the side-by-side preview renders and the translated text/layout looks right, then Download. Stop the server with Ctrl-C.

- [ ] **Step 7: Commit**

```bash
git add src/pdftranslator/web/static tests/test_web_app.py
git commit -m "feat: add vanilla web frontend with side-by-side preview"
```

---

## Self-Review Notes

- **Spec coverage:** FastAPI app + static (Task 1), in-memory threaded job store with progress + eviction (Task 2), `POST /api/translate` with language validation + PDF sniff + the status/original/result routes (Task 3), `pdftranslate-web` / `python -m` launch opening the browser (Task 4), vanilla drag-drop UI with language selects, live progress, side-by-side `<iframe>` preview, and download (Task 5). Error handling (bad code → 400, job failure → `error` surfaced, unknown/not-ready → 404) is covered by Task 3 tests. Out-of-scope items (LLM key, desktop packaging, OCR) are excluded by design.
- **No network in tests:** API tests monkeypatch `providers.build_provider` to a fake; `JobStore` tests inject a fake `runner`; PDFs are built in-memory with `fitz`.
- **Type consistency:** `JobStore.create(data, source, target, provider_name="google")`, `Job` fields, and `create_app(store=None)` are used identically across tasks. `app.state.store` is the single store handle the routes read.
