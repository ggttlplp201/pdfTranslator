import json
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
    # Each line is anchored to an explicit index (a JSON object keyed by line
    # number), not a bare array. A bare array let the model silently merge/split
    # lines so the count drifted, which forced a slow one-call-per-line fallback
    # (~40 calls per page). Index keys keep one call per batch and let us re-ask
    # only for any indices that came back missing.
    SYSTEM = (
        "You are a professional translator. You receive a JSON object whose keys are "
        "line numbers and whose values are CONSECUTIVE lines of a single document in "
        "{source} — a sentence is often split across several lines. Read all the lines "
        "together for context, then translate the document into {target}. Return ONLY a "
        "JSON object with the EXACT same keys; each value is the translation of that "
        "line, divided so it still reads naturally line by line. Translate EVERY line — "
        "including headings, table cells and fragments — and never leave the original "
        "{source} text except for numbers, symbols, or code. No commentary, no code fences."
    )

    def __init__(self, batch_size: int = 100):
        self._batch_size = batch_size

    def translate(self, texts: list[str], source: str, target: str) -> list[str]:
        chunks = [texts[i : i + self._batch_size] for i in range(0, len(texts), self._batch_size)]
        if len(chunks) <= 1:
            return self._batch(chunks[0], source, target) if chunks else []
        # Translate batches concurrently so a multi-batch page isn't serial.
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=min(4, len(chunks))) as pool:
            results = list(pool.map(lambda c: self._batch(c, source, target), chunks))
        out: list[str] = []
        for r in results:
            out.extend(r)
        return out

    def _batch(self, lines: list[str], source: str, target: str) -> list[str]:
        if not lines:
            return []
        result: list[str | None] = [None] * len(lines)
        # Indices that still need a translation (skip whitespace-only lines).
        pending = [i for i, line in enumerate(lines) if line.strip()]
        for i, line in enumerate(lines):
            if not line.strip():
                result[i] = line
        # One batched call, then at most one retry for any indices the model
        # dropped (or a transient empty/garbage response) — never a call per line.
        for _ in range(2):
            if not pending:
                break
            mapping = {str(i): lines[i] for i in pending}
            got = self._translate_map(mapping, source, target) or {}
            still: list[int] = []
            for i in pending:
                value = got.get(str(i))
                if value is None:
                    still.append(i)
                else:
                    result[i] = str(value)
            pending = still
        # Anything still missing: fall back to the original text for that line.
        for i in pending:
            result[i] = lines[i]
        return [r if r is not None else lines[idx] for idx, r in enumerate(result)]

    def _translate_map(self, mapping: dict, source: str, target: str):
        system = self.SYSTEM.format(source=_lang_name(source), target=_lang_name(target))
        raw = self._complete(system, json.dumps(mapping, ensure_ascii=False))
        try:
            data = json.loads(_strip_fences(raw))
        except (ValueError, TypeError):
            return None
        return data if isinstance(data, dict) else None

    def _complete(self, system: str, user: str) -> str:
        raise NotImplementedError


class AnthropicProvider(_LLMProvider):
    def __init__(self, api_key: str, model: str = "claude-haiku-4-5", client=None, batch_size: int = 100):
        super().__init__(batch_size)
        self._model = model
        if client is not None:
            self._client = client
        else:
            import anthropic
            # Bound the call so a network/API stall surfaces as a job error rather
            # than leaving the translation stuck indefinitely.
            self._client = anthropic.Anthropic(api_key=api_key, timeout=60.0, max_retries=2)

    def _complete(self, system: str, user: str) -> str:
        msg = self._client.messages.create(
            model=self._model, max_tokens=16000, system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(
            getattr(b, "text", "") for b in msg.content if getattr(b, "type", None) == "text"
        )


class OpenAIProvider(_LLMProvider):
    def __init__(self, api_key: str, model: str = "gpt-4o-mini", client=None, batch_size: int = 100):
        super().__init__(batch_size)
        self._model = model
        if client is not None:
            self._client = client
        else:
            import openai
            self._client = openai.OpenAI(api_key=api_key, timeout=60.0, max_retries=2)

    def _complete(self, system: str, user: str) -> str:
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return resp.choices[0].message.content or ""


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
