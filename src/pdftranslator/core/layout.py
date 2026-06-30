import re

import fitz

from . import fonts
from .models import TextUnit

_MIN_SIZE = 4.0

# Letters/ideographs worth translating: Latin (incl. accented for Portuguese)
# and CJK. A block with none of these — only digits, punctuation, math symbols —
# is left completely untouched so numbers keep their exact font, size and place.
_TRANSLATABLE = re.compile(r"[A-Za-zÀ-ɏ一-鿿㐀-䶿]")


def _has_translatable(text: str) -> bool:
    return bool(_TRANSLATABLE.search(text))


_ALNUM = re.compile(r"[A-Za-z0-9]+")


def is_noop_translation(source: str, translation: str) -> bool:
    """True when translating barely changed the text — the result keeps almost all
    of the source's letters/numbers (a list of product codes, model numbers, or
    brand names that can't be meaningfully translated).

    Such blocks are left as the original so their exact format and special glyphs
    (®, ©, ™ — which the built-in CJK font can't even render) are preserved.
    """
    src = [t.lower() for t in _ALNUM.findall(source)]
    if len(src) < 2:
        return False  # too little to judge; translate normally
    kept = set(t.lower() for t in _ALNUM.findall(translation))
    preserved = sum(1 for t in src if t in kept)
    return preserved / len(src) >= 0.8


def _block_text(block) -> str:
    """Combine a block's lines into one paragraph, de-hyphenating soft line breaks.

    PDFs wrap text mid-word with a hyphen (e.g. "spin-" / "dles"). Joining the
    lines into one paragraph — and dropping those soft hyphens — lets the
    translator see whole sentences (far better context) instead of fragments.
    """
    out = ""
    for line in block.get("lines", []):
        line_text = "".join(s.get("text", "") for s in line.get("spans", []))
        if not line_text:
            continue
        if not out:
            out = line_text
        elif re.search(r"[A-Za-z]-$", out) and line_text[:1].islower():
            # Soft hyphen word-break: drop the hyphen and join directly.
            out = out[:-1] + line_text
        else:
            out = out.rstrip() + " " + line_text.lstrip()
    return out


def extract_units(page) -> list[TextUnit]:
    """One TextUnit per text block (paragraph), text de-hyphenated and joined.

    Block-level (not line-level) so translation has full-sentence context and a
    paragraph can be reflowed at a single, consistent font size.
    """
    units: list[TextUnit] = []
    data = page.get_text("dict")
    for block in data.get("blocks", []):
        if block.get("type") != 0:  # 0 == text block
            continue
        text = _block_text(block)
        if not text.strip():
            continue
        # Leave purely numeric/symbolic blocks (page numbers, figure numbers,
        # measurements like "40", data values) exactly as they are: not a unit,
        # so they're never redacted, translated, or re-rendered.
        if not _has_translatable(text):
            continue
        spans = [s for line in block.get("lines", []) for s in line.get("spans", [])]
        size = max((s.get("size", 10.0) for s in spans), default=10.0)
        color = spans[0].get("color", 0) if spans else 0
        bold, italic = _dominant_style(spans)
        units.append(TextUnit(
            text=text, bbox=tuple(block["bbox"]), size=size, color=color,
            bold=bold, italic=italic,
        ))
    return units


# PyMuPDF span "flags" bits: 2 = italic, 16 = bold.
_FLAG_ITALIC = 2
_FLAG_BOLD = 16
_BOLD_NAMES = ("bold", "black", "heavy", "semibold", "demibold")
_ITALIC_NAMES = ("italic", "oblique")


def _span_is(span, flag: int, names: tuple) -> bool:
    if span.get("flags", 0) & flag:
        return True
    font = span.get("font", "").lower()
    return any(n in font for n in names)


def _dominant_style(spans) -> tuple[bool, bool]:
    """A block is bold/italic if most of its (non-space) characters are.

    Block-level because we translate whole paragraphs and can't map translated
    words back to individual spans — so we apply one consistent style per block.
    """
    total = bold = italic = 0
    for s in spans:
        n = len(s.get("text", "").strip())
        if not n:
            continue
        total += n
        if _span_is(s, _FLAG_BOLD, _BOLD_NAMES):
            bold += n
        if _span_is(s, _FLAG_ITALIC, _ITALIC_NAMES):
            italic += n
    if not total:
        return False, False
    return bold / total >= 0.6, italic / total >= 0.6


def _redact_rects(page, rects: list) -> None:
    if not rects:
        return
    # Capture existing links before redaction: apply_redactions deletes any link
    # annotation whose rectangle overlaps a redacted area.
    links_before = page.get_links()
    for r in rects:
        page.add_redact_annot(fitz.Rect(r))
    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)
    # Restore links that were deleted. Links that did NOT overlap survive on
    # their own, so we compare by xref to avoid creating duplicates.
    if links_before:
        after_xrefs = {lnk["xref"] for lnk in page.get_links()}
        for lnk in links_before:
            if lnk["xref"] not in after_xrefs:
                restore = {k: v for k, v in lnk.items() if k not in ("xref", "id")}
                page.insert_link(restore)


def redact_units(page, units: list[TextUnit]) -> None:
    _redact_rects(page, [u.bbox for u in units])


def redact_blocks(page) -> None:
    """Redact every original text block on the page (keeping images and links).

    Used by the OCR path to clear a broken/mojibake text layer before laying the
    OCR-recovered translation over the untouched background.
    """
    rects = [b["bbox"] for b in page.get_text("dict").get("blocks", []) if b.get("type") == 0]
    _redact_rects(page, rects)


# Absolute floor used only to AVOID TRUNCATION: if a translation can't fit a box
# even at _MIN_SIZE, shrink further (down to this) so text is never cut off.
_TRUNC_FLOOR = 2.5


def _largest_fit(width: float, height: float, text: str, fontname: str, max_size: float,
                 fontfile: str | None = None, min_size: float = _MIN_SIZE) -> tuple[float, bool]:
    """Return (size, fitted): the largest size in [min_size, max_size] at which
    `text` fits a width x height box, and whether it actually fit at that size.

    Measured with the real renderer (insert_textbox on a scratch page), which
    handles wrapping and mixed CJK/Latin widths correctly. The font is registered
    once on a single reused scratch page (the per-size leftover value is
    independent of prior drawing), so the bundled font is parsed only once.
    """
    box_w = max(width, 1.0)
    box_h = max(height, 1.0) + 2.0
    rect = fitz.Rect(0, 0, box_w, box_h)
    scratch = fitz.open()
    try:
        sp = scratch.new_page(width=box_w + 4, height=box_h + 10)
        if fontfile:
            sp.insert_font(fontname=fontname, fontfile=fontfile)
        size = max_size
        while size >= min_size:
            leftover = sp.insert_textbox(rect, text, fontsize=size, fontname=fontname)
            if leftover >= 0:  # whole text fit at this size
                return size, True
            size -= 0.5
        return min_size, False
    finally:
        scratch.close()


def _fit_textbox(width: float, height: float, text: str, fontname: str, max_size: float,
                 fontfile: str | None = None) -> float:
    """Largest size <= max_size (floor 4.0) at which `text` fits a width x height box."""
    return _largest_fit(width, height, text, fontname, max_size, fontfile)[0]


# Below this the text is too small to read; if a block fits only this small we
# try to grow it into surrounding whitespace before settling.
_READABLE = 7.0
_EXPAND_PAD = 2.0   # keep a small gap from neighbours when growing
_MAX_GROW_X = 3.0   # never grow wider than this multiple of the original
_MAX_GROW_Y = 4.0   # nor taller


def _grow_bounds(u: TextUnit, units: list[TextUnit], page_rect) -> tuple:
    """Expand a cramped block into adjacent empty space — rightward first, then
    downward — stopping at the nearest neighbouring block on each side (so
    columns and table cells are never invaded), at the page margin, and at a sane
    multiple of the original size. Full-width blocks barely move (the page edge or
    a neighbour bounds them); short labels gain the room to render readably.
    """
    x0, y0, x1, y1 = u.bbox
    w, h = x1 - x0, y1 - y0
    right_limit = min(page_rect.x1 - 4.0, x0 + w * _MAX_GROW_X)
    bottom_limit = min(page_rect.y1 - 4.0, y0 + h * _MAX_GROW_Y)
    for o in units:
        if o is u:
            continue
        ox0, oy0, ox1, oy1 = o.bbox
        # A block to the right sharing vertical extent caps rightward growth.
        if ox0 >= x1 - 1 and oy0 < y1 - 1 and oy1 > y0 + 1:
            right_limit = min(right_limit, ox0 - _EXPAND_PAD)
        # A block below sharing horizontal extent caps downward growth.
        if oy0 >= y1 - 1 and ox0 < x1 - 1 and ox1 > x0 + 1:
            bottom_limit = min(bottom_limit, oy0 - _EXPAND_PAD)
    return x0, y0, max(x1, right_limit), max(y1, bottom_limit)


def insert_translations(page, units: list[TextUnit], translations: list[str], target: str) -> None:
    page_rect = page.rect
    registered: set[str] = set()

    def _register(name: str, fontfile: str) -> None:
        if name not in registered:
            page.insert_font(fontname=name, fontfile=fontfile)
            registered.add(name)

    for u, text in zip(units, translations):
        if not text.strip():
            continue
        # Pick the embedded font variant matching the block's dominant style so a
        # bold heading stays bold, an italic note stays italic.
        fontname, fontfile = fonts.font_variant(target, u.bold, u.italic)
        _register(fontname, fontfile)
        x0, y0, x1, y1 = u.bbox
        size, fitted = _largest_fit(x1 - x0, y1 - y0, text, fontname, u.size, fontfile)
        # If the translation only fits at an unreadably small size (it's wider
        # than the source, e.g. a short label that grew when translated) — or
        # doesn't fit at all — recover by reflowing into adjacent whitespace.
        if size < min(u.size, _READABLE) or not fitted:
            gx0, gy0, gx1, gy1 = _grow_bounds(u, units, page_rect)
            grown, gfit = _largest_fit(gx1 - gx0, gy1 - gy0, text, fontname, u.size, fontfile)
            if grown > size or (gfit and not fitted):
                x0, y0, x1, y1, size, fitted = gx0, gy0, gx1, gy1, grown, gfit
        # Anti-truncation: if it STILL doesn't fit, drop below the readable floor
        # so the text is never silently cut off (better tiny than missing).
        if not fitted:
            size = _largest_fit(x1 - x0, y1 - y0, text, fontname, u.size, fontfile,
                                min_size=_TRUNC_FLOOR)[0]
        color = fitz.sRGB_to_pdf(u.color)
        # Reflow the whole paragraph into its block at one size — consistent
        # sizing, confined to the (possibly grown) block so it never overflows.
        page.insert_textbox(
            fitz.Rect(x0, y0, x1, y1 + 2), text,
            fontsize=size, fontname=fontname, color=color, align=0,
        )


def find_layout_issues(page, expected_texts: list[str]) -> list[str]:
    """Render-time layout check: report text that spilled past the page edge, or
    expected translations that are missing/truncated from the output.

    Used as a self-verification gate after translating a page (the inline auto-fit
    in insert_translations should keep this empty; anything it reports is a real
    inconsistency worth fixing/flagging).
    """
    issues: list[str] = []
    rect = page.rect
    data = page.get_text("dict")
    norm_rendered = "".join(page.get_text("text").split())
    for b in data.get("blocks", []):
        if b.get("type") != 0:
            continue
        for line in b["lines"]:
            for s in line["spans"]:
                x0, y0, x1, y1 = s["bbox"]
                if x1 > rect.x1 + 1 or y1 > rect.y1 + 1 or x0 < -1 or y0 < -1:
                    issues.append(f"text past page edge: {s['text'][:20]!r}")
    for t in expected_texts:
        key = "".join(t.split())
        sample = key[: min(len(key), 12)]
        if sample and sample not in norm_rendered:
            issues.append(f"missing/truncated: {t[:25]!r}")
    return issues
