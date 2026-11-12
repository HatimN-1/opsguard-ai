"""Evidence-based, cited ADF investigations from tool results.

Free-form LLM output cannot override a source event or forge a documentation
reference. Doc retrieval is lexical over a Microsoft Learn grounded index.
"""

from collections import Counter
from typing import Any


def compose_adf_investigation(log_result: dict, doc_results: list[dict]) -> str:
    """Build a French report from selected log evidence and retrieved docs."""
    data: dict[str, Any] = log_result.get("data", {})
    if log_result.get("ok") is not True or not isinstance(data, dict):
        return (
            "La recherche des journaux Azure Data Factory a échoué. "
            "Aucun diagnostic ne peut être confirmé sans données vérifiées."
        )
    source = data.get("source", "SOURCE_INCONNUE")
    count = data.get("matching_events", 0)
    lines = [
        "### Investigation Azure Data Factory",
        f"**Source :** `{source}`. ",
        f"**Événements pertinents trouvés :** {count} ",
        f"(**{data.get('returned_events', 0)}** affichés).",
    ]
    if data.get("simulation"):
        lines.append(
            "**Environnement de démonstration :** ces journaux sont SYNTHÉTIQUES, "
            "stockés dans un dossier externe au projet ; ils ne viennent pas d'Azure."
        )
    if data.get("pipeline_name"):
        lines.append(f"**Pipeline demandé :** `{data['pipeline_name']}`.")
    if data.get("run_id"):
        lines.append(f"**Exécution :** `{data['run_id']}`.")
    if not count:
        lines.append("Aucun événement correspondant aux filtres n'a été trouvé.")
        return "\n\n".join(lines)
    if data.get("truncated"):
        if data.get("coverage") == "COMPLETE_FILTERED_EXPORT":
            lines.append(
                "**Affichage limité :** seuls les événements les plus récents sont "
                "listés. Les totaux et anomalies sont calculés sur tous les "
                "événements filtrés de l'export externe."
            )
        else:
            lines.append(
                "**Attention :** l'extraction a été limitée ; une analyse "
                "plus complète peut nécessiter plusieurs requêtes."
            )
    lines.append(
        "**Détail des enregistrements :** "
        f"{data.get('pipeline_run_count', 0)} exécution(s) de pipeline, "
        f"{data.get('activity_run_count', 0)} exécution(s) d'activité."
    )
    totals = data.get("copy_metrics_total") or {}
    if totals.get("rowsRead") or totals.get("rowsCopied"):
        lines.append(
            "**Compteurs d'activités Copy (simulés) :** "
            f"{totals.get('rowsRead', 0)} lignes lues, "
            f"{totals.get('rowsCopied', 0)} lignes copiées. "
            "Ces compteurs ne représentent pas des lignes de logs."
        )
    state = data.get("status_counts") or {}
    lines.append(
        "**Statuts des événements (pipelines ET activités) :** "
        + ", ".join(f"{key} : {value}" for key, value in sorted(state.items()))
    )
    evidence = data.get("errors", [])[:8]
    if evidence:
        lines.append("\n**Anomalies détectées dans les événements :**")
        for err in evidence:
            lines.append(
                f"- Code `{err['error_code']}` sur `{err['pipeline_name']}` "
                f"(run `{err['run_id']}`, {err['occurrences']} événement(s))."
            )
    else:
        lines.append("Aucun code d'erreur structuré n'est présent dans la sélection.")

    corroboration = data.get("evidence_events", [])[:8]
    if corroboration:
        lines.append("\n**Événements justificatifs :**")
        for event in corroboration:
            activity = event.get("activity_name") or "(pipeline)"
            activity_type = event.get("activity_type") or "non renseigné"
            runtime = event.get("integration_runtime") or "non renseigné"
            lines.append(
                f"- `{event['timestamp_utc']}` | `{event['pipeline_name']}` "
                f"| run `{event['run_id']}` | activité `{activity}` "
                f"({activity_type}) | runtime `{runtime}` "
                f"| erreur `{event['error_code']}`."
            )

    matched = []
    for item in doc_results:
        if item.get("ok") is True:
            records = item.get("data", [])
            if isinstance(records, list):
                matched.extend(d for d in records if isinstance(d, dict))
    unique = {doc["doc_id"]: doc for doc in matched if "doc_id" in doc}
    documented_codes = {
        doc.get("matched_error_code")
        for doc in unique.values()
        if doc.get("matched_error_code")
    }
    for error in evidence:
        if error["error_code"] not in documented_codes:
            lines.append(
                f"**Code `{error['error_code']}` : aucune référence spécifique "
                "dans l'index Microsoft Learn local.** Investigation nécessaire."
            )
    if unique:
        lines.append("\n**Documentation Microsoft Learn retrouvée par recherche :**")
        for doc in list(unique.values())[:5]:
            lines.append(f"- **[{doc['doc_id']}]** {doc['title']} — {doc['url']}")
            lines.append(f"  - Contexte : {doc['summary_fr']}")
            for check in doc.get("checks_fr", [])[:3]:
                lines.append(f"  - Vérification documentée : {check}")
    elif evidence:
        lines.append(
            "\n**Aucune référence spécifique retrouvée dans l'index documentaire.** "
            "Ce code ne permet pas d'établir une cause certaine. "
            "Consulter les équipes d'exploitation et la documentation officielle."
        )
    lines.append(
        "\n**Séparation preuve / hypothèse :** un code d'erreur observé est un fait "
        "du journal ; la procédure Microsoft décrit des causes possibles à vérifier, "
        "pas une preuve automatique de cause racine. Aucun pipeline n'a été modifié."
    )
    return "\n".join(lines)


def evidence_query(data: dict) -> list[str]:
    """Pick diverse error codes, not a fixed per-error response branch."""
    codes = Counter(
        error.get("error_code")
        for error in data.get("errors", [])
        if isinstance(error, dict) and error.get("error_code")
    )
    return [code for code, _ in codes.most_common(3)]
