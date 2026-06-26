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
