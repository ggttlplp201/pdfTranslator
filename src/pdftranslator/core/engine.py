import fitz

from . import lang, layout, terminology


def translate_pdf(input_path, output_path, source, target, provider, progress=None) -> None:
    lang.validate_source(source)
    lang.validate_target(target)

    doc = fitz.open(input_path)
    try:
        count = len(doc)
        for index, page in enumerate(doc):
            units = layout.extract_units(page)
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
                # Skip blocks the translator barely changed (product codes, brand
                # names): leaving the original preserves its exact format and any
                # special glyphs (®, ©, ™) the replacement font can't render.
                kept = [
                    (u, t) for u, t in zip(units, translations)
                    if not layout.is_noop_translation(u.text, t)
                ]
                if kept:
                    sel_units = [u for u, _ in kept]
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
