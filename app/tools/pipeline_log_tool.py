"""Read-only tool for bounded simulated pipeline journals."""

from app.simulation.log_store import read_simulated_run


def get_pipeline_logs(pipeline_id: str, run_id: str = "latest") -> dict | None:
    """Return structured evidence, never raw log messages or arbitrary files."""
    return read_simulated_run(pipeline_id, run_id)
