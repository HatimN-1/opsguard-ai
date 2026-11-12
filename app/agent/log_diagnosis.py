"""Deterministic, evidence-grounded diagnosis of simulated MLOps journals."""

from typing import Any

EVENT_LABELS = {
    "RUN_STARTED": "démarrage de la simulation",
    "DATA_EXTRACTED": "extraction simulée",
    "SCHEMA_VALIDATED": "validation du schéma simulé",
    "DATA_VALIDATED": "validation des données simulées",
    "DATA_LOADED": "chargement simulé",
    "SCHEMA_MISMATCH": "incompatibilité de schéma signalée",
    "MISSING_VALUES_DETECTED": "valeurs manquantes détectées",
    "HIGH_LATENCY_DETECTED": "latence élevée signalée",
    "UNKNOWN_ERROR_DETECTED": "erreur non documentée signalée",
    "RUN_FINISHED": "fin de simulation",
}


def compose_simulated_log_answer(data: dict[str, Any], runbook_result: dict | None) -> str:
    """Explain only validated event codes, counts and verified runbook metadata.

    The caller passes a result produced by the bounded, allowlisted log reader.
    No raw log line or free-form LLM output is incorporated into the answer.
    """
    lines = [
        "**Diagnostic des journaux SIMULÉS** — aucune exécution ETL réelle.",
        f"- Pipeline : `{data['pipeline_id']}`.",
        f"- Exécution : `{data['run_id']}`.",
        f"- État enregistré : **{data['status']}**.",
        (
    f"- Volume simulé : {data['records_processed']} enregistrements, "
    f"dont {data['invalid_records']} invalides."
),
        f"- Durée simulée : {data['duration_ms']} ms.",
    ]
    code = data.get("error_code")
    if code:
        lines.append(f"- Code d'erreur observé : `{code}`.")
    else:
        lines.append("- Aucun code d'erreur signalé dans cette simulation.")

    observed = [
        f"L{event['line']} : " + EVENT_LABELS[event["event"]]
        + f" (étape {event['step']})"
        + (f" ; colonne {event['field']}" if event.get("field") else "")
        for event in data.get("events", [])
        if event.get("level") in {"WARNING", "ERROR"}
        and event.get("event") != "RUN_FINISHED"
        and event.get("event") in EVENT_LABELS
    ]
    if observed:
        lines.append("\n**Événements significatifs :**")
        lines.extend(f"- {event}." for event in observed)

    if code and runbook_result is not None:
        if runbook_result.get("ok") is True:
            runbooks = runbook_result.get("data", [])
            if isinstance(runbooks, list) and runbooks:
                book = runbooks[0]
                if isinstance(book, dict):
                    identifier = book.get("runbook_id")
                    if isinstance(identifier, str) and identifier.startswith("RB-"):
                        lines.append(f"\n**Procédure documentée :** `{identifier}`.")
                    if book.get("human_approval_required") is True:
                        lines.append("Une validation humaine est requise par ce runbook.")
                    else:
                        lines.append("Consulter les étapes du runbook avant toute intervention.")
        elif runbook_result.get("error") == "NOT_FOUND":
            lines.append(
                "\n**Aucun runbook disponible pour ce code.** "
                "La cause exacte et la résolution ne sont pas vérifiées. "
                "Une investigation humaine est recommandée."
            )
        else:
            lines.append(
                "\n**Recherche de runbook indisponible.** "
                "Aucune procédure vérifiée ne peut être présentée."
            )
    elif not code:
        lines.append("\nAucune anomalie codifiée ne nécessite une recherche de runbook.")

    lines.append(
        "\n**Limite :** ces événements sont issus d'un générateur contrôlé, "
        "pas de journaux provenant d'un système de production. "
        "Aucune réparation ou approbation automatique n'a été effectuée."
    )
    return "\n".join(lines)
