"""Protect brand names, codes, standards and IDs from being translated.

Translators (LLM or Google) routinely mangle product codes and company suffixes
— e.g. "IACG-456-01-06-2025Arev" → "IACG-456-...A版", "S.A.U." → "S.p.A.",
"Pladur®" loses its ®. We mask such spans with numeric placeholders ({0}, {1},
…) before translating and restore them verbatim afterwards. Placeholders of this
form survive both Google and the LLM engines intact (verified); the translator
may reorder them, which is fine because restoration is keyed by number.
"""
import re

_PLACEHOLDER = "{%d}"
_PLACEHOLDER_RE = re.compile(r"\{(\d+)\}")

# Multi-word patterns first (they contain spaces a token scan would split).
_PHRASES = re.compile(
    r"""(
        https?://\S+                                  # URLs
      | [^\s@]+@[^\s@]+\.[^\s@]+                       # emails
      | \b(?:EN|ISO|IEC|DIN|UNE|ASTM|EMICODE)\s?\d{2,}(?:[-‑]\d+)?\b  # standards
    )""",
    re.VERBOSE,
)

# Company names: a run of capitalised words ending in a legal suffix. High
# precision (the suffix anchors it), so it won't swallow ordinary headings.
_COMPANY = re.compile(
    r"\b(?:[A-Z][\w&]*\.?\s+){1,4}"
    r"(?:S\.A\.U|S\.A\.S|S\.p\.A|S\.A|S\.L|N\.V|B\.V|GmbH|Ltd|Inc|LLC|AG|SARL)\.?",
)

# Token-level candidates: a run of letters/digits and code punctuation.
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9/+®™©.\-]*")
_DOTTED_ACRONYM = re.compile(r"^(?:[A-Za-z]\.){2,}[A-Za-z]?\.?$")  # S.A.U., S.p.A.


def _is_protected_token(t: str) -> bool:
    has_alpha = any(c.isalpha() for c in t)
    has_digit = any(c.isdigit() for c in t)
    if has_alpha and has_digit:
        return True                       # alphanumeric code / model (C12/25, H1)
    if any(c in "®™©" for c in t):
        return True                       # trademarked token (Pladur®)
    if t.endswith("+") and t[0].isalpha():
        return True                       # FON+
    if _DOTTED_ACRONYM.match(t):
        return True                       # S.A.U.
    return False


def protect(text: str) -> tuple[str, list[str]]:
    """Return (masked_text, terms). Restore later with restore()."""
    terms: list[str] = []

    def take(s: str) -> str:
        terms.append(s)
        return _PLACEHOLDER % (len(terms) - 1)

    text = _COMPANY.sub(lambda m: take(m.group(0)), text)
    text = _PHRASES.sub(lambda m: take(m.group(0)), text)
    text = _TOKEN.sub(lambda m: take(m.group(0)) if _is_protected_token(m.group(0)) else m.group(0), text)
    return text, terms


def restore(text: str, terms: list[str]) -> str:
    def sub(m: re.Match) -> str:
        i = int(m.group(1))
        return terms[i] if 0 <= i < len(terms) else m.group(0)
    return _PLACEHOLDER_RE.sub(sub, text)
