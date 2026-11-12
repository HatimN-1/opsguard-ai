"""Safely patch the *current* OpsGuard orchestrator in place, preserving local edits.

Only instruments observable tool calls. Never rewrites old JSONL logs or LLM text.
Abort on unknown source layout, existing instrumentation, or unsupported observability API.
"""

from __future__ import annotations

import inspect
import os
from pathlib import Path

TARGET = Path('app/agent/orchestrator.py')
BACKUP = Path('outputs/backups/orchestrator_before_trace_metadata.py')
SENTINEL = 'def _trace_selection_category(source: str) -> str:'


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise ValueError(f'{label}: attendu 1 bloc, trouvé {count}; aucune modification appliquée')
    return source.replace(old, new, 1)


def transform(source: str) -> str:
    if SENTINEL in source:
        return source

    source = replace_once(
        source,
        'MAX_TOOL_CALLS = 4\n',
        '''MAX_TOOL_CALLS = 4


def _trace_selection_category(source: str) -> str:
    """Convert internal orchestration origins into approved audit categories."""
    return "llm_proposed" if source == "llm" else "policy"


def _trace_outcome_category(result: dict) -> str:
    """Keep the outcome operational, bounded, and free of tool output text."""
    if result.get("ok") is True:
        return "SUCCESS"
    if result.get("error") == "NOT_FOUND":
        return "NOT_FOUND"
    if result.get("error") == "INVALID_ARGUMENTS":
        return "INVALID_ARGUMENTS"
    return "TOOL_ERROR"
''',
        'category helpers',
    )
    source = replace_once(
        source,
        '''        error: str | None = None,
    ) -> None:
        if events is not None:
            events.append(
                make_agent_event(
                    event_type, step=step, tool=tool, ok=ok, error=error
                )
            )''',
        '''        error: str | None = None,
        selection_source: str | None = None,
        arguments: dict[str, Any] | None = None,
        duration_ms: float | None = None,
        outcome_category: str | None = None,
    ) -> None:
        if events is not None:
            events.append(
                make_agent_event(
                    event_type, step=step, tool=tool, ok=ok, error=error,
                    selection_source=selection_source, arguments=arguments,
                    duration_ms=duration_ms, outcome_category=outcome_category,
                )
            )''',
        'emit signature',
    )
    source = replace_once(
        source,
        '''        emit("TOOL_REQUESTED", step=step, tool=name)
        try:
            result = execute_tool(name, args)''',
        '''        emit(
            "TOOL_REQUESTED", step=step, tool=name,
            selection_source=_trace_selection_category(source), arguments=args,
        )
        tool_started = perf_counter()
        try:
            result = execute_tool(name, args)''',
        'normal tool request',
    )
    source = replace_once(
        source,
        '''                "error": "TOOL_EXECUTION_ERROR",
            }

        if tool_observer is not None:''',
        '''                "error": "TOOL_EXECUTION_ERROR",
            }
        tool_duration_ms = (perf_counter() - tool_started) * 1000

        if tool_observer is not None:''',
        'normal tool duration',
    )
    source = replace_once(
        source,
        '''        emit(
            "TOOL_COMPLETED",
            step=step,
            tool=name,
            ok=result.get("ok") is True,
            error=result.get("error"),
        )''',
        '''        emit(
            "TOOL_COMPLETED",
            step=step,
            tool=name,
            ok=result.get("ok") is True,
            error=result.get("error"),
            duration_ms=tool_duration_ms,
            outcome_category=_trace_outcome_category(result),
        )''',
        'normal tool completion',
    )
    source = replace_once(
        source,
        '''                if not isinstance(arguments, dict):
                    emit("TOOL_REQUESTED", step=step, tool=name)
                    result = {''',
        '''                if not isinstance(arguments, dict):
                    emit(
                        "TOOL_REQUESTED", step=step, tool=name,
                        selection_source="llm_proposed", arguments={},
                    )
                    invalid_started = perf_counter()
                    result = {''',
        'invalid-argument tool request',
    )
    source = replace_once(
        source,
        '''                        ok=False,
                        error="INVALID_ARGUMENTS",
                    )
                    if tool_observer is not None:''',
        '''                        ok=False,
                        error="INVALID_ARGUMENTS",
                        duration_ms=(perf_counter() - invalid_started) * 1000,
                        outcome_category="INVALID_ARGUMENTS",
                    )
                    if tool_observer is not None:''',
        'invalid-argument completion',
    )
    compile(source, str(TARGET), 'exec')
    return source


def main() -> int:
    if not TARGET.is_file():
        print('ERREUR: exécuter depuis le dossier racine opsguard-ai.')
        return 2
    # Do not modify code if the linked observability is not compatible.
    try:
        from app.agent.observability import make_agent_event
    except ImportError as exc:
        print(f'ERREUR: module observability non importable ({type(exc).__name__}).')
        return 2
    expected = {'selection_source', 'arguments', 'duration_ms', 'outcome_category'}
    if not expected.issubset(inspect.signature(make_agent_event).parameters):
        print('ERREUR: observability.py ne prend pas en charge les métadonnées requises.')
        return 2
    try:
        before = TARGET.read_text(encoding='utf-8')
        after = transform(before)
    except (OSError, UnicodeError, ValueError) as exc:
        print(f'ERREUR: code différent du modèle de correction ({exc}).')
        return 2
    if before == after:
        print('AUCUNE MODIFICATION : instrumenté précédemment.')
        return 0
    if BACKUP.exists():
        print(f'ERREUR: sauvegarde déjà présente : {BACKUP}. Aucune modification.')
        return 2
    try:
        BACKUP.parent.mkdir(parents=True, exist_ok=True)
        BACKUP.write_text(before, encoding='utf-8')
        temp = TARGET.with_name(TARGET.name + '.trace_fix_tmp')
        temp.write_text(after, encoding='utf-8')
        os.replace(temp, TARGET)
    except OSError as exc:
        print(f'ERREUR: écriture impossible ({type(exc).__name__}).')
        return 2
    print('PATCH APPLIQUÉ : orchestrator.py journalise motif et durée, deux chemins.')
    print(f'Sauvegarde : {BACKUP}')
    print('Aucune ancienne trace JSONL modifiée.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
