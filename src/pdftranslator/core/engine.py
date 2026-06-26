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
                layout.redact_units(page, units)
                layout.insert_translations(page, units, translations, fontname)
            if progress is not None:
                progress(index, count)
        doc.save(output_path, garbage=4, deflate=True)
    finally:
        doc.close()
