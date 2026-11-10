
"""Build safe French answers grounded in successful tool results."""

import math
import re

from app.agent.response_guard import detect_contradictions
from app.agent.response_quality import detect_language

# ---------------------------------------------------------------------
# Validate safe technical identifiers
# ---------------------------------------------------------------------

def _identifier(value: object) -> str | None:
    """Keep only short, safe technical identifiers."""

    if (
        isinstance(value, str)
        and re.fullmatch(r"[A-Za-z0-9_-]{1,80}", value)
    ):
        return value

    return None


# ---------------------------------------------------------------------
# Format valid percentages
# ---------------------------------------------------------------------

def _percentage(value: object) -> str | None:
    """Format valid percentages."""

    if (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and 0 <= value <= 100
    ):
        return f"{value:g} %"

    return None


# ---------------------------------------------------------------------
# Compose a grounded and secure agent answer
# ---------------------------------------------------------------------

def compose_grounded_answer(
    question: str,
    generated_answer: str,
    tool_results: list[dict],
) -> str:
    """Return grounded facts and suppress unsafe model claims."""

    # -------------------------------------------------------------
    # Detect contradictions between the generated answer
    # and verified tool results.
    # -------------------------------------------------------------

    issues = detect_contradictions(
        generated_answer,
        tool_results,
    )

    # -------------------------------------------------------------
    # Detect the user's language.
    # -------------------------------------------------------------

    french_question = (
        detect_language(question) == "fr"
    )

    # -------------------------------------------------------------
    # Non-French requests
    #
    # Preserve the existing behavior for non-French requests,
    # except unsupported ticket actions.
    # -------------------------------------------------------------

    if not french_question:

        if "UNVERIFIED_TICKET_ACTION" in issues:
            return (
                "No ticket was created or approved by this "
                "agent. Human authorization is required."
            )

        return generated_answer

    # -------------------------------------------------------------
    # Store verified facts derived from successful tools only.
    # -------------------------------------------------------------

    facts: list[str] = []

    proposal_only = False

    # -------------------------------------------------------------
    # Process verified tool results
    # -------------------------------------------------------------

    for result in tool_results:

        # Ignore failed tools.
        if result.get("ok") is not True:
            continue

        name = result.get("tool")
        data = result.get("data")

        # =========================================================
        # Tool 1: get_pipeline_status
        # =========================================================

        if (
            name == "get_pipeline_status"
            and isinstance(data, dict)
        ):

            pipeline_id = _identifier(
                data.get("pipeline_id")
            )

            status = data.get("status")

            status_fr = {
                "FAILED": "en échec",
                "SUCCESS": "réussi",
                "RUNNING": "en cours",
            }

            if pipeline_id and status in status_fr:
                facts.append(
                    f"Le pipeline {pipeline_id} est "
                    f"{status_fr[status]} "
                    f"(statut {status})."
                )

            error_code = _identifier(
                data.get("error_code")
            )

            if error_code:
                facts.append(
                    f"Code d'erreur : {error_code}."
                )

        # =========================================================
        # Tool 2: get_model_metrics
        # =========================================================

        elif (
            name == "get_model_metrics"
            and isinstance(data, dict)
        ):

            model_id = _identifier(
                data.get("model_id")
            )

            if model_id:
                facts.append(
                    f"Le modèle analysé est {model_id}."
                )

            error_rate = _percentage(
                data.get("error_rate_pct")
            )

            invalid_rate = _percentage(
                data.get("invalid_input_rate_pct")
            )

            if error_rate:
                facts.append(
                    f"Taux d'erreur : {error_rate}."
                )

            if invalid_rate:
                facts.append(
                    "Taux d'entrées invalides : "
                    f"{invalid_rate}."
                )

        # =========================================================
        # Tool 3: search_runbook
        # =========================================================

        elif (
            name == "search_runbook"
            and isinstance(data, list)
        ):

            # Limit the number of displayed runbooks.
            for runbook in data[:3]:

                if not isinstance(runbook, dict):
                    continue

                runbook_id = _identifier(
                    runbook.get("runbook_id")
                )

                if runbook_id:
                    facts.append(
                        f"Procédure consultée : {runbook_id}."
                    )

                # ---------------------------------------------
                # Human escalation safeguard
                #
                # An explicit approval requirement from
                # verified runbook data must be mentioned
                # even when the model omits it.
                # ---------------------------------------------

                if (
                    runbook.get("human_approval_required")
                    is True
                ):
                    facts.append(
                        "La procédure consultée indique "
                        "qu'une validation humaine "
                        "est requise."
                    )

        # =========================================================
        # Tool 4: prepare_incident_ticket
        # =========================================================

        elif (
            name == "prepare_incident_ticket"
            and isinstance(data, dict)
            and data.get("status") == "PROPOSAL_ONLY"
            and data.get("ticket_created") is False
            and data.get("human_approval_required") is True
        ):

            proposal_only = True

            incident_id = _identifier(
                data.get("incident_id")
            )

            if incident_id:
                facts.append(
                    f"Pour l'incident {incident_id}, "
                    "seule une proposition de ticket "
                    "a été préparée."
                )

            facts.append(
                "Aucun ticket n'a été créé ni approuvé "
                "par cet agent. Une validation humaine "
                "est nécessaire."
            )

    # -------------------------------------------------------------
    # Build the verified facts section.
    # -------------------------------------------------------------

    verified_section = ""

    if facts:
        verified_section = (
            "Faits vérifiés (données simulées) :\n"
            + "\n".join(
                f"- {fact}"
                for fact in facts
            )
        )

    # =============================================================
    # SECURITY RULE 1
    #
    # Never allow free-form LLM text to claim that a proposed
    # incident ticket has been created or approved.
    # =============================================================

    if proposal_only:
        return (
            verified_section
            + "\n\nLa réponse libre du modèle n'est pas "
            "reprise pour cette proposition de ticket. "
            "Toute approbation nécessite une intervention "
            "humaine distincte."
        )

    # =============================================================
    # SECURITY RULE 2
    #
    # Reject unsupported ticket creation or approval claims.
    # This protection also applies when no tool succeeded.
    # =============================================================

    if "UNVERIFIED_TICKET_ACTION" in issues:

        safe_message = (
            "Aucune création ni approbation de ticket "
            "n'a été exécutée par cet agent. "
            "Une validation humaine est requise."
        )

        if verified_section:
            return (
                verified_section
                + "\n\n"
                + safe_message
            )

        return safe_message

    # =============================================================
    # SECURITY RULE 3
    #
    # Hide generated analysis when contradictions are detected.
    # =============================================================

    if issues:

        warning = (
            "L'analyse générée a été masquée car "
            "une contradiction potentielle a été détectée."
        )

        if verified_section:
            return (
                verified_section
                + "\n\n"
                + warning
            )

        return warning

    # =============================================================
    # SECURITY RULE 4
    #
    # No verified facts available.
    #
    # Do not return an English answer to a French question.
    # Use a deterministic French response for ticket requests.
    # =============================================================

    if not facts:

        # Preserve valid French responses.
        if detect_language(generated_answer) == "fr":
            return generated_answer

        # Ticket-related questions get a safe French fallback.
        if re.search(
            r"ticket|approuv|approb",
            question,
            flags=re.IGNORECASE,
        ):
            return (
                "Cet agent ne peut ni créer ni approuver "
                "de ticket. Aucune action de ce type "
                "n'a été exécutée par cet agent. "
                "Une validation humaine est nécessaire."
            )

        # General fallback when language is not confirmed.
        return (
            "La réponse générée n'a pas été reprise : "
            "son respect du français n'a pas été confirmé."
        )

    # =============================================================
    # SECURITY RULE 5
    #
    # Add free-form generated analysis only when:
    # - Verified facts are available.
    # - No contradiction was detected.
    # - The answer is confidently detected as French.
    # =============================================================

    if detect_language(generated_answer) == "fr":

        return (
            verified_section
            + "\n\nAnalyse générée par le modèle "
            "(à vérifier) :\n"
            + generated_answer
        )

    # =============================================================
    # SECURITY RULE 6
    #
    # If language detection fails, preserve verified facts
    # and reject the generated analysis.
    # =============================================================

    return (
        verified_section
        + "\n\nLa synthèse générée n'a pas été "
        "reprise : son respect du français "
        "n'a pas été confirmé."
    )
