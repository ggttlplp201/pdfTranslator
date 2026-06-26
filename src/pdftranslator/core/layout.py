import re

import fitz

from .models import TextUnit

_MIN_SIZE = 4.0


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
        spans = [s for line in block.get("lines", []) for s in line.get("spans", [])]
        size = max((s.get("size", 10.0) for s in spans), default=10.0)
        color = spans[0].get("color", 0) if spans else 0
        units.append(TextUnit(text=text, bbox=tuple(block["bbox"]), size=size, color=color))
    return units


def redact_units(page, units: list[TextUnit]) -> None:
    # Capture existing links before redaction: apply_redactions deletes any link
    # annotation whose rectangle overlaps a redacted area.
    links_before = page.get_links()
    for u in units:
        page.add_redact_annot(fitz.Rect(u.bbox))
    if units:
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)
        # Restore links that were deleted. Links that did NOT overlap survive on
        # their own, so we compare by xref to avoid creating duplicates.
        if links_before:
            after_xrefs = {lnk["xref"] for lnk in page.get_links()}
            for lnk in links_before:
                if lnk["xref"] not in after_xrefs:
                    restore = {k: v for k, v in lnk.items() if k not in ("xref", "id")}
                    page.insert_link(restore)


def _fit_textbox(width: float, height: float, text: str, fontname: str, max_size: float) -> float:
    """Largest size <= max_size (floor 4.0) at which `text` fits a width x height box.

    Measured with the real renderer (insert_textbox on a scratch page), which
    handles wrapping and mixed CJK/Latin widths correctly. One size for the whole
    block keeps the font consistent within a paragraph.
    """
    box_w = max(width, 1.0)
    box_h = max(height, 1.0) + 2.0
    rect = fitz.Rect(0, 0, box_w, box_h)
    scratch = fitz.open()
    try:
        size = max_size
        while size >= _MIN_SIZE:
            sp = scratch.new_page(width=box_w + 4, height=box_h + 10)
            leftover = sp.insert_textbox(rect, text, fontsize=size, fontname=fontname)
            if leftover >= 0:  # whole text fit at this size
                return size
            size -= 0.5
        return _MIN_SIZE
    finally:
        scratch.close()


def insert_translations(page, units: list[TextUnit], translations: list[str], fontname: str) -> None:
    for u, text in zip(units, translations):
        if not text.strip():
            continue
        x0, y0, x1, y1 = u.bbox
        size = _fit_textbox(x1 - x0, y1 - y0, text, fontname, u.size)
        color = fitz.sRGB_to_pdf(u.color)
        # Reflow the whole paragraph into its block at one size — consistent
        # sizing, and confined to the block width so it never overflows the page.
        page.insert_textbox(
            fitz.Rect(x0, y0, x1, y1 + 2), text,
            fontsize=size, fontname=fontname, color=color, align=0,
        )
