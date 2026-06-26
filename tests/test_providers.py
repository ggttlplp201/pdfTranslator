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


class StatusResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")

    def json(self):
        return self._payload


class SequenceSession:
    """Returns a queued response per call (cycling on the last one)."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        idx = min(len(self.calls) - 1, len(self._responses) - 1)
        return self._responses[idx]


def test_google_retries_on_5xx_then_succeeds():
    ok = StatusResponse(200, [[["Olá", "Hi", None, None, 0]], None, "en"])
    session = SequenceSession([StatusResponse(500), StatusResponse(500), ok])
    provider = providers.GoogleProvider(session=session, sleep=lambda *_: None)

    out = provider.translate(["Hi"], source="en", target="pt")

    assert out == ["Olá"]
    assert len(session.calls) == 3  # two failures then success


def test_google_raises_after_persistent_5xx():
    import requests as r
    session = SequenceSession([StatusResponse(500)])
    provider = providers.GoogleProvider(session=session, max_retries=3, sleep=lambda *_: None)

    with pytest.raises(r.RequestException):
        provider.translate(["Hi"], source="en", target="pt")
    assert len(session.calls) == 3
