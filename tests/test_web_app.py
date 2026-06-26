import threading
import time

import fitz
import requests
import pytest
from fastapi.testclient import TestClient
from pdftranslator.web.app import create_app
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
    monkeypatch.setattr(providers, "build_provider", lambda *a, **k: Fake())


def test_index_served():
    client = TestClient(create_app())
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


def test_static_mounted():
    client = TestClient(create_app())
    resp = client.get("/static/styles.css")
    assert resp.status_code == 200


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


def test_result_404_while_running(monkeypatch):
    """GET /result returns 404 while the job is still running, then 200 once done."""
    gate = threading.Event()

    class BlockingFake:
        def translate(self, texts, source, target):
            gate.wait()
            return [t.upper() for t in texts]

    monkeypatch.setattr(providers, "build_provider", lambda *a, **k: BlockingFake())

    client = TestClient(create_app())
    try:
        resp = client.post(
            "/api/translate",
            files={"file": ("in.pdf", _pdf_bytes("hello"), "application/pdf")},
            data={"source": "auto", "target": "en"},
        )
        assert resp.status_code == 200
        job_id = resp.json()["job_id"]

        # While translation is blocked the result must be 404
        assert client.get(f"/api/jobs/{job_id}/result").status_code == 404
    finally:
        gate.set()  # unblock the worker

    status = _wait(client, job_id)
    assert status["status"] == "done"
    assert client.get(f"/api/jobs/{job_id}/result").status_code == 200


def test_bad_source_is_400(fake_google):
    client = TestClient(create_app())
    resp = client.post(
        "/api/translate",
        files={"file": ("in.pdf", _pdf_bytes(), "application/pdf")},
        data={"source": "fr", "target": "en"},
    )
    assert resp.status_code == 400


def test_empty_file_is_400(fake_google):
    client = TestClient(create_app())
    resp = client.post(
        "/api/translate",
        files={"file": ("in.pdf", b"", "application/pdf")},
        data={"source": "auto", "target": "en"},
    )
    assert resp.status_code == 400


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
    monkeypatch.setattr(providers, "build_provider", lambda *a, **k: Boom())

    client = TestClient(create_app())
    job_id = client.post(
        "/api/translate",
        files={"file": ("in.pdf", _pdf_bytes(), "application/pdf")},
        data={"source": "auto", "target": "en"},
    ).json()["job_id"]
    status = _wait(client, job_id)
    assert status["status"] == "error"
    assert "rate limited" in status["error"]


def test_index_has_ui_elements():
    client = TestClient(create_app())
    html = client.get("/").text
    assert 'id="dropzone"' in html
    assert 'id="translateBtn"' in html
    assert 'id="origView"' in html
    assert 'id="transView"' in html
    assert "/static/app.js" in html


def test_app_js_served_with_logic():
    client = TestClient(create_app())
    js = client.get("/static/app.js").text
    assert "/api/translate" in js


def test_previews_served_inline_not_attachment(fake_google):
    # Both PDFs must render in the iframe preview, so they must NOT be sent as
    # attachments (which makes the browser download instead of display them).
    client = TestClient(create_app())
    job_id = client.post(
        "/api/translate",
        files={"file": ("in.pdf", _pdf_bytes("hello"), "application/pdf")},
        data={"source": "auto", "target": "en"},
    ).json()["job_id"]
    _wait(client, job_id)
    for path in (f"/api/jobs/{job_id}/original", f"/api/jobs/{job_id}/result"):
        resp = client.get(path)
        assert resp.status_code == 200
        disposition = resp.headers.get("content-disposition", "")
        assert disposition.startswith("inline"), (path, disposition)
        assert "attachment" not in disposition


def test_pages_and_page_render_as_png(fake_google):
    client = TestClient(create_app())
    job_id = client.post(
        "/api/translate",
        files={"file": ("in.pdf", _pdf_bytes("hello"), "application/pdf")},
        data={"source": "auto", "target": "en"},
    ).json()["job_id"]
    _wait(client, job_id)

    for which in ("original", "result"):
        pages = client.get(f"/api/jobs/{job_id}/pages?which={which}")
        assert pages.status_code == 200
        assert pages.json()["pages"] == 1

        img = client.get(f"/api/jobs/{job_id}/page/{which}/0")
        assert img.status_code == 200
        assert img.headers["content-type"] == "image/png"
        assert img.content[:8] == b"\x89PNG\r\n\x1a\n"  # PNG signature

    # out-of-range page → 404
    assert client.get(f"/api/jobs/{job_id}/page/result/9").status_code == 404


def test_pages_invalid_which_is_400(fake_google):
    client = TestClient(create_app())
    job_id = client.post(
        "/api/translate",
        files={"file": ("in.pdf", _pdf_bytes("hello"), "application/pdf")},
        data={"source": "auto", "target": "en"},
    ).json()["job_id"]
    _wait(client, job_id)
    assert client.get(f"/api/jobs/{job_id}/pages?which=bogus").status_code == 400


def test_result_pages_404_while_running(monkeypatch):
    import threading
    gate = threading.Event()

    class Blocking:
        def translate(self, texts, source, target):
            gate.wait(timeout=5)
            return [t.upper() for t in texts]

    monkeypatch.setattr(providers, "build_provider", lambda *a, **k: Blocking())
    client = TestClient(create_app())
    try:
        job_id = client.post(
            "/api/translate",
            files={"file": ("in.pdf", _pdf_bytes("hello"), "application/pdf")},
            data={"source": "auto", "target": "en"},
        ).json()["job_id"]
        # result not ready yet → pages 404
        assert client.get(f"/api/jobs/{job_id}/pages?which=result").status_code == 404
        # original is available immediately
        assert client.get(f"/api/jobs/{job_id}/pages?which=original").json()["pages"] == 1
    finally:
        gate.set()


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
        files={"file": ("doc.pdf", _pdf_bytes("greetings"), "application/pdf")},
        data={"source": "auto", "target": "en"},
    ).json()["job_id"]
    _wait(client, job_id)

    listing = client.get("/api/jobs").json()
    entry = next(j for j in listing if j["id"] == job_id)
    assert entry["filename"] == "doc.pdf"
    assert entry["engine"] == "google"  # history shows which engine was used

    status = client.get(f"/api/jobs/{job_id}").json()
    assert status["filename"] == "doc.pdf"
    assert status["page_count"] >= 1
    assert status["target"] == "en"

    orig = client.get(f"/api/jobs/{job_id}/text?which=original").json()
    assert "greetings" in " ".join(orig["pages"]).lower()
    trans = client.get(f"/api/jobs/{job_id}/text?which=result").json()
    assert "GREETINGS" in " ".join(trans["pages"])  # fake provider uppercases


def test_text_invalid_which_400(fake_google):
    client = TestClient(create_app())
    job_id = client.post(
        "/api/translate",
        files={"file": ("doc.pdf", _pdf_bytes(), "application/pdf")},
        data={"source": "auto", "target": "en"},
    ).json()["job_id"]
    _wait(client, job_id)
    assert client.get(f"/api/jobs/{job_id}/text?which=nope").status_code == 400


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


def test_app_js_renders_page_images():
    client = TestClient(create_app())
    js = client.get("/static/app.js").text
    assert "/api/translate" in js
    # panes render the actual rendered PDF pages as images, not text
    assert "/pages?which=" in js and "/page/" in js
    assert "engine" in js  # sends the engine field


def test_page_image_style_present():
    client = TestClient(create_app())
    css = client.get("/static/styles.css").text
    js = client.get("/static/app.js").text
    # the image class used by the JS must be styled in the CSS
    assert ".pdfpage" in css
    assert "pdfpage" in js


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


def test_byok_key_handling_is_browser_local():
    client = TestClient(create_app())
    html = client.get("/").text
    js = client.get("/static/app.js").text
    assert 'id="keyStatus"' in html
    # Keys live in the browser (localStorage), never POSTed to the server, and
    # are attached to the translate request instead.
    assert "localStorage" in js
    assert "/api/settings" not in js
    assert 'fd.append("api_key"' in js
    # The privacy note reassures the user the key is not stored server-side.
    assert "never stored on our server" in html


def test_translate_accepts_per_request_key(monkeypatch):
    """A key sent with the request is used to build the provider (BYOK)."""
    seen = {}

    class Fake:
        def translate(self, texts, source, target):
            return [t.upper() for t in texts]

    def fake_build(engine, *, api_key=None):
        seen["engine"] = engine
        seen["api_key"] = api_key
        return Fake()

    monkeypatch.setattr(providers, "build_provider", fake_build)
    client = TestClient(create_app())
    resp = client.post(
        "/api/translate",
        files={"file": ("in.pdf", _pdf_bytes("hello"), "application/pdf")},
        data={"source": "auto", "target": "en", "engine": "claude", "api_key": "sk-byok"},
    )
    assert resp.status_code == 200
    assert seen == {"engine": "claude", "api_key": "sk-byok"}


def test_byok_only_blocks_server_key_storage(monkeypatch):
    monkeypatch.setenv("PDFTRANSLATOR_BYOK_ONLY", "1")
    client = TestClient(create_app())
    # Saving a key on the server is refused in public/hosted mode.
    r = client.post("/api/settings", data={"engine": "claude", "api_key": "sk-x"})
    assert r.status_code == 403
    # And an LLM translate with no per-request key is rejected (no server fallback).
    r2 = client.post(
        "/api/translate",
        files={"file": ("d.pdf", _pdf_bytes(), "application/pdf")},
        data={"source": "auto", "target": "en", "engine": "claude"},
    )
    assert r2.status_code == 400


def test_ui_language_toggle_present():
    client = TestClient(create_app())
    html = client.get("/").text
    js = client.get("/static/app.js").text
    # A language toggle control exists and the JS ships an English+Chinese table.
    assert 'id="langToggle"' in html
    assert "data-i18n=" in html
    assert "翻译" in js  # Simplified Chinese strings are bundled
    assert "applyLang" in js


def test_history_has_close_control():
    client = TestClient(create_app())
    html = client.get("/").text
    js = client.get("/static/app.js").text
    assert 'id="historyClose"' in html
    # close handler + Escape both hide the panel
    assert "historyClose" in js
    assert "Escape" in js


def test_translate_warns_without_file():
    client = TestClient(create_app())
    js = client.get("/static/app.js").text
    # clicking Translate with no file selected shows a warning instead of silently doing nothing
    assert "Please choose a PDF first" in js


def test_history_list_is_private_per_user(fake_google):
    """The history *list* must not reveal another user's jobs (no enumeration).

    Direct access by the unguessable job id is intentionally allowed (capability
    model) so downloads work without depending on the session cookie.
    """
    app = create_app()
    a = TestClient(app)   # user A (own cookie jar / session)
    b = TestClient(app)   # user B (different session)

    job_id = a.post(
        "/api/translate",
        files={"file": ("a.pdf", _pdf_bytes("secret"), "application/pdf")},
        data={"source": "auto", "target": "en"},
    ).json()["job_id"]
    _wait(a, job_id)

    # A sees its own job in history; B's history is empty (cannot enumerate A's).
    assert any(j["id"] == job_id for j in a.get("/api/jobs").json())
    assert b.get("/api/jobs").json() == []


def test_download_works_without_session_cookie(fake_google):
    """A download must succeed even if the request carries no session cookie
    (regression: the per-user owner check returned 'unknown job' on download)."""
    app = create_app()
    a = TestClient(app)
    job_id = a.post(
        "/api/translate",
        files={"file": ("a.pdf", _pdf_bytes("hi"), "application/pdf")},
        data={"source": "auto", "target": "en"},
    ).json()["job_id"]
    _wait(a, job_id)

    # A cookieless client (fresh jar) can still fetch and download by id.
    nocookie = TestClient(app)
    nocookie.cookies.clear()
    r = nocookie.get(f"/api/jobs/{job_id}/result?download=1")
    assert r.status_code == 200
    assert r.content[:5].startswith(b"%PDF")
    assert "attachment" in r.headers.get("content-disposition", "")


def test_session_cookie_issued():
    client = TestClient(create_app())
    resp = client.get("/")
    assert resp.status_code == 200
    assert "pdftx_sid" in resp.headers.get("set-cookie", "")
