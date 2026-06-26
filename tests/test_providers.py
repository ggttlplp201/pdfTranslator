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
    # Index-keyed JSON object: keys are line numbers, values the translations.
    client = FakeAnthropicClient(['{"0": "你好", "1": "世界"}'])
    provider = providers.AnthropicProvider(api_key="x", client=client)
    assert provider.translate(["Hello", "World"], "en", "zh") == ["你好", "世界"]
    assert len(client.calls) == 1  # one batched call, no per-line fan-out


def test_anthropic_retries_only_missing_indices():
    # First call drops index 1; the retry supplies just the missing one — never
    # one call per line.
    client = FakeAnthropicClient(['{"0": "A"}', '{"1": "B"}'])
    provider = providers.AnthropicProvider(api_key="x", client=client)
    out = provider.translate(["Hello", "World"], "en", "zh")
    assert out == ["A", "B"]
    assert len(client.calls) == 2  # initial + one retry for the missing index


def test_anthropic_falls_back_to_original_when_unresolved():
    # Model returns nothing usable on both attempts → keep originals, no loop.
    client = FakeAnthropicClient(['{}'])
    provider = providers.AnthropicProvider(api_key="x", client=client)
    out = provider.translate(["Hello", "World"], "en", "zh")
    assert out == ["Hello", "World"]
    assert len(client.calls) == 2  # bounded: initial + one retry


def test_anthropic_strips_code_fences():
    client = FakeAnthropicClient(['```json\n{"0": "你好"}\n```'])
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
