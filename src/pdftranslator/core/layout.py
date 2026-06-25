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
    for u in units:
        page.add_redact_annot(fitz.Rect(u.bbox))
    if units:
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)


def _fit_fontsize(width: float, height: float, text: str, fontname: str, max_size: float) -> float:
    font = fitz.Font(fontname)
    size = max_size
    while size >= 4.0:
        text_width = font.text_length(text, fontsize=size)
        # Check if text fits on a single line within the available width
        if text_width <= width:
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
