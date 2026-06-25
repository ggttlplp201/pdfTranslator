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
