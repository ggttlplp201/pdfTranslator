import fitz

from . import fonts, lang, layout


def translate_pdf(input_path, output_path, source, target, provider, progress=None) -> None:
    lang.validate_source(source)
    lang.validate_target(target)
    fontname = fonts.font_for_language(target)

    doc = fitz.open(input_path)
    try:
        count = len(doc)
        for index, page in enumerate(doc):
            units = layout.extract_units(page)
            if units:
                translations = provider.translate([u.text for u in units], source, target)
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
                    layout.insert_translations(page, sel_units, [t for _, t in kept], fontname)
            if progress is not None:
                progress(index, count)
        doc.save(output_path, garbage=4, deflate=True)
    finally:
        doc.close()
