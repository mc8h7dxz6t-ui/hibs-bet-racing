from __future__ import annotations

from functools import lru_cache

from hibs_racing.nlp.normalize import normalize_comment
from hibs_racing.nlp.tagger_regex import TAG_PATTERNS

_SPACY_AVAILABLE: bool | None = None


def spacy_available() -> bool:
    global _SPACY_AVAILABLE
    if _SPACY_AVAILABLE is not None:
        return _SPACY_AVAILABLE
    try:
        import spacy  # noqa: F401
        from spacy.matcher import PhraseMatcher  # noqa: F401

        _SPACY_AVAILABLE = True
    except ImportError:
        _SPACY_AVAILABLE = False
    return _SPACY_AVAILABLE


@lru_cache(maxsize=1)
def _load_nlp():
    import spacy

    try:
        return spacy.load("en_core_web_sm")
    except OSError as exc:
        raise RuntimeError(
            "spaCy model missing — run: python -m spacy download en_core_web_sm"
        ) from exc


@lru_cache(maxsize=1)
def _phrase_matcher():
    from spacy.matcher import PhraseMatcher

    nlp = _load_nlp()
    matcher = PhraseMatcher(nlp.vocab, attr="LOWER")
    for tag, patterns in TAG_PATTERNS.items():
        phrases = []
        for pattern, _weight in patterns:
            # PhraseMatcher uses literal phrases; strip regex anchors/alternation.
            literal = pattern.replace(r"\b", "").replace("(?:", "").replace(")", "")
            literal = literal.replace("|", " ").replace(r"\d+", "2").replace("+", "")
            literal = literal.replace(r"\s+", " ").strip()
            if literal and not literal.startswith("("):
                phrases.append(nlp.make_doc(literal))
        if phrases:
            matcher.add(tag, phrases)
    return matcher


def spacy_tag_scores(text: str | None) -> dict[str, float]:
    """
    Optional spaCy PhraseMatcher pass — same tag vocabulary as regex.
    Returns empty dict if spaCy is not installed.
    """
    if not spacy_available():
        return {}

    norm = normalize_comment(text).normalized
    if not norm:
        return {}

    nlp = _load_nlp()
    doc = nlp(norm)
    matcher = _phrase_matcher()
    scores = {tag: 0.0 for tag in TAG_PATTERNS}
    for match_id, _start, _end in matcher(doc):
        tag = nlp.vocab.strings[match_id]
        scores[tag] = min(1.0, scores[tag] + 0.85)
    return scores
