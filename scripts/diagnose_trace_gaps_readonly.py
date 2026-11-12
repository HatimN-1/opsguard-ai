"""Read-only, privacy-conscious diagnosis of OpsGuard tool timeline metadata.

Only operational categories are printed, never prompts, run ids, arguments,
responses, trace ids, or raw journal content. This script does not mutate logs.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path


def _valid_duration(value: object) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _safe_category(value: object, *, limit: int = 40) -> str:
    """Prevent unexpectedly detailed or secret strings from being printed."""
    if not isinstance(value, str) or not value:
        return "unavailable"
    allowed = {"deterministic", "policy_fallback", "llm", "evidence_plan",
               "guardrail", "manual", "system", "unknown"}
    return value if value in allowed and len(value) <= limit else "other"


def inspect(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"Journal introuvable : {path}")
    counts = Counter()
    problems: list[dict] = []
    grouped = Counter()
    with path.open("r", encoding="utf-8-sig") as handle:
        for number, raw in enumerate(handle, 1):
            if not raw.strip():
                continue
            counts["records"] += 1
            try:
                rec = json.loads(raw)
            except json.JSONDecodeError:
                counts["invalid_jsonl_rows"] += 1
                problems.append({"line": number, "problem": "INVALID_JSON_ROW"})
                continue
            if not isinstance(rec, dict):
                counts["invalid_record_rows"] += 1
                continue
            events = rec.get("events")
            if not isinstance(events, list):
                counts["legacy_without_events"] += 1
                continue
            counts["records_with_events"] += 1
            mode = _safe_category(rec.get("execution_mode"))
            for pos, event in enumerate(events, 1):
                if not isinstance(event, dict):
                    counts["invalid_event_objects"] += 1
                    continue
                event_type = event.get("event_type")
                if event_type not in ("TOOL_REQUESTED", "TOOL_COMPLETED"):
                    continue
                counts[event_type.lower()] += 1
                missing = []
                if event_type == "TOOL_REQUESTED" and not any(
                    isinstance(event.get(field), str) and event[field].strip()
                    for field in ("selection_source", "selection_reason", "selection_category")
                ):
                    missing.append("TOOL_SELECTION_UNDOCUMENTED")
                if event_type == "TOOL_COMPLETED" and not _valid_duration(
                    event.get("duration_ms", event.get("latency_ms"))
                ):
                    missing.append("TOOL_DURATION_MISSING")
                if not missing:
                    continue
                # Some audit implementations expect these metadata on both events.
                # The field presence is additionally surfaced for investigation.
                tool_name = event.get("tool")
                safe_tool = (tool_name if isinstance(tool_name, str)
                             and tool_name in {
                                 "query_adf_logs", "search_official_docs",
                                 "get_pipeline_status", "get_model_metrics",
                                 "search_runbook", "prepare_incident_ticket",
                                 "prepare_business_escalation", "get_pipeline_logs",
                             } else "other")
                for problem in missing:
                    counts[problem] += 1
                    grouped[(event_type, safe_tool, mode, problem)] += 1
                    problems.append({
                        "line": number,
                        "event_position": pos,
                        "event_type": event_type,
                        "tool_category": safe_tool,
                        "execution_mode_category": mode,
                        "problem": problem,
                    })
    return {
        "source": path.name,
        "counts": dict(counts),
        "groups": [
            {"event_type": k[0], "tool_category": k[1],
             "execution_mode_category": k[2], "problem": k[3], "count": v}
            for k, v in sorted(grouped.items())
        ],
        "first_80_findings": problems[:80],
        "findings_total": len(problems),
        "note": (
            "Diagnostic de champs observables, non identique au quality gate officiel. "
            "Les lignes sont indexées à partir de 1. Aucune trace n'a été modifiée."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("logs/agent_traces.jsonl"))
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    result = inspect(args.source)
    counts = result["counts"]
    print("OpsGuard AI — diagnostic des métadonnées de traces (lecture seule)")
    for key in ("records", "records_with_events", "legacy_without_events",
                "tool_requested", "tool_completed", "TOOL_SELECTION_UNDOCUMENTED",
                "TOOL_DURATION_MISSING", "invalid_jsonl_rows"):
        print(f"  {key}: {counts.get(key, 0)}")
    print("Répartition des écarts :")
    for item in result["groups"]:
        print("  {event_type} / {tool_category} / {execution_mode_category} : "
              "{problem} ({count})".format(**item))
    print("Premières lignes à consulter (métadonnées uniquement) :")
    for item in result["first_80_findings"][:30]:
        print(f"  ligne {item['line']} / événement {item['event_position']}: "
              f"{item['problem']}")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                               encoding="utf-8")
        print(f"Rapport anonymisé : {args.output}")


if __name__ == "__main__":
    main()
