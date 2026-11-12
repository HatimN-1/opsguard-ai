"""Build safe, helpful answers from successful simulated MLOps tool results."""

import math
import re

from app.agent.response_guard import detect_contradictions
from app.agent.response_quality import detect_language

# Display translations of the known, versioned simulated runbook steps.
# Unknown future steps remain source text instead of being invented.
KNOWN_RUNBOOK_TRANSLATIONS = {
    "Inspect the latest pipeline execution logs.":
        "Examiner les journaux de la dernière exécution du pipeline.",
    "Compare source and expected schemas.":
        "Comparer le schéma source au schéma attendu.",
    "Identify missing fields or incompatible data types.":
        "Identifier les champs manquants ou les types de données incompatibles.",
    "Validate the transformation configuration.":
        "Vérifier la configuration des transformations.",
    "Test the corrected schema on a sample dataset.":
        "Tester le schéma corrigé sur un échantillon de données.",
    "Inspect average latency and P95 latency.":
        "Examiner les latences moyenne et P95.",
    "Review CPU and memory utilization.":
        "Contrôler l'utilisation du processeur et de la mémoire.",
    "Check the number of concurrent requests.":
        "Vérifier le nombre de requêtes simultanées.",
    "Investigate slow preprocessing operations.":
        "Examiner les opérations de prétraitement lentes.",
    "Compare latency against the reference baseline.":
        "Comparer la latence aux valeurs de référence.",
    "Calculate the missing-value rate for each feature.":
        "Calculer le taux de valeurs manquantes par variable.",
    "Compare the rates with the reference dataset.":
        "Comparer les taux avec le jeu de données de référence.",
    "Identify recent changes in upstream data sources.":
        "Identifier les modifications récentes des sources de données amont.",
    "Review the preprocessing and imputation rules.":
        "Vérifier les règles de prétraitement et d'imputation.",
    "Escalate if the missing values affect critical features.":
        "Escalader si les valeurs manquantes affectent des variables critiques.",
}


def _identifier(value: object) -> str | None:
    """Only show short technical identifiers in deterministic facts."""
    if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,80}", value):
        return value
    return None


def _percentage(value: object) -> str | None:
    if (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and 0 <= value <= 100
    ):
        return f"{value:g} %"
    return None


def _number(value: object) -> str | None:
    if type(value) is int and value >= 0:
        return f"{value:,}".replace(",", " ")
    return None


def _latency(value: object) -> str | None:
    if (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0
    ):
        return f"{value:g} ms"
    return None


def _safe_runbook_step(value: object) -> str | None:
    """Display limited text from simulated runbooks, never execute it."""
    if not isinstance(value, str):
        return None
    step = " ".join(value.split())
    return KNOWN_RUNBOOK_TRANSLATIONS.get(step, step[:220]) if step else None


def compose_grounded_answer(
    question: str,
    generated_answer: str,
    tool_results: list[dict],
) -> str:
    """Ground answers and refuse unsupported ticket action claims.

    The verified section is assembled from the Python tool outputs, not the LLM.
    Free-form text is only displayed when it passes limited quality checks.
    """
    issues = detect_contradictions(generated_answer, tool_results)
    # Default unknown short requests to French rather than discarding evidence.
    french_question = detect_language(question) != "en"
    if not french_question:
        if "UNVERIFIED_TICKET_ACTION" in issues:
            return (
                "No ticket was created or approved by this agent. "
                "Human authorization is required."
            )
        return generated_answer

    facts: list[str] = []
    procedures: list[str] = []
    proposal_only = False

    for result in tool_results:
        if not isinstance(result, dict) or result.get("ok") is not True:
            continue
        name = result.get("tool")
        data = result.get("data")

        if name == "get_pipeline_status" and isinstance(data, dict):
            pipeline_id = _identifier(data.get("pipeline_id"))
            status = data.get("status")
            statuses = {"FAILED": "en échec", "SUCCESS": "réussi", "RUNNING": "en cours"}
            if pipeline_id and status in statuses:
                facts.append(
                    f"Le pipeline {pipeline_id} est {statuses[status]} (statut {status})."
                )
            error_code = _identifier(data.get("error_code"))
            if error_code:
                facts.append(f"Code d'erreur : {error_code}.")
            records = _number(data.get("records_processed"))
            invalid = _number(data.get("invalid_records"))
            if records is not None and invalid is not None:
                facts.append(f"Enregistrements traités : {records} ; invalides : {invalid}.")

        elif name == "get_model_metrics" and isinstance(data, dict):
            model_id = _identifier(data.get("model_id"))
            if model_id:
                facts.append(f"Modèle consulté : {model_id}.")
            requests = _number(data.get("requests_total"))
            if requests is not None:
                facts.append(f"Nombre de requêtes : {requests}.")
            error_rate = _percentage(data.get("error_rate_pct"))
            invalid_rate = _percentage(data.get("invalid_input_rate_pct"))
            if error_rate is not None:
                facts.append(f"Taux d'erreur : {error_rate}.")
            if invalid_rate is not None:
                facts.append(f"Taux d'entrées invalides : {invalid_rate}.")
            avg_latency = _latency(data.get("latency_avg_ms"))
            p95_latency = _latency(data.get("latency_p95_ms"))
            if avg_latency is not None:
                facts.append(f"Latence moyenne : {avg_latency}.")
            if p95_latency is not None:
                facts.append(f"Latence P95 : {p95_latency}.")

        elif name == "search_runbook" and isinstance(data, list):
            for runbook in data[:3]:
                if not isinstance(runbook, dict):
                    continue
                runbook_id = _identifier(runbook.get("runbook_id"))
                if runbook_id:
                    facts.append(f"Procédure consultée : {runbook_id}.")
                if runbook.get("human_approval_required") is True:
                    facts.append(
                        "La procédure consultée indique qu'une validation humaine est requise."
                    )
                steps = runbook.get("diagnostic_steps")
                if runbook_id and isinstance(steps, list):
                    procedures.append(f"Étapes documentées dans {runbook_id} :")
                    for number, raw_step in enumerate(steps[:5], start=1):
                        step = _safe_runbook_step(raw_step)
                        if step:
                            procedures.append(f"{number}. {step}")

        elif (
            name == "prepare_incident_ticket"
            and isinstance(data, dict)
            and data.get("status") == "PROPOSAL_ONLY"
            and data.get("ticket_created") is False
            and data.get("human_approval_required") is True
        ):
            proposal_only = True
            incident_id = _identifier(data.get("incident_id"))
            if incident_id:
                facts.append(
                    f"Pour l'incident {incident_id}, seule une proposition "
                    "de ticket a été préparée."
                )
            facts.append(
                "Aucun ticket n'a été créé ni approuvé par cet agent. "
                "Une validation humaine est nécessaire."
            )

    verified_section = (
        "Faits vérifiés (données simulées) :\n" + "\n".join(f"- {fact}" for fact in facts)
        if facts
        else ""
    )
    if procedures:
        verified_section += "\n\n" + "\n".join(procedures)

    if proposal_only:
        return (
            verified_section
            + "\n\nLa réponse libre du modèle n'est pas reprise pour cette "
            "proposition de ticket. Toute approbation nécessite une "
            "intervention humaine distincte."
        )

    if "UNVERIFIED_TICKET_ACTION" in issues:
        note = (
            "Aucune création ni approbation de ticket n'a été exécutée "
            "par cet agent. Une validation humaine est requise."
        )
        return (verified_section + "\n\n" + note) if verified_section else note

    if issues:
        note = (
            "L'analyse générée a été masquée car une contradiction "
            "potentielle a été détectée."
        )
        return (verified_section + "\n\n" + note) if verified_section else note

    if not facts:
        if detect_language(generated_answer) == "fr":
            return generated_answer
        if re.search(r"ticket|approuv|approb", question, flags=re.IGNORECASE):
            return (
                "Cet agent ne peut ni créer ni approuver de ticket. "
                "Aucune action de ce type n'a été exécutée par cet agent. "
                "Une validation humaine est nécessaire."
            )
        return (
            "Je n'ai pas de faits vérifiés à présenter pour cette demande. "
            "Tu peux préciser un pipeline, un modèle ou un incident."
        )

    if detect_language(generated_answer) == "fr":
        return verified_section + "\n\nAnalyse du modèle (à vérifier) :\n" + generated_answer

    # No repetitive, unhelpful language-detection warning after valid facts.
    return verified_section
