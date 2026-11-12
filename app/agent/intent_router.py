"""Small, explicit deterministic intents for OpsGuard AI.

This layer does not give the model new permissions. It makes predictable
questions reliable and supports a bounded fallback for missed tools.
"""

import json
import re
from pathlib import Path

from app.agent.response_quality import normalize_text

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _ids(filename: str, field: str) -> list[str]:
    """Read known simulated IDs; return no IDs on invalid source data."""
    try:
        with (DATA_DIR / filename).open(encoding="utf-8") as handle:
            items = json.load(handle)
        if not isinstance(items, list):
            return []
        return [
            item[field]
            for item in items
            if isinstance(item, dict)
            and isinstance(item.get(field), str)
            and re.fullmatch(r"[a-z0-9_]{3,80}", item[field])
        ]
    except (OSError, UnicodeError, ValueError, KeyError, TypeError):
        return []


def pipeline_ids() -> list[str]:
    """Known pipeline IDs, in display order."""
    return _ids("pipelines.json", "pipeline_id")


def mentioned_pipeline_id(question: str) -> str | None:
    """Identify an explicitly named, known pipeline."""
    for pipeline_id in pipeline_ids():
        if re.search(rf"(?<!\w){re.escape(pipeline_id)}(?!\w)", question, re.IGNORECASE):
            return pipeline_id
    return None


def mentioned_model_id(question: str) -> str | None:
    """Identify an explicitly named, known ML model."""
    for model_id in _ids("model_metrics.json", "model_id"):
        if re.search(rf"(?<!\w){re.escape(model_id)}(?!\w)", question, re.IGNORECASE):
            return model_id
    return None


def mentioned_incident_id(question: str) -> str | None:
    """Identify a validated, explicit incident ID."""
    match = re.search(r"\bINC-[0-9]{3}\b", question, re.IGNORECASE)
    return match.group(0).upper() if match else None


def wants_pipeline_overview(question: str) -> bool:
    """Detect a request for ALL pipelines, excluding a named pipeline."""
    normalized = normalize_text(question)
    if mentioned_pipeline_id(question):
        return False
    if not re.search(r"\bpipelines\b", normalized):
        return False
    return bool(
        re.search(
            r"\b(tous|toutes|ensemble|global|globale|complete|complet|"
            r"liste|lister|etats|statuts|all|every|overview|summary)\b",
            normalized,
        )
    )


def wants_runbook(question: str) -> bool:
    """Whether the user explicitly wants a runbook or procedure."""
    return bool(
        re.search(
            r"\b(runbooks?|procedures?|resolution|depannage|troubleshoot)\b",
            normalize_text(question),
        )
    )



def mentioned_error_code(question: str) -> str | None:
    """Extract one explicit uppercase error code, never a pipeline identifier.

    Only an error-code-shaped token is accepted; the orchestrator additionally
    requires a procedure request before executing a runbook lookup.
    """
    if not re.search(r"\b(erreur|error|code)\b", normalize_text(question)):
        return None

    codes = re.findall(
        r"(?<![A-Za-z0-9_])[A-Z][A-Z0-9_]{2,79}(?![A-Za-z0-9_])",
        question,
    )
    candidates = [code for code in codes if "_" in code]
    if len(candidates) == 1:
        return candidates[0]
    return None

def wants_pipeline_logs(question: str) -> bool:
    """Only explicit simulated execution-log requests enter this path."""
    normalized = normalize_text(question)
    return bool(re.search(
        r"\b(logs?|journaux|journal|traces? d.execution|execution log)\b",
        normalized,
    ))


def mentioned_log_run_id(question: str) -> str | None:
    """Optional validated execution identifier; arbitrary paths are rejected."""
    found = re.findall(r"(?<![\w-])SIM-[0-9a-f]{12}(?![\w-])", question)
    return found[0] if len(found) == 1 else None


def wants_proposal(question: str) -> bool:
    """A proposal request must not be confused with approval or creation."""
    normalized = normalize_text(question)
    return bool(
        mentioned_incident_id(question)
        and re.search(r"\b(proposition|propose|preparer|prepare)\b", normalized)
    )


def direct_answer(question: str) -> str | None:
    """Answer narrowly scoped FAQs without unreliable LLM speculation."""
    q = normalize_text(question).strip(" .!?;:\n\t")

    if q in {"bonjour", "bonsoir", "salut", "coucou", "hello", "hi"}:
        if q in {"hello", "hi"}:
            return "Hello! I'm OpsGuard AI. Ask me about pipelines, ML metrics or incidents."
        return (
            "Bonjour ! Je suis OpsGuard AI. Je peux diagnostiquer des "
            "pipelines, consulter des métriques ML, rechercher des runbooks "
            "et préparer des propositions de tickets. Que souhaites-tu analyser ?"
        )

    if re.search(r"\bmaroc\b", q) and re.search(
        r"(ou se trouve|ou est|situe|localisation)", q
    ):
        return (
            "Le Maroc se trouve en Afrique du Nord, au bord de l'océan "
            "Atlantique et de la mer Méditerranée. Pour OpsGuard AI, "
            "je peux aussi t'aider à analyser tes incidents MLOps."
        )

    if re.search(
        r"(fonctionnalit|capacite|que peux.tu faire|que peut faire|"
        r"quelles questions|quoi demander|que puis.je demander|"
        r"comment utiliser|a quoi sert|aide.moi a utiliser)",
        q,
    ):
        return (
            "OpsGuard AI propose cinq outils métier :\n"
            "- `get_pipeline_status` : consulter l'état d'un pipeline ETL ;\n"
            "- `get_model_metrics` : consulter les métriques d'un modèle ML ;\n"
            "- `search_runbook` : retrouver une procédure associée à une erreur ;\n"
            "- `prepare_incident_ticket` : préparer une proposition, sans créer de ticket ;\n"
            "- `get_pipeline_logs` : consulter des journaux d’exécution SIMULÉS et validés.\n\n"
            "Tu peux par exemple demander : « Analyse le pipeline etl_orders_daily "
            "et consulte son runbook », « Analyse fraud_detection_v1 » ou "
            "« Donne-moi l'état de tous les pipelines ». Les données sont simulées. "
            "La création et l'approbation de tickets sont réservées au workflow "
            "de démonstration distinct, avec intervention humaine."
        )

    if re.search(r"\b(composants?|architecture|modules?)\b", q) and re.search(
        r"\b(systeme|projet|opsguard|agent|application|ce|cet|ton)\b", q
    ):
        return (
            "OpsGuard AI comporte :\n"
            "1. Qwen3 1.7B, exécuté localement avec Ollama ;\n"
            "2. Un orchestrateur qui limite et supervise les appels ;\n"
            "3. Un registre de cinq outils validés avec Pydantic ;\n"
            "4. Des données MLOps simulées (pipelines, modèles, runbooks, incidents) ;\n"
            "5. Des réponses fondées sur les résultats d'outils ;\n"
            "6. Une interface Streamlit, une API FastAPI et des traces JSONL ;\n"
            "7. Un workflow de tickets avec approbation humaine simulée.\n\n"
            "L'agent ne déploie pas de modèles et ne modifie pas l'infrastructure."
        )

    if re.search(
        r"(comment (ca |cela )?marche|comment fonctionne|fonctionnement)", q
    ) and re.search(
        r"\b(systeme|projet|opsguard|agent|application|ce|cet)\b", q
    ):
        return (
            "Voici comment fonctionne OpsGuard AI :\n"
            "1. Tu poses une question dans Streamlit.\n"
            "2. Qwen3 sélectionne des outils MLOps lorsque nécessaire.\n"
            "3. Le registre valide leurs noms et leurs arguments Pydantic.\n"
            "4. Les outils consultent les données simulées.\n"
            "5. L'application construit une réponse à partir des faits vérifiés.\n"
            "6. Une trace horodatée permet d'observer les appels dans le dashboard.\n\n"
            "Les tickets sont uniquement proposés par l'agent : une approbation "
            "humaine distincte est nécessaire pour le workflow simulé."
        )

    return None


def wants_adf_investigation(question: str) -> bool:
    """Route only explicit Azure Data Factory monitoring requests."""
    normalized = normalize_text(question)
    return bool(re.search(
        r"\b(azure|adf|data factory|log analytics|adf_[a-z0-9_]+)\b",
        normalized,
    ))


def mentioned_adf_pipeline(question: str) -> str | None:
    """Extract an explicitly named pipeline without guessing from a generic request."""
    adf_names = re.findall(
        r"(?<!\w)adf_[a-z0-9_]{2,76}(?!\w)", question, re.IGNORECASE
    )
    if len(adf_names) == 1:
        return adf_names[0].lower()
    if len(adf_names) > 1:
        return None
    named = re.search(
        r"\b(?:pipeline|pipeline_name)\s+[`'\"]?"
        r"([A-Za-z][A-Za-z0-9_.-]{2,79})",
        question,
        flags=re.IGNORECASE,
    )
    if named is None:
        return None
    candidate = named.group(1)
    if normalize_text(candidate) in {
        "azure", "adf", "data", "tous", "all", "the", "dans", "avec",
        "et", "est", "pour", "unknown", "logs", "sans",
    }:
        return None
    return candidate


def mentioned_adf_lookback_hours(question: str) -> int:
    """Read a constrained duration from a question; default to 72 hours."""
    normalized = normalize_text(question)
    matches = re.findall(
        r"(?<!\w)(\d{1,3})\s*(heures?|hours?|h|jours?|days?|j)\b",
        normalized,
    )
    if len(matches) != 1:
        return 72
    number = int(matches[0][0])
    unit = matches[0][1]
    hours = number * 24 if unit.startswith(("j", "day")) else number
    return hours if 1 <= hours <= 720 else 72
