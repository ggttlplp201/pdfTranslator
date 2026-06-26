"""OCR fallback for PDFs whose text layer is broken or missing.

Most PDFs have a correct text layer we read directly. Some don't: scanned pages
have no text layer, and some digital PDFs have a broken font encoding so the
text extracts as mojibake (e.g. "Indoor Air Comfort Gold" -> "×²¼±±®ß·®"). For
those we render the page to an image and read it with Tesseract, then feed the
recovered text through the normal translate/redact/insert pipeline.

OCR only runs when the bundled-or-system `tesseract` binary is available; if it
isn't, enabled() returns False and the engine behaves exactly as before.
"""
import io

import fitz

from .models import TextUnit

LANGS = "eng+chi_sim+por"
DPI = 300
_MIN_CONF = 30.0          # drop low-confidence word noise
_GARBLED_RATIO = 0.30     # >30% Latin-1 high chars => mojibake text layer


def enabled() -> bool:
    """True only if pytesseract + the tesseract binary are usable."""
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def page_is_garbled(page) -> bool:
    """Heuristic: should this page use OCR instead of its text layer?

    - Lots of text but a high fraction of Latin-1 symbol/letter codes -> the
      font encoding is broken (mojibake). Real text (incl. accented Portuguese)
      sits well under the threshold; mojibake is ~80%+.
    - Almost no extractable text but the page has images -> scanned page.
    """
    text = page.get_text("text")
    stripped = [c for c in text if not c.isspace()]
    if len(stripped) < 12:
        return bool(page.get_images())  # little/no text + images => scanned
    high = sum(1 for c in stripped if 0x80 <= ord(c) <= 0xFF)
    return high / len(stripped) > _GARBLED_RATIO


def _intersect_area(a, b) -> float:
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[2], b[2]), min(a[3], b[3])
    return max(0.0, x1 - x0) * max(0.0, y1 - y0)


def over_text(bbox, block_rects, min_frac: float = 0.25) -> bool:
    """True if a fair share of this OCR box sits over a real text block.

    Lets us skip OCR'd graphics/logos (e.g. a stylised "Certificate" title image)
    that have no redactable text underneath — translating those would just overlay
    the untouched graphic. Only applies when text blocks exist (broken text layer);
    a truly scanned page has no blocks and keeps every OCR unit.
    """
    area = max(1e-6, (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]))
    inter = sum(_intersect_area(bbox, r) for r in block_rects)
    return inter / area >= min_frac


def _text_color(img, box) -> int:
    """Guess the text colour (black or white) from the page image under a box.

    The box is mostly background; if it's dark the text is light (white), else
    dark (black). Handles the common light-on-dark / dark-on-light cases.
    """
    from PIL import ImageStat
    x0, y0, x1, y1 = box
    crop = img.crop((x0, y0, max(x0 + 1, x1), max(y0 + 1, y1))).convert("L")
    mean = ImageStat.Stat(crop).mean[0]
    return 0xFFFFFF if mean < 128 else 0x000000


def extract_units(page, dpi: int = DPI, langs: str = LANGS) -> list[TextUnit]:
    """OCR the rendered page into paragraph-level TextUnits (PDF coordinates)."""
    import pytesseract
    from PIL import Image

    pix = page.get_pixmap(dpi=dpi)
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    data = pytesseract.image_to_data(img, lang=langs, output_type=pytesseract.Output.DICT)
    scale = 72.0 / dpi

    # Group words by (block, paragraph) so a paragraph becomes one unit (keeps
    # translation context, like the normal block-level extraction).
    groups: dict[tuple, dict] = {}
    for i in range(len(data["text"])):
        word = data["text"][i].strip()
        if not word:
            continue
        try:
            conf = float(data["conf"][i])
        except (TypeError, ValueError):
            conf = -1.0
        if conf < _MIN_CONF:
            continue
        key = (data["block_num"][i], data["par_num"][i])
        x, y, w, h = (data["left"][i], data["top"][i], data["width"][i], data["height"][i])
        g = groups.setdefault(key, {"words": [], "x0": 1e9, "y0": 1e9, "x1": 0.0, "y1": 0.0,
                                    "hsum": 0.0, "hn": 0})
        g["words"].append(word)
        g["x0"] = min(g["x0"], x)
        g["y0"] = min(g["y0"], y)
        g["x1"] = max(g["x1"], x + w)
        g["y1"] = max(g["y1"], y + h)
        g["hsum"] += h
        g["hn"] += 1

    units: list[TextUnit] = []
    for g in groups.values():
        text = " ".join(g["words"]).strip()
        if not text:
            continue
        box_px = (g["x0"], g["y0"], g["x1"], g["y1"])
        bbox = (g["x0"] * scale, g["y0"] * scale, g["x1"] * scale, g["y1"] * scale)
        size = (g["hsum"] / g["hn"]) * scale if g["hn"] else 10.0  # glyph height ~ font size
        units.append(TextUnit(text=text, bbox=bbox, size=size, color=_text_color(img, box_px)))

    # Reading order: top-to-bottom, then left-to-right.
    units.sort(key=lambda u: (round(u.bbox[1] / 5.0), u.bbox[0]))
    return units
