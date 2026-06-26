import fitz

from .models import TextUnit


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


def _rendered_width(text: str, fontname: str, size: float) -> float:
    """Actual rendered width of one line of `text`, measured by the real renderer.

    fitz.Font.text_length under-measures Latin glyphs in the built-in CJK font by
    ~30% (it reports a width far smaller than what insert_text actually draws), so
    mixed Chinese/Latin lines overflowed the column. Rendering to a scratch page
    and reading the span bbox gives the true width.
    """
    doc = fitz.open()
    try:
        page = doc.new_page(width=10000, height=200)
        page.insert_text((0, 100), text, fontsize=size, fontname=fontname)
        data = page.get_text("dict")
        rights = [
            span["bbox"][2]
            for block in data.get("blocks", []) if block.get("type") == 0
            for line in block["lines"]
            for span in line["spans"]
        ]
        return max(rights) if rights else 0.0
    finally:
        doc.close()


_MIN_SIZE = 4.0


def _ideal_width_size(width: float, text: str, fontname: str, max_size: float) -> float:
    """Font size (unclamped) at which `text`'s rendered width equals `width`.

    Returns max_size when the text already fits. May return a value below the
    readable floor, which the caller uses to decide between single-line placement
    and wrapping. Width scales linearly with size, so measure once and scale.
    """
    rendered = _rendered_width(text, fontname, max_size)
    if rendered <= width or rendered <= 0:
        return max_size
    return max_size * width / rendered


def _fit_fontsize(width: float, height: float, text: str, fontname: str, max_size: float) -> float:
    """Largest size <= max_size (floor 4.0) at which `text`'s rendered width fits `width`.

    `height` is accepted for signature compatibility; single-line placement is
    constrained by width.
    """
    return max(_ideal_width_size(width, text, fontname, max_size), _MIN_SIZE)


def insert_translations(page, units: list[TextUnit], translations: list[str], fontname: str) -> None:
    for u, text in zip(units, translations):
        if not text.strip():
            continue
        x0, y0, x1, y1 = u.bbox
        width = x1 - x0
        height = y1 - y0
        color = fitz.sRGB_to_pdf(u.color)
        ideal = _ideal_width_size(width, text, fontname, u.size)
        if ideal >= _MIN_SIZE:
            # Fits on one line at a readable size: place exactly at the baseline.
            size = min(ideal, u.size)
            y_baseline = y0 + (height - size) * 0.5 + size * 0.75
            page.insert_text((x0, y_baseline), text, fontsize=size, fontname=fontname, color=color)
        else:
            # Too long for one line even at the floor size: wrap within the box so
            # it can never run off the page (may clip vertically in extreme cases).
            page.insert_textbox(
                fitz.Rect(x0, y0, x1, y1 + 2), text,
                fontsize=_MIN_SIZE, fontname=fontname, color=color, align=0,
            )
