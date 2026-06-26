import fitz

from . import lang, layout, ocr, terminology


def translate_pdf(input_path, output_path, source, target, provider, progress=None) -> None:
    lang.validate_source(source)
    lang.validate_target(target)
    use_ocr = ocr.enabled()

    doc = fitz.open(input_path)
    try:
        count = len(doc)
        for index, page in enumerate(doc):
            units = layout.extract_units(page)
            # Fallback: if the text layer is broken/missing, recover text via OCR.
            ocr_page = False
            if use_ocr and ocr.page_is_garbled(page):
                ocr_units = ocr.extract_units(page)
                # If the page has a (broken) text layer, only translate OCR boxes
                # that sit over real text — leave graphics/logos (e.g. a title
                # image) untouched. A truly scanned page has no blocks: keep all.
                block_rects = [
                    b["bbox"] for b in page.get_text("dict").get("blocks", [])
                    if b.get("type") == 0
                ]
                if block_rects:
                    ocr_units = [u for u in ocr_units if ocr.over_text(u.bbox, block_rects)]
                if ocr_units:
                    layout.redact_blocks(page)  # clear the broken original text layer
                    units = ocr_units
                    ocr_page = True
            if units:
                # Mask brand names / codes / IDs so the translator can't mangle
                # them, then restore them verbatim in the result.
                masked, masks = [], []
                for u in units:
                    m, terms = terminology.protect(u.text)
                    masked.append(m)
                    masks.append(terms)
                raw = provider.translate(masked, source, target)
                translations = [terminology.restore(t, terms) for t, terms in zip(raw, masks)]
                if ocr_page:
                    # The broken original was already cleared, so insert every OCR
                    # unit (don't keep-original — there's nothing good to keep).
                    kept = list(zip(units, translations))
                else:
                    # Skip blocks the translator barely changed (product codes,
                    # brand names): leaving the original preserves its exact format
                    # and special glyphs (®, ©, ™) the replacement font can't render.
                    kept = [
                        (u, t) for u, t in zip(units, translations)
                        if not layout.is_noop_translation(u.text, t)
                    ]
                if kept:
                    sel_units = [u for u, _ in kept]
                    if not ocr_page:
                        layout.redact_units(page, sel_units)
                    layout.insert_translations(page, sel_units, [t for _, t in kept], target)
            if progress is not None:
                progress(index, count)
        # Subset embedded fonts so a 10MB CJK font shrinks to the few KB actually
        # used, keeping output files small.
        try:
            doc.subset_fonts()
        except Exception:
            pass  # subsetting is an optimization; never fail the translation over it
        doc.save(output_path, garbage=4, deflate=True)
    finally:
        doc.close()
