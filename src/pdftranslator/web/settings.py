import json
import os
from pathlib import Path

_ENGINE_KEY = {"claude": "claude_api_key", "openai": "openai_api_key"}


def _config_dir() -> Path:
    override = os.environ.get("PDFTRANSLATOR_CONFIG_DIR")
    base = Path(override) if override else Path.home() / ".config" / "pdftranslator"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _config_file() -> Path:
    return _config_dir() / "config.json"


def _load() -> dict:
    f = _config_file()
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return {}
    return {}


def _save(data: dict) -> None:
    f = _config_file()
    f.write_text(json.dumps(data), encoding="utf-8")
    try:
        os.chmod(f, 0o600)
    except OSError:
        pass


def get_key(engine: str) -> str | None:
    field = _ENGINE_KEY.get(engine)
    if field is None:
        return None
    return _load().get(field)


def set_key(engine: str, key: str) -> None:
    field = _ENGINE_KEY.get(engine)
    if field is None:
        raise ValueError(f"no key storage for engine: {engine}")
    data = _load()
    data[field] = key
    _save(data)


def has_key(engine: str) -> bool:
    return bool(get_key(engine))
