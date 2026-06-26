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
    monkeypatch.setattr(providers, "build_provider", lambda name: Fake())


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

    monkeypatch.setattr(providers, "build_provider", lambda name: BlockingFake())

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

    monkeypatch.setattr(providers, "build_provider", lambda name: Blocking())
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
