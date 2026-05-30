from __future__ import annotations

from hibs_racing.nlp.sectional_proxy import SectionalProxyFeatures, extract_sectional_features, merge_tag_scores
from hibs_racing.nlp.tagger_regex import tag_comment
from hibs_racing.nlp.tagger_spacy import spacy_available, spacy_tag_scores


def parse_comment(
    text: str | None,
    *,
    race_type: str | None = None,
    use_spacy: bool = False,
) -> SectionalProxyFeatures:
    """
    NLP pipeline: normalize → regex tags → optional spaCy merge → sectional proxies.

    This is the GPS-sectional reverse-engineering entry point for rankers.
    """
    if use_spacy and spacy_available():
        base = tag_comment(text, race_type=race_type)
        boosted = spacy_tag_scores(text)
        merged = merge_tag_scores(base, boosted)
        return extract_sectional_features(
            text,
            race_type=race_type,
            base_tags=merged,
            parser_backend="regex+spacy",
        )

    backend = "regex+spacy" if use_spacy and spacy_available() else "regex"
    return extract_sectional_features(text, race_type=race_type, parser_backend=backend)
