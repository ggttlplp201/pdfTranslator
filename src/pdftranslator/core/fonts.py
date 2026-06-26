"""Resolve a real, embeddable font per target language.

We bundle Noto fonts and embed them in the output (subset on save) instead of
relying on PyMuPDF's built-in aliases ("china-s"/"helv"). Those aliases are not
portably embedded — other viewers (Poppler) report "Unknown font tag 'china-s'"
and may drop glyphs (e.g. ®). Bundled Noto fonts render consistently everywhere
and cover ® / © / ™.
"""
import sys
from pathlib import Path

# Font family per language.
_FAMILY = {"zh": "NotoSansSC", "en": "NotoSans", "pt": "NotoSans"}


def _fonts_dir() -> Path:
    """Locate bundled fonts whether running from source or a frozen build."""
    base = getattr(sys, "_MEIPASS", None)
    if base is not None:
        return Path(base) / "pdftranslator" / "assets" / "fonts"
    return Path(__file__).parent.parent / "assets" / "fonts"


def _suffix(family: str, bold: bool, italic: bool) -> str:
    if family == "NotoSansSC":
        # The CJK family ships Regular + Bold only (CJK has no italic form).
        return "-Bold" if bold else "-Regular"
    if bold and italic:
        return "-BoldItalic"
    if bold:
        return "-Bold"
    if italic:
        return "-Italic"
    return "-Regular"


def font_variant(target: str, bold: bool = False, italic: bool = False) -> tuple[str, str]:
    """Return (registration_name, fontfile_path) for a language + style."""
    family = _FAMILY.get(target, "NotoSans")
    suffix = _suffix(family, bold, italic)
    name = (family + suffix).replace("-", "")   # e.g. NotoSansSCBold
    fname = f"{family}{suffix}.ttf"
    return name, str(_fonts_dir() / fname)


def font_for_language(target: str) -> tuple[str, str]:
    """Return the Regular (name, fontfile) for the target language."""
    return font_variant(target, bold=False, italic=False)
