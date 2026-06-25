_TO_GOOGLE = {"en": "en", "pt": "pt", "zh": "zh-CN", "auto": "auto"}
_TARGETS = {"en", "pt", "zh"}
_SOURCES = {"en", "pt", "zh", "auto"}


def to_google(code: str) -> str:
    if code not in _TO_GOOGLE:
        raise ValueError(f"unsupported language code: {code}")
    return _TO_GOOGLE[code]


def validate_target(code: str) -> None:
    if code not in _TARGETS:
        raise ValueError(f"unsupported target language: {code} (use en, pt, zh)")


def validate_source(code: str) -> None:
    if code not in _SOURCES:
        raise ValueError(f"unsupported source language: {code} (use en, pt, zh, auto)")
