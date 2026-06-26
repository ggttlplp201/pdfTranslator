import time
from typing import Protocol

import requests

from . import lang

_GOOGLE_URL = "https://translate.googleapis.com/translate_a/single"


class TranslationProvider(Protocol):
    def translate(self, texts: list[str], source: str, target: str) -> list[str]:
        ...


class GoogleProvider:
    def __init__(self, session=None, max_retries: int = 3, backoff: float = 0.5, sleep=time.sleep):
        self._session = session or requests.Session()
        self._cache: dict[tuple[str, str, str], str] = {}
        self._max_retries = max_retries
        self._backoff = backoff
        self._sleep = sleep

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
        # The unofficial endpoint is flaky (transient 5xx / 429 / network drops),
        # so retry a few times with exponential backoff before giving up.
        last_exc: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                resp = self._session.get(_GOOGLE_URL, params=params, timeout=15)
                status = getattr(resp, "status_code", 200)
                if status >= 500 or status == 429:
                    last_exc = requests.HTTPError(f"Google returned {status}")
                else:
                    resp.raise_for_status()
                    data = resp.json()
                    segments = data[0] or []
                    translated = "".join(seg[0] for seg in segments if seg and seg[0])
                    self._cache[key] = translated
                    return translated
            except requests.RequestException as exc:
                last_exc = exc
            if attempt < self._max_retries - 1:
                self._sleep(self._backoff * (2 ** attempt))
        raise last_exc if last_exc else requests.RequestException("translation failed")


def build_provider(name: str) -> TranslationProvider:
    if name == "google":
        return GoogleProvider()
    raise ValueError(f"unknown provider: {name}")
