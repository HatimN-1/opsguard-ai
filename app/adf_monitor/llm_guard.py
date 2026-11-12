"""Evidence-bound validation of optional French enterprise LLM summaries.

The guard can reject unsupported numbers and pipeline identifiers, but is not
an entailment model. Accepted prose still requires human factual review.
"""

import re

from app.agent.response_guard import detect_contradictions
from app.agent.response_quality import detect_language

LLM_GUARD_VERSION = "NORTHSTAR_ADF_GUARD_CLAIMS_V2"

_REPORTED_ACTION = re.compile(
    r"\b(?:j['’]ai|nous avons|l['’]agent a)\s+"
    r"(?:redémarré|supprimé|approuvé|créé|modifié|réparé|relancé|déployé)",
    re.IGNORECASE,
)
_PIPELINE_ID = re.compile(r"\badf_\d{2}_[a-z]+\b", re.IGNORECASE)
_NUMERIC_TOKEN = re.compile(r"(?<![A-Za-z0-9_])\d+(?![A-Za-z0-9_])")
_CODE_IDENTIFIER = re.compile(r"\b[A-Z][A-Z0-9_]*_[A-Z0-9_]*\d[A-Z0-9_]*\b")
_OBSERVED_CODE_CLAIM = re.compile(
    r"\bcode(?: d['’]erreur)?\s+[`']?(\d+)[`']?\s+"
    r"(?:est\s+)?(?:observ[eé]|d[eé]tect[eé]|confirm[eé])\s+"
    r"(?:dans|sur)\s+(?:les?\s+)?(?:logs?|journaux?|pipelines?|ex[eé]cutions?)\b",
    re.IGNORECASE,
)
_COUNT_CLAIM = re.compile(
    r"(?<!\w)\d+\s+(?:(?:des?|d['’])\s+)?"
    r"(?:ex[eé]cutions?|activit[eé]s?|[eé]tapes?|[eé]v[eé]nements?|"
    r"succ[eè]s|r[eé]ussites?|[eé]checs?|erreurs?|incidents?|pipelines?|t[aâ]ches?)\b",
    re.IGNORECASE,
)
_RECURRENCE_CLAIM = re.compile(
    r"\b(?:persistant\w*|r[eé]current\w*|syst[eé]matique\w*|"
    r"se r[eé]p[eè]te|[aà] chaque ex[eé]cution)\b", re.IGNORECASE,
)
_FALSE_FAILURE_CLAIM = re.compile(
    r"\b(?:a [eé]chou[eé]|est en [eé]chec|[eé]chec (?:d[eé]tect[eé]|confirm[eé]|observ[eé])|"
    r"(?:incident|erreur|panne) (?:d[eé]tect[eé]|confirm[eé]|observ[eé]))\b",
    re.IGNORECASE,
)
_FALSE_SUCCESS_CLAIM = re.compile(
    r"\b(?:pipeline|ex[eé]cution)[^.]{0,80}"
    r"(?:a r[eé]ussi|est r[eé]ussi(?:e)?|s'est termin[eé]e? avec succ[eè]s)\b",
    re.IGNORECASE,
)


# Direct French negative quantifiers that grammatically negate the immediately
# following incident noun. Keep this tightly scoped: a negation elsewhere in a
# sentence must not excuse a separate affirmative failure claim.
_DIRECT_NEGATION = re.compile(
    r"(?:\baucun(?:e)?|\bpas\s+d['’]|\bpas\s+de|\bsans|"
    r"\babsence\s+d['’]|\babsence\s+de)\s*$",
    re.IGNORECASE,
)


def _has_affirmative_failure_claim(text: str) -> bool:
    """Reject *affirmative* failure claims on a successful run.

    Example: "Il n'y a pas d'échec détecté" is a negated observation,
    whereas "Aucun échec détecté. Pourtant le pipeline a échoué" still
    contains an affirmative failure and is rejected. This rule handles only
    direct local negation; it does not certify general semantic fidelity.
    """
    for match in _FALSE_FAILURE_CLAIM.finditer(text):
        # Do not let a negation in a previous sentence or another clause
        # override an affirmative claim. An apostrophe directly before the
        # matched noun is intentional ("pas d'échec").
        preceding = text[max(0, match.start() - 45):match.start()]
        preceding = re.split(r"[.!?;:\n]", preceding)[-1]
        if _DIRECT_NEGATION.search(preceding):
            continue
        return True
    return False

# A missing-document statement must be checked against the documents actually
# returned for the selected errors. It is not enough that a code is observed.
# Different valid French formulations of the SAME unsupported factual claim.
# The original rule covered only "Aucune documentation ... n'a été trouvée";
# Qwen also produces "Il n'y a pas de documentation officielle ...".
_DOC_NOUN = r"(?:documentation|documents?|r[eé]f[eé]rences?)\s+officiel(?:le)?s?"
_NO_OFFICIAL_DOC_FOUND = re.compile(
    rf"(?:\baucun(?:e)?\s+{_DOC_NOUN}\s+n['’]"
    rf"(?:a\s+pas\s+[eé]t[eé]|est\s+pas|a\s+[eé]t[eé])\s+"
    rf"(?:trouv[eé]e?s?|retrouv[eé]e?s?|identifi[eé]e?s?|disponible?s?)\b"
    rf"|\bil\s+n['’]y\s+a\s+pas\s+de\s+{_DOC_NOUN}\b"
    rf"|\b(?:aucun(?:e)?|pas\s+de)\s+{_DOC_NOUN}\s+pour\b"
    rf"|\b(?:la\s+)?documentation\s+officielle\s+(?:est|reste)\s+"
    rf"(?:introuvable|indisponible|inexistante)\b)",
    re.IGNORECASE,
)

_EXPLICIT_DOC_CODE = re.compile(
    r"\b(?:pour|sur|concernant)\s+(?:le\s+)?code\s+"
    r"([A-Za-z0-9_]+)\b", re.IGNORECASE,
)


def _denies_retrieved_documentation(text: str, documents: list[dict]) -> bool:
    """Reject a *negative retrieval claim* only if matching documents exist.

    Statements explicitly scoped to an undocumented error stay valid when
    documents for a different error have been retrieved in the same report.
    """
    documented_codes = {
        str(doc.get("matched_error_code", "")).casefold()
        for doc in documents
        if isinstance(doc, dict) and doc.get("matched_error_code")
    }
    if not documented_codes:
        return False
    for match in _NO_OFFICIAL_DOC_FOUND.finditer(text):
        statement = re.split(r"[.!?;\n]", text[match.start():], maxsplit=1)[0]
        specified = _EXPLICIT_DOC_CODE.search(statement)
        if specified:
            if specified.group(1).casefold() in documented_codes:
                return True
        else:
            # "ce code" or an unqualified claim is in conflict with one or
            # more retrieved documents, so it cannot be asserted as fact.
            return True
    return False



# A same (pipeline, error code) pair on two distinct failed runs proves
# repeated observed error codes, NOT repeated root causes.
_NO_RECORDED_RECURRENCE = re.compile(
    r"\b(?:il\s+n['’]y\s+a\s+pas\s+de\s+r[eé]currence\s+confirm[eé]e"
    r"|aucune\s+r[eé]currence\s+confirm[eé]e)\b",
    re.IGNORECASE,
)
_PSEUDO_RUN_ID = re.compile(
    r"\brun[_-]?id[_:-][A-Za-z0-9][A-Za-z0-9_.:-]*\b",
    re.IGNORECASE,
)


def _same_code_failed_runs_recur(facts: dict) -> bool:
    """Repetition must refer to one pipeline and distinct execution IDs."""
    grouped: dict[tuple[str, str], set[str]] = {}
    for item in facts.get("errors", []):
        if not isinstance(item, dict):
            continue
        pipeline = item.get("pipeline_name") or facts.get("pipeline_name")
        code, run_id = item.get("error_code"), item.get("run_id")
        if pipeline and code and run_id:
            grouped.setdefault((str(pipeline), str(code)), set()).add(str(run_id))
    return any(len(runs) >= 2 for runs in grouped.values())


def _verified_numbers(facts: dict, documents: list[dict]) -> set[str]:
    """Only source codes and curated documentation authorize free-standing numbers.

    Digits within a pipeline ID, activity name or UUID are NOT evidence of a
    corresponding numeric count or code. Those IDs must be validated as a whole.
    """
    fragments = []
    for error in facts.get("errors", [])[:15]:
        if isinstance(error, dict) and error.get("error_code"):
            fragments.append(str(error["error_code"]))
    for event in facts.get("evidence_events", [])[:12]:
        if isinstance(event, dict) and event.get("error_code"):
            fragments.append(str(event["error_code"]))
    for document in documents[:3]:
        if not isinstance(document, dict):
            continue
        for key in ("matched_error_code", "title", "summary_fr"):
            if document.get(key) is not None:
                fragments.append(str(document[key]))
        fragments.extend(str(v) for v in document.get("checks_fr", [])[:2])
    return set(_NUMERIC_TOKEN.findall(" ".join(fragments)))


def _mask_verified_ids(text: str, facts: dict) -> str:
    """Mask complete trusted identifiers before scanning standalone numbers."""
    identifiers = {str(item) for item in facts.get("pipeline_names", []) if item}
    for key in ("pipeline_name", "run_id"):
        if facts.get(key):
            identifiers.add(str(facts[key]))
    for record in [*facts.get("errors", []), *facts.get("evidence_events", [])]:
        if not isinstance(record, dict):
            continue
        for key in ("pipeline_name", "run_id", "activity_name", "activity_run_id"):
            if record.get(key):
                identifiers.add(str(record[key]))
    masked = text
    for identifier in sorted(identifiers, key=len, reverse=True):
        masked = re.sub(
            rf"(?<![A-Za-z0-9_]){re.escape(identifier)}(?![A-Za-z0-9_])",
            " [IDENTIFIANT] ", masked, flags=re.IGNORECASE,
        )
    return masked


def _pipeline_run_status(facts: dict) -> str | None:
    status = facts.get("pipeline_status_counts") or {}
    count = facts.get("distinct_pipeline_run_count", facts.get("pipeline_run_count"))
    if count == 1 and len(status) == 1:
        return next(iter(status))
    return None


def _has_repeated_failed_runs(facts: dict) -> bool:
    by_code: dict[str, set[str]] = {}
    for item in facts.get("errors", []):
        if not isinstance(item, dict) or not item.get("error_code") or not item.get("run_id"):
            continue
        by_code.setdefault(str(item["error_code"]), set()).add(str(item["run_id"]))
    return any(len(runs) >= 2 for runs in by_code.values())


def validate_llm_summary(
    text: str, facts: dict, documents: list[dict]
) -> tuple[str, str | None]:
    """Return an accepted summary or an explicit non-sensitive rejection reason.

    NOTE: This is a conservative evidence-token check, not semantic proof that
    all claims are true. The verified, deterministic report remains primary.
    """
    proposed = str(text or "").strip()
    if not proposed:
        return "", "EMPTY_RESPONSE"
    if len(proposed) > 900:
        return "", "TOO_LONG"
    if not proposed.endswith("."):
        return "", "INVALID_FORMAT"
    if _REPORTED_ACTION.search(proposed):
        return "", "FORBIDDEN_ACTION_CLAIM"
    if detect_language(proposed) != "fr":
        return "", "LANGUAGE"
    if detect_contradictions(proposed, []):
        return "", "CONTRADICTION"

    allowed_pipelines = {
        str(item).casefold() for item in facts.get("pipeline_names", [])
    }
    if facts.get("pipeline_name"):
        allowed_pipelines.add(str(facts["pipeline_name"]).casefold())
    if any(
        pipeline.casefold() not in allowed_pipelines
        for pipeline in _PIPELINE_ID.findall(proposed)
    ):
        return "", "UNVERIFIED_PIPELINE"

    status = _pipeline_run_status(facts)
    if status == "Succeeded" and _has_affirmative_failure_claim(proposed):
        return "", "UNSUPPORTED_FAILURE_CLAIM"
    if status == "Failed" and _FALSE_SUCCESS_CLAIM.search(proposed):
        return "", "UNSUPPORTED_SUCCESS_CLAIM"
    if _RECURRENCE_CLAIM.search(proposed) and not _has_repeated_failed_runs(facts):
        return "", "UNSUPPORTED_RECURRENCE_CLAIM"
    if _denies_retrieved_documentation(proposed, documents):
        return "", "CONTRADICTS_RETRIEVED_DOCUMENTATION"
    if (_NO_RECORDED_RECURRENCE.search(proposed)
            and _same_code_failed_runs_recur(facts)):
        return "", "CONTRADICTS_RECORDED_RECURRENCE"

    # Semantic contradictions observed in real business UI testing.
    if re.search(
        r"\b(?:les?\s+logs?|les?\s+journaux?)\s+"
        r"(?:prouvent?|d[eé]montrent?|confirment?)\s+"
        r"[^.!?]{0,85}(?:jeton\w*\s+expir[eé]|cause\s+racine|"
        r"manque\s+de\s+(?:java|jre))",
        proposed, re.IGNORECASE,
    ):
        return "", "UNSUPPORTED_ROOT_CAUSE_CLAIM"
    if re.search(
        r"\b(?:un\s+op[eé]rateur|une\s+v[eé]rification\s+humaine|"
        r"un\s+administrateur)\s+(?:a\s+)?"
        r"(?:confirm[eé]|valid[eé]|v[eé]rifi[eé])",
        proposed, re.IGNORECASE,
    ):
        return "", "UNVERIFIED_HUMAN_ACTION"
    if re.search(
        r"\b(?:aucune?|pas\s+d['’])\s+(?!autre)"
        r"(?:erreur\s+structur[eé]e|erreur\s+d[eé]tect[eé]e|code\s+d['’]erreur)"
        r"[^.!?]{0,100}(?:observ[eé]|d[eé]tect[eé]|signal[eé])",
        proposed, re.IGNORECASE,
    ) and facts.get("errors"):
        return "", "UNSUPPORTED_NO_ERROR_CLAIM"
    if (
        re.search(r"\bex[eé]cutions?\s+en\s+cours\b", proposed, re.IGNORECASE)
        and not (facts.get("pipeline_status_counts") or {}).get("InProgress")
        and not re.search(
            r"\baucune?\s+ex[eé]cution\s+en\s+cours", proposed, re.IGNORECASE
        )
    ):
        return "", "UNSUPPORTED_IN_PROGRESS_CLAIM"
    if re.search(
        r"\b(?:aucune?\s+documentation\s+officielle\s+(?:n['’]existe|n['’]est)|"
        r"documentation\s+officielle\s+inexistante)", proposed, re.IGNORECASE,
    ):
        return "", "UNSUPPORTED_GLOBAL_DOCUMENTATION_CLAIM"
    observed_run_ids = {
        str(item.get("run_id", "")).casefold()
        for item in [*facts.get("run_records", []), *facts.get("evidence_events", []),
                     *facts.get("errors", [])]
        if isinstance(item, dict) and item.get("run_id")
    }
    if facts.get("run_id"):
        observed_run_ids.add(str(facts["run_id"]).casefold())
    uuid_ids = re.findall(
        r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
        proposed, re.IGNORECASE,
    )
    claimed_ids = [*uuid_ids, *_PSEUDO_RUN_ID.findall(proposed)]
    if any(value.casefold() not in observed_run_ids for value in claimed_ids):
        return "", "UNVERIFIED_RUN_ID"

    if _COUNT_CLAIM.search(proposed):
        return "", "UNSUPPORTED_COUNT_CLAIM"
    observed_codes = {
        str(item.get("error_code"))
        for item in facts.get("errors", []) if isinstance(item, dict) and item.get("error_code")
    }
    for match in _OBSERVED_CODE_CLAIM.finditer(proposed):
        if match.group(1) not in observed_codes:
            return "", "UNOBSERVED_ERROR_CLAIM"
    approved_codes = {
        str(item.get("error_code"))
        for item in facts.get("errors", []) if isinstance(item, dict) and item.get("error_code")
    }
    for code in _CODE_IDENTIFIER.findall(proposed):
        if code not in approved_codes:
            return "", "UNVERIFIED_ERROR_CODE"

    allowed_numbers = _verified_numbers(facts, documents)
    numeric_text = _mask_verified_ids(proposed, facts)
    if any(number not in allowed_numbers for number in _NUMERIC_TOKEN.findall(numeric_text)):
        return "", "UNVERIFIED_NUMBER"
    return proposed, None
