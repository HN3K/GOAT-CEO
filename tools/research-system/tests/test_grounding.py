"""Phase 2/3 primitive: mechanical quote-presence (the free anti-hallucination floor)."""

from research_system.grounding import normalize_ws, quote_present

SOURCE = (
    "Retrieval-augmented generation grounds each statement in retrieved source text.\n"
    "When the full article is captured to disk, the task shifts from recall to extraction.\n"
    "A mechanical check that the quoted span appears verbatim catches fabrications."
)


def test_exact_present():
    assert quote_present("grounds each statement in retrieved source text", SOURCE)


def test_whitespace_normalized_match():
    # quote spans a newline in the source and uses different spacing
    assert quote_present("source text.   When the full article", SOURCE)
    assert quote_present("recall to\nextraction", SOURCE)


def test_absent_returns_false():
    assert not quote_present("models hallucinate because of vibes", SOURCE)


def test_paraphrase_fails():
    # same meaning, not verbatim -> must fail (this is the point)
    assert not quote_present("captured to the filesystem", SOURCE)


def test_empty_quote_false():
    assert not quote_present("", SOURCE)
    assert not quote_present("   ", SOURCE)


def test_casefold_option():
    assert not quote_present("RETRIEVAL-AUGMENTED GENERATION", SOURCE)          # strict
    assert quote_present("RETRIEVAL-AUGMENTED GENERATION", SOURCE, casefold=True)


def test_normalize_ws():
    assert normalize_ws("  a\n\n  b\t c ") == "a b c"
