"""Evidence-only business answers. No LLM required for statuses or run comparisons.

Every row comes from the read-only ADFPipelineRun metadata (not activity rows).
The 12-company catalogue is fixed. Root causes are never claimed as confirmed.
"""

from collections import Counter, defaultdict

from app.adf_monitor.business_catalog import known_business_ids


def build_business_report(plan: dict, facts: dict) -> dict:
    """Return typed rows and a precise French summary for a business question."""
    kind = plan.get("intent", "INCIDENT_DIAGNOSIS")
    selected = plan.get("pipeline_id")
    runs = [r for r in facts.get("run_records", [])
            if not selected or r["pipeline_name"] == selected]
    if kind == "LATEST_STATUS":
        latest = {r["pipeline_name"]: r for r in facts.get("latest_pipeline_runs", [])}
        rows = []
        for pid in known_business_ids():
            run = latest.get(pid)
            rows.append({
                "pipeline_name": pid,
                "run_id": run["run_id"] if run else "—",
                "timestamp_utc": run["timestamp_utc"] if run else "—",
                "status": run["status"] if run else "NO_TELEMETRY",
                "error_code": run["error_code"] if run and run["error_code"] else "—",
            })
        failed = sum(r["status"] == "Failed" for r in rows)
        succeeded = sum(r["status"] == "Succeeded" for r in rows)
        other = sum(r["status"] not in {"Failed", "Succeeded", "NO_TELEMETRY"}
                    for r in rows)
        unknown = sum(r["status"] == "NO_TELEMETRY" for r in rows)
        return {
            "kind": kind, "title": "Dernière exécution des douze pipelines",
            "summary": (
                f"Dernier statut observé par pipeline : {failed} en échec, "
                f"{succeeded} réussi(s), {other} autre(s) statut(s), "
                f"{unknown} sans télémétrie "
                "dans la période. Cette vue ne compte pas les incidents historiques."
            ), "rows": rows,
        }
    if kind in {"RUN_COMPARISON", "RECURRENCE"}:
        limit = plan.get("run_limit", 4) if kind == "RUN_COMPARISON" else 20
        rows = [{
            "pipeline_name": r["pipeline_name"], "run_id": r["run_id"],
            "timestamp_utc": r["timestamp_utc"], "status": r["status"],
            "error_code": r["error_code"] or "—",
        } for r in runs[:limit]]
        by_code: dict[str, set[str]] = defaultdict(set)
        for r in runs:
            if r["status"] == "Failed" and r["error_code"]:
                by_code[r["error_code"]].add(r["run_id"])
        repeated = {code: len(ids) for code, ids in by_code.items() if len(ids) >= 2}
        code_counts = dict(Counter(r["error_code"] for r in runs if r["error_code"]))
        focus_codes = plan.get("focus_error_codes") or []
        if focus_codes:
            code_counts = {code: code_counts.get(code, 0) for code in focus_codes}
            repeated = {code: n for code, n in repeated.items() if code in focus_codes}
        recurrence = (
            "Récurrence observée de code(s) sur des Run IDs distincts : "
            + ", ".join(f"{code} ({count} runs)" for code, count in sorted(repeated.items()))
            if repeated else "Aucun code répété sur au moins deux runs en échec dans les données consultées."
        )
        return {
            "kind": kind, "title": "Historique et comparaison des exécutions",
            "summary": (f"{len(rows)} exécution(s) listée(s) de la plus récente à la plus ancienne. "
                        + recurrence + " Une récurrence de code ne confirme pas la même cause racine."),
            "rows": rows, "recurrence_by_code": repeated,
            "failed_runs_by_code": code_counts,
            "coverage_note": (
                "Comparaison calculée à partir des Run IDs, sans doublons d'activités. "
                "Historique borné aux 200 derniers Run IDs de la sélection."
            ),
        }
    errors = facts.get("errors", [])
    unique = {(e["pipeline_name"], e["run_id"]) for e in errors}
    rows = [{
        "pipeline_name": e["pipeline_name"], "run_id": e["run_id"],
        "error_code": e["error_code"], "event_occurrences": e["occurrences"],
    } for e in errors]
    return {
        "kind": kind, "title": "Investigation des incidents",
        "summary": (
            f"{len(unique)} exécution(s) distincte(s) présentant un code d'erreur "
            "dans la sélection. Les codes observés ne prouvent pas à eux seuls "
            "la cause racine ; une vérification humaine reste nécessaire."
        ) if rows else "Aucun code d'erreur structuré dans la sélection consultée.",
        "rows": rows,
    }
