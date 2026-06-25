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
