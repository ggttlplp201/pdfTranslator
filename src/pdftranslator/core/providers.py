from typing import Protocol

import requests

from . import lang

_GOOGLE_URL = "https://translate.googleapis.com/translate_a/single"


class TranslationProvider(Protocol):
    def translate(self, texts: list[str], source: str, target: str) -> list[str]:
        ...


class GoogleProvider:
    def __init__(self, session=None):
        self._session = session or requests.Session()
        self._cache: dict[tuple[str, str, str], str] = {}

    def translate(self, texts: list[str], source: str, target: str) -> list[str]:
        sl = lang.to_google(source)
        tl = lang.to_google(target)
        return [self._one(t, sl, tl) for t in texts]

    def _one(self, text: str, sl: str, tl: str) -> str:
        if not text.strip():
            return text
        key = (text, sl, tl)
        if key in self._cache:
            return self._cache[key]
        params = {"client": "gtx", "sl": sl, "tl": tl, "dt": "t", "q": text}
        resp = self._session.get(_GOOGLE_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        segments = data[0] or []
        translated = "".join(seg[0] for seg in segments if seg and seg[0])
        self._cache[key] = translated
        return translated


def build_provider(name: str) -> TranslationProvider:
    if name == "google":
        return GoogleProvider()
    raise ValueError(f"unknown provider: {name}")
