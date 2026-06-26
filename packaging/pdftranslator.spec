# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — builds a single-file pdfTranslator desktop app.

Cross-platform: run `pyinstaller packaging/pdftranslator.spec` from the repo
root on macOS (produces dist/pdfTranslator[.app]) or Windows (dist/pdfTranslator.exe).
PyInstaller cannot cross-compile, so each OS binary is built on that OS.
"""
import os
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Paths in a .spec resolve relative to the spec file, so anchor to the repo root.
ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
SRC = os.path.join(ROOT, "src")

# Bundle the web UI assets at the same relative path the app expects.
datas = [(os.path.join(SRC, "pdftranslator", "web", "static"), "pdftranslator/web/static")]
datas += [(os.path.join(SRC, "pdftranslator", "assets", "fonts"), "pdftranslator/assets/fonts")]
datas += collect_data_files("fitz")  # PyMuPDF runtime resources

# uvicorn loads its protocol/loop implementations dynamically; the LLM SDKs are
# imported lazily only when their engine is selected — PyInstaller's static
# analysis misses these, so name them explicitly. (openai's submodules include
# an optional voice helper that needs numpy, so we don't sweep them wholesale —
# the import graph from `import openai` already pulls in the client we use.)
hiddenimports = collect_submodules("uvicorn") + ["anthropic", "openai"]

a = Analysis(
    [os.path.join(SPECPATH, "desktop_entry.py")],
    pathex=[SRC],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "matplotlib"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="pdfTranslator",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # a small window that shows "running" and quits the app when closed
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

# On macOS, also wrap the binary in a double-clickable .app bundle.
if sys.platform == "darwin":
    app = BUNDLE(
        exe,
        name="pdfTranslator.app",
        icon=None,
        bundle_identifier="com.leon.pdftranslator",
    )
