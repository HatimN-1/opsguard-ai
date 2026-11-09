
"""Build safe French answers grounded in successful tool results."""

import math
import re

from app.agent.response_guard import detect_contradictions
from app.agent.response_quality import detect_language


def _identifier(value: object) -> str | None:
    """Keep only short, safe technical identifiers."""

    if (
        isinstance(value, str)
        and re.fullmatch(r"[A-Za-z0-9_-]{1,80}", value)
    ):
        return value

    return None


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


def compose_grounded_answer(
    question: str,
    generated_answer: str,
    tool_results: list[dict],
) -> str:
    """Return grounded facts and suppress unsafe model claims."""

    # Check contradictions even when no tool succeeded.
    issues = detect_contradictions(
        generated_answer,
        tool_results,
    )

    french_question = detect_language(question) == "fr"

    # Preserve responses to non-French requests,
    # except detected unsupported ticket actions.
    if not french_question:
        if "UNVERIFIED_TICKET_ACTION" in issues:
            return (
                "No ticket was created or approved by this "
                "agent. Human authorization is required."
            )

        return generated_answer

    facts: list[str] = []
    proposal_only = False

    for result in tool_results:
        # Only successful tool results can provide facts.
        if result.get("ok") is not True:
            continue

        name = result.get("tool")
        data = result.get("data")

        # --------------------------------------------------
        # Pipeline facts
        # --------------------------------------------------

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

        # --------------------------------------------------
        # Machine learning monitoring facts
        # --------------------------------------------------

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

        # --------------------------------------------------
        # Runbook facts
        # --------------------------------------------------

        elif (
            name == "search_runbook"
            and isinstance(data, list)
        ):
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

        # --------------------------------------------------
        # Incident ticket proposal
        #
        # A proposal is NOT a creation or approval.
        # All conditions are combined to avoid SIM102.
        # --------------------------------------------------

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

    # ------------------------------------------------------
    # Build the verified facts section.
    # ------------------------------------------------------

    verified_section = ""

    if facts:
        verified_section = (
            "Faits vérifiés (données simulées) :\n"
            + "\n".join(
                f"- {fact}"
                for fact in facts
            )
        )

    # ------------------------------------------------------
    # Security rule 1:
    # Never use free-form model claims to describe the
    # execution outcome of an incident ticket proposal.
    # ------------------------------------------------------

    if proposal_only:
        return (
            verified_section
            + "\n\nLa réponse libre du modèle n'est pas "
            "reprise pour cette proposition de ticket. "
            "Toute approbation nécessite une intervention "
            "humaine distincte."
        )

    # ------------------------------------------------------
    # Security rule 2:
    # Block unsupported ticket creation or approval claims,
    # including when no tools were executed successfully.
    # ------------------------------------------------------

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

    # ------------------------------------------------------
    # Security rule 3:
    # Hide generated analysis if another potential
    # contradiction was detected.
    # ------------------------------------------------------

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

    # ------------------------------------------------------
    # No verified facts and no detected contradiction.
    # ------------------------------------------------------

    if not facts:
        return generated_answer

    # ------------------------------------------------------
    # Add the generated analysis only if it is detected
    # as French and no contradiction was found.
    # ------------------------------------------------------

    if detect_language(generated_answer) == "fr":
        return (
            verified_section
            + "\n\nAnalyse générée par le modèle "
            "(à vérifier) :\n"
            + generated_answer
        )

    # ------------------------------------------------------
    # Preserve verified facts if the model's generated
    # response is not confidently detected as French.
    # ------------------------------------------------------

    return (
        verified_section
        + "\n\nLa synthèse générée n'a pas été "
        "reprise : son respect du français "
        "n'a pas été confirmé."
    )
