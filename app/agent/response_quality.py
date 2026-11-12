"""Lightweight response-quality and language checks for OpsGuard AI."""

import re
import unicodedata

FRENCH_WORDS = {
    "le", "la", "les", "un", "une", "des", "du", "de", "est", "sont",
    "dans", "avec", "pour", "vous", "votre", "cette", "ces", "donnees",
    "erreur", "echec", "echoue", "reussi", "succes", "verifier",
    "procedure", "metriques", "correspondant", "probleme", "analyse",
    "consulte", "quel", "quelle", "quels", "quelles", "pourquoi", "comment",
    "son", "ses", "je", "nous", "me", "ne", "pas", "peux", "peut", "puis",
    "aider", "aide", "suis", "bonjour", "bonsoir", "merci", "ici",
    "ce", "cet", "que", "qui", "au", "aux", "sur", "et", "ou", "plus",
    "resultat", "resultats", "information", "informations", "voici",
    "disponible", "disponibles", "analysees", "consulter", "pipeline",
}

ENGLISH_WORDS = {
    "the", "and", "for", "with", "from", "this", "that", "your", "you",
    "are", "is", "was", "were", "should", "check", "data", "steps",
    "issue", "shows", "failed", "please", "following", "has", "how",
    "can", "assist", "hello", "today", "cannot", "without", "human",
    "approval", "model", "metrics", "runbook", "available", "error",
}


def normalize_text(text: str) -> str:
    """Normalize casing and accents for simple rule-based matching."""
    normalized = unicodedata.normalize("NFKD", text.casefold())
    return "".join(
        character for character in normalized if not unicodedata.combining(character)
    )


def detect_language(text: str) -> str:
    """Estimate French/English with conservative, explainable heuristics."""
    words = re.findall(r"[a-z]+", normalize_text(text))
    french_count = sum(word in FRENCH_WORDS for word in words)
    english_count = sum(word in ENGLISH_WORDS for word in words)

    if french_count >= 2 and french_count > english_count:
        return "fr"
    if english_count >= 2 and english_count > french_count:
        return "en"
    return "indeterminate"


def score_response(answer: str, expected_facts: dict[str, list[str]]) -> dict:
    """Check language and required factual mentions in evaluation responses."""
    if not expected_facts:
        raise ValueError("Expected facts cannot be empty")

    normalized_answer = normalize_text(answer)
    missing_facts = sorted(
        fact_name
        for fact_name, alternatives in expected_facts.items()
        if not any(
            normalize_text(alternative) in normalized_answer
            for alternative in alternatives
        )
    )
    language = detect_language(answer)
    coverage = (len(expected_facts) - len(missing_facts)) / len(expected_facts)
    language_ok = language == "fr"
    return {
        "detected_language": language,
        "language_ok": language_ok,
        "fact_coverage": round(coverage, 4),
        "missing_facts": missing_facts,
        "passed": language_ok and not missing_facts,
    }
