import importlib


def test_set_get_has_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("PDFTRANSLATOR_CONFIG_DIR", str(tmp_path))
    settings = importlib.import_module("pdftranslator.web.settings")

    assert settings.has_key("claude") is False
    assert settings.get_key("claude") is None

    settings.set_key("claude", "sk-ant-123")
    assert settings.get_key("claude") == "sk-ant-123"
    assert settings.has_key("claude") is True
    # openai still unset and independent
    assert settings.has_key("openai") is False


def test_unknown_engine_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("PDFTRANSLATOR_CONFIG_DIR", str(tmp_path))
    settings = importlib.import_module("pdftranslator.web.settings")
    import pytest
    with pytest.raises(ValueError):
        settings.set_key("google", "x")
    assert settings.get_key("google") is None
