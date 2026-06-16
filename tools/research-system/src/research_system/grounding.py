"""Mechanical grounding check — the cheap, model-free anti-hallucination floor.

A claim's quote must appear (near-)verbatim in its cited source file. Matching is
whitespace-normalized (markdown wraps lines, PDFs inject newlines) but otherwise
literal, so a fabricated or paraphrased "quote" fails. This is verification step
6a (DESIGN §3) and is reused by the answerer to self-check.
"""

from __future__ import annotations

import re

_WS = re.compile(r"\s+")


def normalize_ws(text: str) -> str:
    """Collapse all whitespace runs to single spaces and strip ends."""
    return _WS.sub(" ", text).strip()


def quote_present(quote: str, source_text: str, *, casefold: bool = False) -> bool:
    """True if ``quote`` appears in ``source_text`` ignoring only whitespace.

    ``casefold=True`` also ignores case — useful to distinguish "absent" from
    "present but mis-cased" in diagnostics. Default is case-sensitive (strict).
    """
    q = normalize_ws(quote)
    if not q:
        return False
    src = normalize_ws(source_text)
    if casefold:
        return q.casefold() in src.casefold()
    return q in src
