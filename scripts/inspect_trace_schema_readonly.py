"""Audit read-only de la presence de champs observables dans les traces OpsGuard.

N'affiche jamais de valeurs d'arguments, de prompts, de reponses, de Run IDs,
de traces, ni de noms de champs arbitraires. Ne modifie pas les traces.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path

FIELD_CANDIDATES = (
    "selection_source", "selection_reason", "selection_category",
    "tool_selection_reason", "tool_selection_source", "source", "reason",
    "duration_ms", "latency_ms", "elapsed_ms", "tool_duration_ms",
)
EVENT_TYPES = ("TOOL_REQUESTED", "TOOL_COMPLETED")
DURATION_KEYS = ("duration_ms", "latency_ms", "elapsed_ms", "tool_duration_ms")
SELECTION_KEYS = (
    "selection_source", "selection_reason", "selection_category",
    "tool_selection_reason", "tool_selection_source", "source", "reason",
)


def field_kind(value: object) -> str:
    if value is None:
        return "null"
    if type(value) is bool:
        return "boolean"
    if isinstance(value, (int, float)):
        return "nonnegative_finite_number" if math.isfinite(value) and value >= 0 else "other_number"
    if isinstance(value, str):
        return "nonempty_string" if value.strip() else "empty_string"
    return "other_type"


def inspect(path: Path) -> dict:
    counts = Counter()
    fields = Counter()
    by_chunk = Counter()
    examples: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8-sig") as stream:
        for line_num, row in enumerate(stream, start=1):
            if not row.strip():
                continue
            counts["records"] += 1
            try:
                record = json.loads(row)
            except (ValueError, TypeError):
                counts["invalid_json_rows"] += 1
                continue
            if not isinstance(record, dict):
                counts["invalid_object_rows"] += 1
                continue
            events = record.get("events")
            if not isinstance(events, list):
                counts["legacy_without_events"] += 1
                continue
            counts["records_with_events"] += 1
            chunk = "first_500_rows" if line_num <= 500 else "later_rows"
            for i, event in enumerate(events, start=1):
                if not isinstance(event, dict):
                    continue
                kind = event.get("event_type")
                if kind not in EVENT_TYPES:
                    continue
                counts[kind] += 1
                by_chunk[(chunk, kind)] += 1
                for field in FIELD_CANDIDATES:
                    if field in event:
                        fields[(kind, field, field_kind(event[field]))] += 1
                required = SELECTION_KEYS if kind == "TOOL_REQUESTED" else DURATION_KEYS
                if not any(key in event for key in required):
                    counts[f"{kind}_NO_CANDIDATE_FIELD"] += 1
                    by_chunk[(chunk, f"{kind}_NO_CANDIDATE_FIELD")] += 1
                    if len(examples) < 12:
                        examples.append({"line": line_num, "event_position": i, "event_type": kind})
                elif kind == "TOOL_REQUESTED" and not any(
                    field_kind(event.get(key)) == "nonempty_string" for key in required
                ):
                    counts["TOOL_REQUESTED_WITHOUT_VALID_SELECTION"] += 1
                elif kind == "TOOL_COMPLETED" and not any(
                    field_kind(event.get(key)) == "nonnegative_finite_number" for key in required
                ):
                    counts["TOOL_COMPLETED_WITHOUT_VALID_DURATION"] += 1
    return {
        "counts": dict(sorted(counts.items())),
        "candidate_field_presence_types": [
            {"event_type": ev, "field": field, "type": value_type, "count": n}
            for (ev, field, value_type), n in sorted(fields.items())
        ],
        "first_500_vs_later": [
            {"segment": seg, "event": key, "count": n}
            for (seg, key), n in sorted(by_chunk.items())
        ],
        "first_examples_metadata_only": examples,
        "limitation": "Presence de champs seulement ; ne remplace pas scripts.audit_project3_traces. Ne lit aucun texte d'outil.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("logs/agent_traces.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("outputs/trace_schema_report.json"))
    args = parser.parse_args()
    report = inspect(args.source)
    print("OpsGuard — verification des champs de chronologie (lecture seule)")
    for key, value in report["counts"].items():
        print(f"  {key}: {value}")
    print("Champs reconnus dans les evenements (comptes uniquement) :")
    for field in report["candidate_field_presence_types"]:
        print(f"  {field['event_type']} / {field['field']} / {field['type']}: {field['count']}")
    print("Par segment :")
    for part in report["first_500_vs_later"]:
        print(f"  {part['segment']} / {part['event']}: {part['count']}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Rapport de metadonnees : {args.output}")


if __name__ == "__main__":
    main()
