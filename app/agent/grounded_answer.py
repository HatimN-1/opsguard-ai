
"""Build French answers grounded in successful tool results."""

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
    """Format a valid percentage without unnecessary zeros."""

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
    """Separate verified tool facts from generated analysis."""

    if detect_language(question) != "fr":
        return generated_answer

    facts = []

    for result in tool_results:
        if result.get("ok") is not True:
            continue

        name = result.get("tool")
        data = result.get("data")

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
                        "Procédure consultée : "
                        f"{runbook_id}."
                    )

    if not facts:
        return generated_answer

    verified_section = (
        "Faits vérifiés (données simulées) :\n"
        + "\n".join(f"- {fact}" for fact in facts)
    )

    
    if detect_language(generated_answer) == "fr":
        issues = detect_contradictions(
            generated_answer,
            tool_results,
        )

        if issues:
            return (
                verified_section
                + "\n\nL'analyse générée a été masquée "
                "car une contradiction potentielle "
                "a été détectée."
            )

        return (
            verified_section
            + "\n\nAnalyse générée par le modèle "
            "(à vérifier) :\n"
            + generated_answer
        )


    return (
        verified_section
        + "\n\nLa synthèse générée n'a pas été "
        "reprise : son respect du français "
        "n'a pas été confirmé."
    )
