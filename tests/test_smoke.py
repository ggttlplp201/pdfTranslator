import importlib


def test_package_imports():
    mod = importlib.import_module("pdftranslator")
    assert mod is not None
