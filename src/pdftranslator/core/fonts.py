"""Resolve a real, embeddable font per target language.

We bundle Noto fonts and embed them in the output (subset on save) instead of
relying on PyMuPDF's built-in aliases ("china-s"/"helv"). Those aliases are not
portably embedded — other viewers (Poppler) report "Unknown font tag 'china-s'"
and may drop glyphs (e.g. ®). Bundled Noto fonts render consistently everywhere
and cover ® / © / ™.
"""
import sys
from pathlib import Path

# (registration name, file name) per language.
_FONTS = {
    "zh": ("NotoSansSC", "NotoSansSC-Regular.ttf"),
    "en": ("NotoSans", "NotoSans-Regular.ttf"),
    "pt": ("NotoSans", "NotoSans-Regular.ttf"),
}


def _fonts_dir() -> Path:
    """Locate bundled fonts whether running from source or a frozen build."""
    base = getattr(sys, "_MEIPASS", None)
    if base is not None:
        return Path(base) / "pdftranslator" / "assets" / "fonts"
    return Path(__file__).parent.parent / "assets" / "fonts"


def font_for_language(target: str) -> tuple[str, str]:
    """Return (fontname, fontfile_path) for the target language."""
    name, fname = _FONTS.get(target, _FONTS["en"])
    return name, str(_fonts_dir() / fname)
