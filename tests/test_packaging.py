"""Guard the packaging gaps that broke the hosted deploy.

The web UI assets (static/*) must be declared as package data, otherwise the
built wheel omits them and the server crashes at startup with a missing-static
directory error (works from source via PYTHONPATH, fails once installed).
"""
import tomllib
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


def test_static_assets_declared_as_package_data():
    pyproject = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    package_data = pyproject["tool"]["setuptools"]["package-data"]
    patterns = package_data.get("pdftranslator.web", [])
    assert any("static" in p for p in patterns), package_data


def test_static_files_present_next_to_package():
    import pdftranslator.web as web

    static = Path(web.__file__).parent / "static"
    for name in ("index.html", "app.js", "styles.css"):
        assert (static / name).exists(), name
