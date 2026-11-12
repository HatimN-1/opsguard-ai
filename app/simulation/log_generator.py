"""Generate realistic-looking but explicitly SIMULATED MLOps execution logs.

No ETL pipeline, remote host, model, network service or system command is run.
Only a small set of predefined scenarios can be generated.
"""

import json
import os
import secrets
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.simulation.log_store import (
    ALLOWED_SCENARIOS,
    MAX_LOG_BYTES,
    SIMULATED_LOG_DIR,
    is_known_pipeline,
    read_simulated_run,
)


def generate_simulated_run(
    pipeline_id: str,
    scenario: str,
    *,
    directory: Path | None = None,
) -> dict:
    """Safely persist one bounded scenario; never run external pipelines."""
    if not is_known_pipeline(pipeline_id):
        raise ValueError("Pipeline de démonstration inconnu.")
    if not isinstance(scenario, str) or scenario not in ALLOWED_SCENARIOS:
        raise ValueError("Scénario non autorisé.")

    root = directory if directory is not None else SIMULATED_LOG_DIR
    root.mkdir(parents=True, exist_ok=True)
    if root.is_symlink():
        raise ValueError("Le répertoire des logs ne doit pas être un lien symbolique.")

    run_id = "SIM-" + secrets.token_hex(6)
    base = datetime.now(UTC)
    records = 900 + secrets.randbelow(601)
    invalid = 0
    status = "SUCCESS"
    error_code = None
    duration = 50 + secrets.randbelow(100)
    entries: list[tuple[str, str, str, str, str | None]] = [
        ("INFO", "RUN_STARTED", "EXTRACT", "Simulation démarrée.", None),
        ("INFO", "DATA_EXTRACTED", "EXTRACT", f"{records} lignes simulées.", None),
    ]

    if scenario == "schema_error":
        status, error_code, invalid = "FAILED", "SCHEMA_VALIDATION_ERROR", records
        entries.append((
            "ERROR", "SCHEMA_MISMATCH", "TRANSFORM",
            "Champ obligatoire customer_id absent dans le scénario simulé.", error_code,
        ))
    elif scenario == "missing_values":
        status, error_code = "WARNING", "MISSING_VALUES"
        invalid = 20 + secrets.randbelow(100)
        entries.extend([
            ("WARNING", "MISSING_VALUES_DETECTED", "TRANSFORM",
             f"{invalid} enregistrements simulés contiennent des valeurs manquantes.",
             error_code),
            ("INFO", "DATA_LOADED", "LOAD",
             "Chargement simulé avec exclusions de lignes invalides.", None),
        ])
    elif scenario == "high_latency":
        status, error_code = "WARNING", "HIGH_LATENCY"
        duration = 1800 + secrets.randbelow(1200)
        entries.extend([
            ("WARNING", "HIGH_LATENCY_DETECTED", "MONITOR",
             "Latence élevée simulée pendant l'étape de chargement.", error_code),
            ("INFO", "DATA_LOADED", "LOAD", "Chargement simulé terminé.", None),
        ])
    elif scenario == "unknown_error":
        status, error_code = "FAILED", "RESOURCE_CONTENTION_XYZ_999"
        entries.append((
            "ERROR", "UNKNOWN_ERROR_DETECTED", "TRANSFORM",
            "Erreur synthétique inconnue : origine non diagnostiquée.", error_code,
        ))
    else:
        entries.extend([
            ("INFO", "SCHEMA_VALIDATED", "TRANSFORM", "Schéma simulé conforme.", None),
            ("INFO", "DATA_LOADED", "LOAD", "Chargement simulé terminé.", None),
        ])

    entries.append((
        "INFO" if status == "SUCCESS" else "WARNING" if status == "WARNING" else "ERROR",
        "RUN_FINISHED", "MONITOR", f"Simulation terminée : {status}.", error_code,
    ))

    events = []
    for index, (level, event, step, message, code) in enumerate(entries):
        row = {
            "run_id": run_id,
            "pipeline_id": pipeline_id,
            "timestamp_utc": (base + timedelta(milliseconds=index * 25)).isoformat(),
            "level": level,
            "event": event,
            "step": step,
            "message": message,
        }
        if code:
            row["error_code"] = code
        if event == "SCHEMA_MISMATCH":
            row["field"] = "customer_id"
        if event == "RUN_FINISHED":
            row.update({
                "status": status,
                "scenario": scenario,
                "records_processed": records,
                "invalid_records": invalid,
                "duration_ms": duration,
            })
        events.append(row)

    content = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in events)
    if len(content.encode("utf-8")) > MAX_LOG_BYTES:
        raise ValueError("Le journal dépasse la limite autorisée.")

    destination = root / f"{pipeline_id}__{run_id}.jsonl"
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=root, prefix=".simulation-", suffix=".tmp",
            delete=False,
        ) as handle:
            temp_name = handle.name
            handle.write(content)
        os.replace(temp_name, destination)
    finally:
        if temp_name is not None:
            Path(temp_name).unlink(missing_ok=True)

    result = read_simulated_run(pipeline_id, run_id, directory=root)
    if result is None:
        raise RuntimeError("Le journal créé n'a pas pu être validé.")

    # Keep a small, bounded demo history per pipeline (not production retention).
    # Only files with our validated prefix/suffix are eligible for pruning.
    candidates = sorted(
        (
            path for path in root.glob(f"{pipeline_id}__SIM-*.jsonl")
            if path.is_file() and not path.is_symlink()
        ),
        key=lambda path: path.stat().st_mtime_ns,
        reverse=True,
    )
    for old_file in candidates[50:]:
        old_file.unlink(missing_ok=True)
    return result
