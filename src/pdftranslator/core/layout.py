import fitz

from .models import TextUnit


# Module-level cache for fonts to avoid rebuilding on each call
_FONT_CACHE = {}


def extract_units(page) -> list[TextUnit]:
    units: list[TextUnit] = []
    data = page.get_text("dict")
    for block in data.get("blocks", []):
        if block.get("type") != 0:  # 0 == text block
            continue
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            text = "".join(s.get("text", "") for s in spans)
            if not text.strip():
                continue
            size = max((s.get("size", 10.0) for s in spans), default=10.0)
            color = spans[0].get("color", 0) if spans else 0
            units.append(
                TextUnit(text=text, bbox=tuple(line["bbox"]), size=size, color=color)
            )
    return units


def _get_cached_font(fontname: str) -> fitz.Font:
    """Get or create a font from the cache."""
    return _FONT_CACHE.setdefault(fontname, fitz.Font(fontname))


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


def _fit_fontsize(width: float, height: float, text: str, fontname: str, max_size: float) -> float:
    font = _get_cached_font(fontname)
    size = max_size
    while size >= 4.0:
        text_width = font.text_length(text, fontsize=size)
        # Check if text fits within both width and height constraints
        if text_width <= width and size <= height:
            return size
        size -= 0.5
    return 4.0


def insert_translations(page, units: list[TextUnit], translations: list[str], fontname: str) -> None:
    for u, text in zip(units, translations):
        if not text.strip():
            continue
        x0, y0, x1, y1 = u.bbox
        width = x1 - x0
        height = y1 - y0
        size = _fit_fontsize(width, height, text, fontname, u.size)
        color = fitz.sRGB_to_pdf(u.color)
        # Position text vertically centered in the bbox
        # insert_text uses top-left as reference, so we offset by the font height
        y_offset = y0 + (height - size) * 0.5 + size * 0.75
        page.insert_text((x0, y_offset), text, fontsize=size, fontname=fontname, color=color)
