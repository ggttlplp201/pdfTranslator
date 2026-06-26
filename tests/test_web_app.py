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
