# PDF Translator — UI Redesign + Engine Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the single-page web UI to the hi-fi handoff (text-reader panes), and let users pick the translation engine — Google (free), Claude, or OpenAI (key entered in the UI, saved locally).

**Architecture:** Reuse the Phase-1 engine and the in-memory threaded `JobStore`. Add LLM providers behind the existing `TranslationProvider` interface, a local key store, and JSON endpoints that expose per-page original/translated text + job metadata. Rebuild the vanilla frontend to the handoff with an engine menu.

**Tech Stack:** Python 3.11+, FastAPI, uvicorn, PyMuPDF, the `anthropic` and `openai` SDKs; vanilla HTML/CSS/JS; pytest + Starlette TestClient.

## Global Constraints

- Python `>=3.11`. New runtime deps: `anthropic>=0.40`, `openai>=1.40` (added to pyproject; install with `pip install -e ".[dev]"`).
- Reuse unchanged: `core.engine.translate_pdf(input_path, output_path, source, target, provider, progress=None)`, `core.lang.validate_source/validate_target`, the `core.providers.GoogleProvider`.
- Engines: `"google"` (no key), `"claude"`, `"openai"`. Default models: Claude `claude-haiku-4-5`, OpenAI `gpt-4o-mini`.
- Internal language codes: source ∈ {`auto`,`en`,`pt`,`zh`}, target ∈ {`en`,`pt`,`zh`}.
- Keys saved locally to `~/.config/pdftranslator/config.json` (override dir via env `PDFTRANSLATOR_CONFIG_DIR`); never returned by any GET.
- History is **session-only** (the in-memory `JobStore`); no database.
- Design values are authoritative in `docs/design/redesign-handoff.md`; SVG icons are copied from `docs/design/redesign-prototype.dc.html` (do NOT copy its `<x-dc>`/`<sc-if>` scaffolding).
- Tests must not hit the network: mock the LLM SDK clients (inject `client=`), use the fake provider + in-memory PDFs for endpoints, and a temp `PDFTRANSLATOR_CONFIG_DIR` for settings.
- pytest is configured with `pythonpath = ["src"]`. TDD: red → green → commit. Plain Conventional Commits, NO co-author trailer.
- Work from `pdfTranslator/`; activate `.venv`. The git repo root is the parent `Development/` directory shared with other projects — only `git add` files under `pdfTranslator/`.

---

### Task 1: Enrich `Job` and `JobStore`

**Files:**
- Modify: `src/pdftranslator/web/jobs.py`
- Modify: `tests/test_web_jobs.py`

**Interfaces:**
- Consumes: `core.engine.translate_pdf`.
- Produces:
  - `Job` dataclass fields: `id, source, target, engine, filename, size_bytes, page_count, input_path, output_path, tmpdir, provider=None, created_at=0.0, status="running", page=0, error=None, thread=None`.
  - `JobStore.create(data: bytes, source: str, target: str, *, engine="google", provider=None, filename="document.pdf", page_count=0) -> Job` — `size_bytes` is `len(data)`, `created_at` is `time.time()`; stores `provider` on the job; registers/evicts under lock; starts the background thread; sets `job.thread`.
  - `JobStore.get(job_id) -> Job | None` (unchanged).
  - `JobStore.list() -> list[Job]` — newest first.
  - Default runner `_translate(job)` uses `job.provider` (raises `RuntimeError` if `None`) and a progress callback that sets `job.page = index + 1`.

- [ ] **Step 1: Write the failing test (replace the body of `tests/test_web_jobs.py`)**

```python
import time

import requests
from pdftranslator.web.jobs import JobStore


def test_job_runs_to_done_with_metadata():
    def fake_runner(job):
        job.page = job.page_count

    store = JobStore(runner=fake_runner)
    job = store.create(
        b"%PDF-1.4 data", "auto", "zh",
        engine="google", filename="report.pdf", page_count=3,
    )
    job.thread.join(timeout=5)

    got = store.get(job.id)
    assert got.status == "done"
    assert got.filename == "report.pdf"
    assert got.size_bytes == len(b"%PDF-1.4 data")
    assert got.page_count == 3
    assert got.engine == "google"
    assert got.created_at > 0


def test_runner_failure_sets_error():
    def boom(job):
        raise requests.RequestException("rate limited")

    store = JobStore(runner=boom)
    job = store.create(b"%PDF", "auto", "en")
    job.thread.join(timeout=5)
    assert store.get(job.id).status == "error"
    assert "rate limited" in store.get(job.id).error


def test_default_runner_requires_provider():
    # No runner injected and no provider → the job ends in error, not a crash.
    store = JobStore()
    job = store.create(b"%PDF", "auto", "en", provider=None)
    job.thread.join(timeout=5)
    assert store.get(job.id).status == "error"


def test_list_returns_newest_first():
    def fake_runner(job):
        job.page = 1

    store = JobStore(runner=fake_runner)
    a = store.create(b"%PDF", "auto", "en", filename="a.pdf")
    b = store.create(b"%PDF", "auto", "en", filename="b.pdf")
    a.thread.join(timeout=5)
    b.thread.join(timeout=5)
    names = [j.filename for j in store.list()]
    assert names[0] == "b.pdf" and names[1] == "a.pdf"


def test_store_evicts_oldest_terminal_and_removes_tmpdir():
    def fake_runner(job):
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
Expected: FAIL — `create()` got an unexpected keyword / missing fields.

- [ ] **Step 3: Rewrite `src/pdftranslator/web/jobs.py`**

```python
import shutil
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from ..core import engine


@dataclass
class Job:
    id: str
    source: str
    target: str
    engine: str
    filename: str
    size_bytes: int
    page_count: int
    input_path: Path
    output_path: Path
    tmpdir: Path
    provider: object = None
    created_at: float = 0.0
    status: str = "running"
    page: int = 0
    error: Optional[str] = None
    thread: Optional[threading.Thread] = field(default=None, repr=False, compare=False)


class JobStore:
    def __init__(self, max_jobs: int = 20, runner: Optional[Callable[[Job], None]] = None):
        self._jobs: dict[str, Job] = {}
        self._order: list[str] = []
        self._lock = threading.Lock()
        self._max_jobs = max_jobs
        self._runner = runner or self._translate

    def create(self, data: bytes, source: str, target: str, *, engine: str = "google",
               provider: object = None, filename: str = "document.pdf",
               page_count: int = 0) -> Job:
        job_id = uuid.uuid4().hex
        tmpdir = Path(tempfile.mkdtemp(prefix="pdftr-"))
        input_path = tmpdir / "input.pdf"
        output_path = tmpdir / "output.pdf"
        input_path.write_bytes(data)
        job = Job(
            id=job_id, source=source, target=target, engine=engine,
            filename=filename, size_bytes=len(data), page_count=page_count,
            input_path=input_path, output_path=output_path, tmpdir=tmpdir,
            provider=provider, created_at=time.time(),
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

    def list(self) -> list[Job]:
        with self._lock:
            return [self._jobs[i] for i in reversed(self._order) if i in self._jobs]

    def _evict_locked(self) -> None:
        while len(self._order) > self._max_jobs:
            victim_id = None
            for jid in self._order:
                j = self._jobs.get(jid)
                if j is None or j.status != "running":
                    victim_id = jid
                    break
            if victim_id is None:
                break
            self._order.remove(victim_id)
            old = self._jobs.pop(victim_id, None)
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
        if job.provider is None:
            raise RuntimeError("no translation provider configured")

        def progress(index: int, count: int) -> None:
            job.page = index + 1

        engine.translate_pdf(
            str(job.input_path), str(job.output_path),
            source=job.source, target=job.target,
            provider=job.provider, progress=progress,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_web_jobs.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/pdftranslator/web/jobs.py tests/test_web_jobs.py
git commit -m "feat: enrich Job with metadata and provider; add JobStore.list"
```

---

### Task 2: Local API-key store (`web.settings`)

**Files:**
- Create: `src/pdftranslator/web/settings.py`
- Create: `tests/test_web_settings.py`

**Interfaces:**
- Produces: `settings.get_key(engine) -> str | None`, `settings.set_key(engine, key) -> None` (raises `ValueError` for engines without storage), `settings.has_key(engine) -> bool`. Storage dir from `PDFTRANSLATOR_CONFIG_DIR` else `~/.config/pdftranslator`.

- [ ] **Step 1: Write the failing test**

`tests/test_web_settings.py`:

```python
import importlib


def test_set_get_has_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("PDFTRANSLATOR_CONFIG_DIR", str(tmp_path))
    settings = importlib.import_module("pdftranslator.web.settings")

    assert settings.has_key("claude") is False
    assert settings.get_key("claude") is None

    settings.set_key("claude", "sk-ant-123")
    assert settings.get_key("claude") == "sk-ant-123"
    assert settings.has_key("claude") is True
    # openai still unset and independent
    assert settings.has_key("openai") is False


def test_unknown_engine_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("PDFTRANSLATOR_CONFIG_DIR", str(tmp_path))
    settings = importlib.import_module("pdftranslator.web.settings")
    import pytest
    with pytest.raises(ValueError):
        settings.set_key("google", "x")
    assert settings.get_key("google") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_web_settings.py -v`
Expected: FAIL — `No module named 'pdftranslator.web.settings'`

- [ ] **Step 3: Write `src/pdftranslator/web/settings.py`**

```python
import json
import os
from pathlib import Path

_ENGINE_KEY = {"claude": "claude_api_key", "openai": "openai_api_key"}


def _config_dir() -> Path:
    override = os.environ.get("PDFTRANSLATOR_CONFIG_DIR")
    base = Path(override) if override else Path.home() / ".config" / "pdftranslator"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _config_file() -> Path:
    return _config_dir() / "config.json"


def _load() -> dict:
    f = _config_file()
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return {}
    return {}


def _save(data: dict) -> None:
    f = _config_file()
    f.write_text(json.dumps(data), encoding="utf-8")
    try:
        os.chmod(f, 0o600)
    except OSError:
        pass


def get_key(engine: str) -> str | None:
    field = _ENGINE_KEY.get(engine)
    if field is None:
        return None
    return _load().get(field)


def set_key(engine: str, key: str) -> None:
    field = _ENGINE_KEY.get(engine)
    if field is None:
        raise ValueError(f"no key storage for engine: {engine}")
    data = _load()
    data[field] = key
    _save(data)


def has_key(engine: str) -> bool:
    return bool(get_key(engine))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_web_settings.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/pdftranslator/web/settings.py tests/test_web_settings.py
git commit -m "feat: add local API-key storage"
```

---

### Task 3: LLM providers + engine-aware `build_provider`

**Files:**
- Modify: `pyproject.toml` (add `anthropic`, `openai`)
- Modify: `src/pdftranslator/core/providers.py`
- Modify: `tests/test_providers.py`

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `AnthropicProvider(api_key, model="claude-haiku-4-5", client=None, batch_size=40)` and `OpenAIProvider(api_key, model="gpt-4o-mini", client=None, batch_size=40)`, each with `translate(texts, source, target) -> list[str]`. They batch the input, ask the model for a same-length JSON array, and fall back to per-line on a count mismatch.
  - `build_provider(engine: str, *, api_key: str | None = None) -> TranslationProvider` — routes `google`/`claude`/`openai`; raises `ValueError` for unknown engine or a missing LLM key. (The old `build_provider("google")` call still works.)

- [ ] **Step 1: Add deps and install**

Edit `pyproject.toml` `dependencies` to add:
```toml
    "anthropic>=0.40",
    "openai>=1.40",
```
Run:
```bash
. .venv/bin/activate
pip install -e ".[dev]" -q
```
Expected: installs with no errors.

- [ ] **Step 2: Write the failing test (append to `tests/test_providers.py`)**

```python
class FakeAnthropicMessage:
    def __init__(self, text):
        self.content = [type("B", (), {"type": "text", "text": text})()]


class FakeAnthropicClient:
    def __init__(self, texts):
        self._texts = list(texts)
        self.calls = []

        class _Messages:
            def __init__(self, outer):
                self._outer = outer

            def create(self, model, max_tokens, system, messages):
                self._outer.calls.append(messages[0]["content"])
                idx = min(len(self._outer.calls) - 1, len(self._outer._texts) - 1)
                return FakeAnthropicMessage(self._outer._texts[idx])

        self.messages = _Messages(self)


def test_anthropic_batch_returns_translations():
    client = FakeAnthropicClient(['["你好", "世界"]'])
    provider = providers.AnthropicProvider(api_key="x", client=client)
    assert provider.translate(["Hello", "World"], "en", "zh") == ["你好", "世界"]
    assert len(client.calls) == 1  # one batched call


def test_anthropic_falls_back_per_line_on_count_mismatch():
    # First (batch) call returns the wrong count; then one call per line.
    client = FakeAnthropicClient(['["only-one"]', '["A"]', '["B"]'])
    provider = providers.AnthropicProvider(api_key="x", client=client)
    out = provider.translate(["Hello", "World"], "en", "zh")
    assert out == ["A", "B"]
    assert len(client.calls) == 3  # 1 failed batch + 2 per-line


def test_anthropic_strips_code_fences():
    client = FakeAnthropicClient(['```json\n["你好"]\n```'])
    provider = providers.AnthropicProvider(api_key="x", client=client)
    assert provider.translate(["Hello"], "en", "zh") == ["你好"]


def test_build_provider_routes_engines():
    assert isinstance(providers.build_provider("google"), providers.GoogleProvider)
    assert isinstance(
        providers.build_provider("claude", api_key="k"), providers.AnthropicProvider
    )
    assert isinstance(
        providers.build_provider("openai", api_key="k"), providers.OpenAIProvider
    )


def test_build_provider_requires_llm_key():
    with pytest.raises(ValueError):
        providers.build_provider("claude")
    with pytest.raises(ValueError):
        providers.build_provider("openai", api_key="")
    with pytest.raises(ValueError):
        providers.build_provider("bogus")
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_providers.py -v`
Expected: FAIL — `module 'providers' has no attribute 'AnthropicProvider'`.

- [ ] **Step 4: Append to `src/pdftranslator/core/providers.py`**

```python
import json

_LANG_NAMES = {
    "en": "English",
    "pt": "Portuguese",
    "zh": "Simplified Chinese",
    "auto": "the source language (auto-detect)",
}


def _lang_name(code: str) -> str:
    return _LANG_NAMES.get(code, code)


def _strip_fences(text: str) -> str:
    s = text.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s[3:]
        if s.endswith("```"):
            s = s[: -3]
    return s.strip()


class _LLMProvider:
    SYSTEM = (
        "You are a professional translator. You receive a JSON array of text lines. "
        "Translate each line from {source} into {target}. Return ONLY a JSON array of "
        "strings, the same length and order as the input, each being the translation of "
        "the corresponding line. Preserve inline numbers, symbols and code. Do not add "
        "commentary or code fences."
    )

    def __init__(self, batch_size: int = 40):
        self._batch_size = batch_size

    def translate(self, texts: list[str], source: str, target: str) -> list[str]:
        out: list[str] = []
        for i in range(0, len(texts), self._batch_size):
            out.extend(self._batch(texts[i : i + self._batch_size], source, target))
        return out

    def _batch(self, lines: list[str], source: str, target: str) -> list[str]:
        if not lines:
            return []
        parsed = self._translate_lines(lines, source, target)
        if parsed is not None and len(parsed) == len(lines):
            return [str(x) for x in parsed]
        # Count mismatch or parse failure: translate one line at a time.
        result = []
        for line in lines:
            if not line.strip():
                result.append(line)
                continue
            single = self._translate_lines([line], source, target)
            result.append(str(single[0]) if single else line)
        return result

    def _translate_lines(self, lines: list[str], source: str, target: str):
        system = self.SYSTEM.format(source=_lang_name(source), target=_lang_name(target))
        raw = self._complete(system, json.dumps(lines, ensure_ascii=False))
        try:
            data = json.loads(_strip_fences(raw))
        except (ValueError, TypeError):
            return None
        return data if isinstance(data, list) else None

    def _complete(self, system: str, user: str) -> str:
        raise NotImplementedError


class AnthropicProvider(_LLMProvider):
    def __init__(self, api_key: str, model: str = "claude-haiku-4-5", client=None, batch_size: int = 40):
        super().__init__(batch_size)
        self._model = model
        if client is not None:
            self._client = client
        else:
            import anthropic
            self._client = anthropic.Anthropic(api_key=api_key)

    def _complete(self, system: str, user: str) -> str:
        msg = self._client.messages.create(
            model=self._model, max_tokens=8000, system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(
            getattr(b, "text", "") for b in msg.content if getattr(b, "type", None) == "text"
        )


class OpenAIProvider(_LLMProvider):
    def __init__(self, api_key: str, model: str = "gpt-4o-mini", client=None, batch_size: int = 40):
        super().__init__(batch_size)
        self._model = model
        if client is not None:
            self._client = client
        else:
            import openai
            self._client = openai.OpenAI(api_key=api_key)

    def _complete(self, system: str, user: str) -> str:
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return resp.choices[0].message.content or ""
```

Then replace the existing `build_provider` function with:

```python
def build_provider(engine: str, *, api_key: str | None = None) -> TranslationProvider:
    if engine == "google":
        return GoogleProvider()
    if engine == "claude":
        if not api_key:
            raise ValueError("no Claude API key saved")
        return AnthropicProvider(api_key)
    if engine == "openai":
        if not api_key:
            raise ValueError("no OpenAI API key saved")
        return OpenAIProvider(api_key)
    raise ValueError(f"unknown engine: {engine}")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_providers.py -v`
Expected: PASS (all provider tests)

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/pdftranslator/core/providers.py tests/test_providers.py
git commit -m "feat: add Claude and OpenAI translation providers"
```

---

### Task 4: API — settings, jobs list, enriched status, per-page text

**Files:**
- Modify: `src/pdftranslator/web/app.py`
- Modify: `tests/test_web_app.py`

**Interfaces:**
- Consumes: `web.settings`, `web.jobs.JobStore`, `fitz`.
- Produces routes:
  - `GET /api/settings` → `{"claude": bool, "openai": bool}` (from `settings.has_key`).
  - `POST /api/settings` (form `engine`, `api_key`) → `{"ok": true}`; `400` for an engine without key storage.
  - `GET /api/jobs` → `[{id, filename, source, target, status, page_count, created_at}, …]` newest first.
  - `GET /api/jobs/{id}` → adds `filename, size_bytes, source, target, engine` to the existing fields.
  - `GET /api/jobs/{id}/text?which=original|result` → `{"pages": [text, …]}`; `result` requires `done`; `404` unknown/not-ready; `400` invalid `which`.

- [ ] **Step 1: Write the failing test (append to `tests/test_web_app.py`)**

```python
def test_settings_get_and_post(tmp_path, monkeypatch):
    monkeypatch.setenv("PDFTRANSLATOR_CONFIG_DIR", str(tmp_path))
    client = TestClient(create_app())
    assert client.get("/api/settings").json() == {"claude": False, "openai": False}
    r = client.post("/api/settings", data={"engine": "claude", "api_key": "sk-x"})
    assert r.status_code == 200
    assert client.get("/api/settings").json()["claude"] is True
    # the key value is never returned
    assert "sk-x" not in client.get("/api/settings").text


def test_settings_bad_engine_400(tmp_path, monkeypatch):
    monkeypatch.setenv("PDFTRANSLATOR_CONFIG_DIR", str(tmp_path))
    client = TestClient(create_app())
    assert client.post("/api/settings", data={"engine": "google", "api_key": "x"}).status_code == 400


def test_jobs_list_and_text(fake_google):
    client = TestClient(create_app())
    job_id = client.post(
        "/api/translate",
        files={"file": ("doc.pdf", _pdf_bytes("hello world"), "application/pdf")},
        data={"source": "auto", "target": "en"},
    ).json()["job_id"]
    _wait(client, job_id)

    listing = client.get("/api/jobs").json()
    assert any(j["id"] == job_id and j["filename"] == "doc.pdf" for j in listing)

    status = client.get(f"/api/jobs/{job_id}").json()
    assert status["filename"] == "doc.pdf"
    assert status["page_count"] >= 1
    assert status["target"] == "en"

    orig = client.get(f"/api/jobs/{job_id}/text?which=original").json()
    assert "hello world" in " ".join(orig["pages"]).lower()
    trans = client.get(f"/api/jobs/{job_id}/text?which=result").json()
    assert "HELLO" in " ".join(trans["pages"])  # fake provider uppercases


def test_text_invalid_which_400(fake_google):
    client = TestClient(create_app())
    job_id = client.post(
        "/api/translate",
        files={"file": ("doc.pdf", _pdf_bytes(), "application/pdf")},
        data={"source": "auto", "target": "en"},
    ).json()["job_id"]
    _wait(client, job_id)
    assert client.get(f"/api/jobs/{job_id}/text?which=nope").status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_web_app.py -v`
Expected: FAIL — `/api/settings` route missing (404/405).

- [ ] **Step 3: Edit `src/pdftranslator/web/app.py`**

Add imports near the top (keep existing ones):

```python
from . import settings
```

Add a per-page text helper above `create_app` (after the `PREVIEW_DPI` line):

```python
def _page_texts(path: Path) -> list[str]:
    doc = fitz.open(path)
    try:
        return [doc[i].get_text("text") for i in range(doc.page_count)]
    finally:
        doc.close()
```

Inside `create_app`, update `job_status` to return the extra fields, and add the new routes (place alongside the other `@app.get`/`@app.post` handlers):

```python
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
            "filename": job.filename,
            "size_bytes": job.size_bytes,
            "source": job.source,
            "target": job.target,
            "engine": job.engine,
        }

    @app.get("/api/jobs")
    def jobs_list() -> list:
        return [
            {
                "id": j.id,
                "filename": j.filename,
                "source": j.source,
                "target": j.target,
                "status": j.status,
                "page_count": j.page_count,
                "created_at": j.created_at,
            }
            for j in app.state.store.list()
        ]

    @app.get("/api/jobs/{job_id}/text")
    def job_text(job_id: str, which: str = "result") -> dict:
        job = app.state.store.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="unknown job")
        if which == "original":
            path = job.input_path
        elif which == "result":
            if job.status != "done":
                raise HTTPException(status_code=404, detail="result not ready")
            path = job.output_path
        else:
            raise HTTPException(status_code=400, detail="invalid document")
        return {"pages": _page_texts(path)}

    @app.get("/api/settings")
    def get_settings() -> dict:
        return {"claude": settings.has_key("claude"), "openai": settings.has_key("openai")}

    @app.post("/api/settings")
    def save_settings(engine: str = Form(...), api_key: str = Form(...)) -> dict:
        try:
            settings.set_key(engine, api_key)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {"ok": True}
```

> Note: there is an existing `job_status` route — replace it with the version above (don't add a duplicate).

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_web_app.py -v`
Expected: PASS (existing + new)

- [ ] **Step 5: Commit**

```bash
git add src/pdftranslator/web/app.py tests/test_web_app.py
git commit -m "feat: add settings, jobs list, and per-page text endpoints"
```

---

### Task 5: `POST /api/translate` selects the engine

**Files:**
- Modify: `src/pdftranslator/web/app.py`
- Modify: `tests/test_web_app.py`

**Interfaces:**
- Consumes: `core.providers.build_provider`, `web.settings`, `fitz`.
- Produces: `POST /api/translate` now accepts a form field `engine` (default `"google"`). For `claude`/`openai` it loads the saved key (`400` if missing), builds the provider, computes `page_count` from the PDF, and creates the job with `engine`, `provider`, `filename`, `page_count`.

- [ ] **Step 1: Write the failing test (append to `tests/test_web_app.py`)**

```python
def test_translate_llm_without_key_is_400(tmp_path, monkeypatch):
    monkeypatch.setenv("PDFTRANSLATOR_CONFIG_DIR", str(tmp_path))
    client = TestClient(create_app())
    r = client.post(
        "/api/translate",
        files={"file": ("d.pdf", _pdf_bytes(), "application/pdf")},
        data={"source": "auto", "target": "en", "engine": "claude"},
    )
    assert r.status_code == 400
    assert "key" in r.json()["detail"].lower()


def test_translate_defaults_to_google(fake_google):
    client = TestClient(create_app())
    r = client.post(
        "/api/translate",
        files={"file": ("d.pdf", _pdf_bytes("hi"), "application/pdf")},
        data={"source": "auto", "target": "en"},  # no engine field
    )
    assert r.status_code == 200
    job_id = r.json()["job_id"]
    _wait(client, job_id)
    assert client.get(f"/api/jobs/{job_id}").json()["engine"] == "google"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_web_app.py::test_translate_llm_without_key_is_400 -v`
Expected: FAIL — engine not handled / no 400.

- [ ] **Step 3: Replace the `translate` handler in `src/pdftranslator/web/app.py`**

Add imports (keep existing): `from ..core import lang, providers`.

```python
    @app.post("/api/translate")
    async def translate(
        file: UploadFile = File(...),
        source: str = Form(...),
        target: str = Form(...),
        engine: str = Form("google"),
    ) -> dict:
        try:
            lang.validate_source(source)
            lang.validate_target(target)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        api_key = None
        if engine in ("claude", "openai"):
            api_key = settings.get_key(engine)
            if not api_key:
                label = "Claude" if engine == "claude" else "OpenAI"
                raise HTTPException(status_code=400, detail=f"Add your {label} API key first.")
        try:
            provider = providers.build_provider(engine, api_key=api_key)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        data = await file.read()
        if not data:
            raise HTTPException(status_code=400, detail="empty file")
        if not data.startswith(b"%PDF"):
            raise HTTPException(status_code=400, detail="not a PDF file")
        try:
            doc = fitz.open(stream=data, filetype="pdf")
            page_count = doc.page_count
            doc.close()
        except Exception:
            raise HTTPException(status_code=400, detail="could not read PDF")

        job = app.state.store.create(
            data, source, target,
            engine=engine, provider=provider,
            filename=file.filename or "document.pdf", page_count=page_count,
        )
        return {"job_id": job.id}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_web_app.py -v`
Expected: PASS (all). Then run the full suite: `python -m pytest -q` — all green.

- [ ] **Step 5: Commit**

```bash
git add src/pdftranslator/web/app.py tests/test_web_app.py
git commit -m "feat: select translation engine on translate request"
```

---

### Task 6: Frontend — redesigned layout, controls, and text-reader panes

**Files:**
- Rewrite: `src/pdftranslator/web/static/index.html`
- Rewrite: `src/pdftranslator/web/static/styles.css`
- Modify: `tests/test_web_app.py`

**Reference (read these for exact values — they are in the repo):**
- `docs/design/redesign-handoff.md` — every color, size, spacing, shadow, font, and per-component spec.
- `docs/design/redesign-prototype.dc.html` — copy the 9 inline SVG icons (upload, clock-history, chevron-down, swap, arrow-right, download, checkmark, file). Do NOT copy `<x-dc>`/`<sc-if>`/`support.js` scaffolding.

**DOM contract (stable ids/classes the JS and tests depend on — build the markup to the handoff but use exactly these hooks):**
- Header: `.wordmark` (contains 文), button `#historyBtn`.
- Dropzone: `#dropzone`, hidden `#fileInput` (`accept="application/pdf"`), file sub-line `#fileMeta`.
- Controls: `#from` (select), `#swapBtn`, `#to` (select), `#engine` (select: options `google`/`claude`/`openai`), `#apiKeyWrap` (hidden unless an LLM engine is chosen) containing `#apiKey` (input) + `#saveKeyBtn`, `#translateBtn`.
- Status bar: `#statusBar` with children `#statusIdle`, `#statusProgress` (text `#progressText` + bar `#progressBar`), `#statusDone` (with `#downloadBtn`), `#statusError` (text `#errorText` + `#retryBtn`). Only one shown at a time.
- Panes: `#origView` and `#transView` (scrollable bodies), badges `#origBadge` / `#transBadge`.
- History panel: `#historyPanel` (hidden by default), list container `#historyList`.

**Interfaces:**
- Consumes: the Task 4/5 endpoints.
- Produces: the static page; behavior wired in Task 7.

- [ ] **Step 1: Write the failing test (append to `tests/test_web_app.py`)**

```python
def test_redesign_structure_present():
    client = TestClient(create_app())
    html = client.get("/").text
    for hook in (
        'id="dropzone"', 'id="from"', 'id="to"', 'id="engine"', 'id="swapBtn"',
        'id="translateBtn"', 'id="origView"', 'id="transView"', 'id="historyBtn"',
        'id="statusBar"', 'id="apiKey"',
    ):
        assert hook in html, hook
    # design tokens / fonts wired
    assert "#1B66C9" in html or "1B66C9" in client.get("/static/styles.css").text
    assert "Hanken Grotesk" in client.get("/static/styles.css").text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_web_app.py::test_redesign_structure_present -v`
Expected: FAIL — old markup lacks these hooks.

- [ ] **Step 3: Rewrite `index.html` and `styles.css`**

Build `src/pdftranslator/web/static/index.html` to the handoff layout (header → dropzone → controls → status bar → panes, centered column `max-width:1180px`), using the DOM contract ids above and the 文 wordmark. Include the Google Fonts `<link>` from the prototype (Hanken Grotesk, IBM Plex Mono, Noto Sans SC). Add the engine `<select>` (`#engine`) into the controls row after the To select, and an `#apiKeyWrap` (an `#apiKey` text input + `#saveKeyBtn`) that is `hidden` by default. Add a `#historyPanel` (hidden) after the header. Reference `<script src="/static/app.js"></script>` at the end of `<body>`.

Build `src/pdftranslator/web/static/styles.css` to the handoff's Design Tokens and per-component specs exactly: page bg `#F8F9FA`, accent `--accent:#1B66C9`, border `#DADCE0`, square corners (`border-radius:0`) except circular badges (`999px`), the button/select/dropzone/status/pane styles, the `.scrollpane` custom scrollbar (10px, thumb `#DADCE0` with 3px white inset), and the Noto Sans SC stack for `.pane-trans` bodies. Acceptance: the values in §Design Tokens and §Components of `docs/design/redesign-handoff.md` are reproduced (colors, the listed font sizes, spacing scale, shadows).

> This task delivers the static structure + styling. The dynamic behavior (upload, translate, polling, panes fill, engine menu, history, swap, status states) is Task 7; for now `app.js` may remain the previous file — Task 7 rewrites it. The page should render without JS errors (guard against missing handlers by leaving `app.js` loading last).

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_web_app.py::test_redesign_structure_present -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/pdftranslator/web/static/index.html src/pdftranslator/web/static/styles.css tests/test_web_app.py
git commit -m "feat: redesigned layout and styling per handoff"
```

---

### Task 7: Frontend — behavior (upload, engine menu, translate, panes, status, history, swap)

**Files:**
- Rewrite: `src/pdftranslator/web/static/app.js`
- Modify: `tests/test_web_app.py`

**Interfaces:**
- Consumes: the Task 4/5 endpoints and the DOM contract from Task 6.

- [ ] **Step 1: Write the failing test (append to `tests/test_web_app.py`)**

```python
def test_app_js_calls_text_and_settings_endpoints():
    client = TestClient(create_app())
    js = client.get("/static/app.js").text
    assert "/api/translate" in js
    assert "/api/jobs/" in js and "/text?which=" in js
    assert "/api/settings" in js
    assert "engine" in js  # sends the engine field
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_web_app.py::test_app_js_calls_text_and_settings_endpoints -v`
Expected: FAIL — current app.js lacks these calls.

- [ ] **Step 3: Rewrite `src/pdftranslator/web/static/app.js`**

```javascript
const $ = (id) => document.getElementById(id);
const state = { file: null, jobId: null, poll: null };

const LANG_BADGE = { auto: "AUTO", en: "EN", pt: "PT", zh: "ZH" };

function showStatus(which) {
  for (const id of ["statusIdle", "statusProgress", "statusDone", "statusError"]) {
    const el = $(id);
    if (el) el.classList.toggle("hidden", id !== which);
  }
  $("statusBar").classList.remove("hidden");
}

function setBadges() {
  $("origBadge").textContent = LANG_BADGE[$("from").value] || "AUTO";
  $("transBadge").textContent = LANG_BADGE[$("to").value] || "ZH";
}

function humanSize(n) {
  if (n >= 1024 * 1024) return (n / (1024 * 1024)).toFixed(1) + " MB";
  if (n >= 1024) return (n / 1024).toFixed(0) + " KB";
  return n + " B";
}

function setFile(f) {
  if (!f) return;
  const isPdf = f.type === "application/pdf" || f.name.toLowerCase().endsWith(".pdf");
  if (!isPdf) { showError("Please choose a PDF file."); return; }
  state.file = f;
  $("fileMeta").textContent = `${f.name} · ${humanSize(f.size)}`;
  $("fileMeta").classList.remove("hidden");
  $("translateBtn").disabled = false;
}

function showError(msg) {
  $("errorText").textContent = msg;
  showStatus("statusError");
}

async function safeDetail(res) {
  try { return (await res.json()).detail; } catch { return null; }
}

// ---- engine menu + key ----
async function refreshEngineUi() {
  const engine = $("engine").value;
  const needsKey = engine === "claude" || engine === "openai";
  $("apiKeyWrap").classList.toggle("hidden", !needsKey);
  if (needsKey) {
    try {
      const s = await (await fetch("/api/settings")).json();
      $("apiKey").placeholder = s[engine] ? "Key saved — enter a new one to replace" : "Paste your API key";
    } catch {}
  }
}

async function saveKey() {
  const engine = $("engine").value;
  const key = $("apiKey").value.trim();
  if (!key) return;
  const fd = new FormData();
  fd.append("engine", engine);
  fd.append("api_key", key);
  const res = await fetch("/api/settings", { method: "POST", body: fd });
  if (res.ok) { $("apiKey").value = ""; refreshEngineUi(); }
  else showError((await safeDetail(res)) || "Could not save key.");
}

// ---- translate ----
async function startTranslate() {
  if (!state.file) return;
  $("origView").innerHTML = "";
  $("transView").innerHTML = "";
  $("translateBtn").disabled = true;
  showStatus("statusProgress");
  setProgress(0, 0);

  const fd = new FormData();
  fd.append("file", state.file);
  fd.append("source", $("from").value);
  fd.append("target", $("to").value);
  fd.append("engine", $("engine").value);

  let res;
  try { res = await fetch("/api/translate", { method: "POST", body: fd }); }
  catch { return fail("Network error during upload."); }
  if (!res.ok) return fail((await safeDetail(res)) || "Upload failed.");

  state.jobId = res.json ? (await res.json()).job_id : null;
  loadText("original", "origView");
  pollStatus();
}

function setProgress(page, count) {
  const pct = count > 0 ? Math.round((page / count) * 100) : 6;
  $("progressBar").style.width = pct + "%";
  $("progressText").textContent = count ? `Translating page ${page} of ${count}…` : "Starting…";
}

function fail(msg) {
  if (state.poll) { clearInterval(state.poll); state.poll = null; }
  $("translateBtn").disabled = false;
  showError(msg);
}

function pollStatus() {
  if (state.poll) clearInterval(state.poll);
  state.poll = setInterval(async () => {
    let res;
    try { res = await fetch(`/api/jobs/${state.jobId}`); } catch { return; }
    if (!res.ok) return;
    const s = await res.json();
    if (s.status === "running") {
      setProgress(s.page, s.page_count);
    } else if (s.status === "done") {
      clearInterval(state.poll); state.poll = null;
      await loadText("result", "transView");
      $("downloadBtn").href = `/api/jobs/${state.jobId}/result`;
      showStatus("statusDone");
      $("translateBtn").disabled = false;
      refreshHistory();
    } else if (s.status === "error") {
      fail(s.error || "Translation failed.");
    }
  }, 1000);
}

// ---- text-reader panes ----
async function loadText(which, viewId) {
  const view = $(viewId);
  view.innerHTML = "";
  let res;
  try { res = await fetch(`/api/jobs/${state.jobId}/text?which=${which}`); }
  catch { view.textContent = "Preview unavailable."; return; }
  if (!res.ok) { view.textContent = "Preview unavailable."; return; }
  const { pages } = await res.json();
  pages.forEach((text, i) => {
    if (i > 0) {
      const marker = document.createElement("div");
      marker.className = "pagemarker";
      marker.textContent = which === "result" ? `第 ${i + 1} 页` : `PAGE ${i + 1}`;
      view.appendChild(marker);
    }
    const p = document.createElement("div");
    p.className = "pagetext";
    p.textContent = text;
    view.appendChild(p);
  });
}

// ---- history (session-only) ----
async function refreshHistory() {
  let res;
  try { res = await fetch("/api/jobs"); } catch { return; }
  if (!res.ok) return;
  const jobs = await res.json();
  const list = $("historyList");
  list.innerHTML = "";
  jobs.forEach((j) => {
    const item = document.createElement("button");
    item.className = "historyitem";
    item.textContent = `${j.filename} · ${(j.source || "auto").toUpperCase()}→${(j.target || "").toUpperCase()} · ${j.status}`;
    item.addEventListener("click", () => openHistory(j.id));
    list.appendChild(item);
  });
}

async function openHistory(jobId) {
  state.jobId = jobId;
  $("historyPanel").classList.add("hidden");
  await loadText("original", "origView");
  const s = await (await fetch(`/api/jobs/${jobId}`)).json();
  if (s.status === "done") {
    await loadText("result", "transView");
    $("downloadBtn").href = `/api/jobs/${jobId}/result`;
    showStatus("statusDone");
  }
}

function swapLangs() {
  const from = $("from"), to = $("to");
  // 'auto' has no slot in To; fall back to 'en' when swapping an auto source up.
  const newTo = from.value === "auto" ? "en" : from.value;
  const newFrom = to.value;
  from.value = newFrom;
  to.value = newTo;
  setBadges();
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

  $("from").addEventListener("change", setBadges);
  $("to").addEventListener("change", setBadges);
  $("swapBtn").addEventListener("click", swapLangs);
  $("engine").addEventListener("change", refreshEngineUi);
  $("saveKeyBtn").addEventListener("click", saveKey);
  $("translateBtn").addEventListener("click", startTranslate);
  if ($("retryBtn")) $("retryBtn").addEventListener("click", startTranslate);
  $("historyBtn").addEventListener("click", () => {
    $("historyPanel").classList.toggle("hidden");
    refreshHistory();
  });

  setBadges();
  refreshEngineUi();
  showStatus("statusIdle");
}

document.addEventListener("DOMContentLoaded", wireUp);
```

> If the markup from Task 6 used different child ids for the status states, reconcile them with the ids referenced here before finishing.

- [ ] **Step 4: Run test to verify it passes, then the full suite**

Run: `python -m pytest tests/test_web_app.py::test_app_js_calls_text_and_settings_endpoints -v`
Expected: PASS
Run: `python -m pytest -q`
Expected: all tests pass.

- [ ] **Step 5: Manual verification**

```bash
. .venv/bin/activate
PYTHONPATH=src pdftranslate-web
```
In the browser: confirm the redesigned look (light canvas, blue accent, 文 wordmark, squared corners), drop a PDF, see name·size·pages, Translate with Google → progress → both text panes fill with original/translated text + page markers → Download works. Switch Engine to Claude → key field appears → save a key → translate. Open History → see the session's jobs → click one to reopen. Try swap. Stop with Ctrl-C.

- [ ] **Step 6: Commit**

```bash
git add src/pdftranslator/web/static/app.js tests/test_web_app.py
git commit -m "feat: wire redesigned UI behavior, engine menu, history, swap"
```

---

## Self-Review Notes

- **Spec coverage:** text-reader panes (Tasks 4 text endpoint + 6/7 panes); engine menu Google/Claude/OpenAI with local key (Tasks 2 settings, 3 providers, 4 settings API, 5 translate wiring, 7 menu UI); session-only history (Task 1 `list` + 4 `/api/jobs` + 7 panel); enriched status/metadata (Tasks 1, 4); friendly error + retry (Task 7 status states); redesign layout/tokens (Task 6). Download unchanged (existing `/result`). Out-of-scope items (desktop packaging, persistent history, OCR, model picker) excluded.
- **No-network tests:** LLM providers via injected fake clients; endpoints via fake provider + in-memory PDFs; settings via temp `PDFTRANSLATOR_CONFIG_DIR`.
- **Type consistency:** `build_provider(engine, *, api_key=None)`, `JobStore.create(..., *, engine, provider, filename, page_count)`, `Job` fields, and the endpoint shapes are referenced identically across tasks. The frontend DOM-contract ids in Task 6 match those used by `app.js` in Task 7.
- **Visual fidelity** is matched to `docs/design/redesign-handoff.md` and verified live by the user (Task 7 Step 5); it cannot be auto-screenshotted in this environment.
