# OpsGuard AI — Simulated MLOps Execution Logs

## Purpose and provenance

This is a **synthetic journal generator**, not an ETL engine, Airflow, MLflow,
Kubernetes or a production log collector. It creates files that resemble MLOps
execution logs, and the agent diagnoses their **validated, structured metadata**.
The code does **not execute pipelines** or infer events from live infrastructure.

The previous `data/pipelines.json` snapshot and the new journal history are
**independent**. Their statuses may disagree; that is intentional. Never present
one as a current measurement of the other.

## Data flow

1. Streamlit, or the command-line script, selects a known `pipeline_id` and one
   of five allowlisted scenarios.
2. `app.simulation.log_generator` writes a local UTF-8 JSONL journal under
   `logs/simulated_pipelines/`, using a random `SIM-...` run identifier.
3. `app.simulation.log_store` reads the file with bounded size/event counts,
   validated identifiers and schema. It filters out raw `message` strings from
   the agent-facing result.
4. `get_pipeline_logs` is registered as the fifth **read-only** agent tool.
5. When a user explicitly requests journal analysis for a known pipeline, the
   orchestrator uses `get_pipeline_logs`, then `search_runbook` if an error code
   exists. The response is assembled deterministically and quotes line numbers
   / event types. No Ollama call is made by this *particular* diagnostic route.
6. The Streamlit 'Logs simulés' page shows the full synthetic journal, its
   structured events and the diagnostic with a trace ID.

## Scenarios

| Code | Outcome | Runbook |
|---|---|---|
| `success` | `SUCCESS` | No error |
| `schema_error` | `FAILED`, `SCHEMA_VALIDATION_ERROR` | `RB-001` |
| `missing_values` | `WARNING`, `MISSING_VALUES` | `RB-003` |
| `high_latency` | `WARNING`, `HIGH_LATENCY` | `RB-002` |
| `unknown_error` | `FAILED`, `RESOURCE_CONTENTION_XYZ_999` | None, report `NOT_FOUND` |

The volume, timing and run identifiers vary with each generation. **Those
numbers are simulated**, not measurements from processing actual records.

## Safety and operational limitations

- Generated files remain under a fixed application directory and are ignored
  by Git because the existing `.gitignore` excludes `logs/`.
- Only pipeline IDs already present in `data/pipelines.json` are supported.
- The tool accepts `run_id='latest'` or a strict `SIM-<12 hex characters>`.
- Logs are read-only for the agent. The simulation launcher is **not exposed
  to Qwen3 as a tool**; only a human action in Streamlit/CLI can create a run.
- File content is treated as untrusted data. The agent receives only event
  categories, bounded counters, statuses and known error codes, **not text
  messages**. Line numbers allow the user to confirm evidence in the UI.
- Oversize/malformed journals and symlinked run files are rejected.
- The generator keeps a maximum of 50 runs per pipeline (local demo retention).
- No authentication is implemented; keep Streamlit bound to `127.0.0.1`.
- No log streaming or background daemon is implemented. No automatic actions
  against external infrastructure are authorized.
- This is not causal diagnosis of a real incident. The simulated scenario
  labels are ground truth *only within the demo generator*.

## Extension path

For genuine pipeline monitoring, replace the synthetic generator with a collector
for actual execution events (Python ETL, Airflow, Prefect, etc.) while keeping
strict source allowlists, bounded ingestion, schema validation and evidence
references. Add durable storage and data-source authenticity checks before
any production deployment. The LLM should not receive arbitrary raw log text.
