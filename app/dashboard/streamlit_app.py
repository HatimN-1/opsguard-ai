
"""Local, read-only observability dashboard for OpsGuard AI."""

import pandas as pd
import streamlit as st

from app.dashboard.data import (
    QUALITY_REPORT,
    TOOL_REPORT,
    filter_traces,
    load_report_summary,
    load_traces,
    summarize_traces,
)


def format_latency(latency_ms: float | None) -> str:
    """Display short latencies in ms and longer ones in seconds."""

    if latency_ms is None:
        return "—"

    if latency_ms < 1000:
        return f"{latency_ms:.2f} ms"

    return f"{latency_ms / 1000:.2f} s"


# ------------------------------------------------------------
# Page configuration
# ------------------------------------------------------------

st.set_page_config(
    page_title="OpsGuard AI - Observability",
    page_icon="📊",
    layout="wide",
)

st.title("OpsGuard AI — Tableau de bord MLOps")

st.caption(
    "Observabilité locale en lecture seule. "
    "Données simulées, sans affichage des prompts, "
    "réponses ou arguments des outils."
)

if st.button("Actualiser les données"):
    st.rerun()


# ------------------------------------------------------------
# Load local traces
# ------------------------------------------------------------

all_traces = load_traces(limit=500)


# ------------------------------------------------------------
# Interactive filters
# ------------------------------------------------------------

st.subheader("Filtres des exécutions")

mode_options = {
    "Toutes les traces": "all",
    "Client Ollama par défaut": "local_ollama",
    "Client injecté (tests possibles)": "injected_client",
    "Anciennes traces non classées": "unclassified",
}

status_options = [
    "all",
    *sorted({
        event["status"]
        for event in all_traces
        if event["status"]
    }),
]

tool_options = [
    "all",
    *sorted({
        item["tool"]
        for event in all_traces
        for item in event["tools_used"]
        if item["tool"]
    }),
]

mode_column, status_column, tool_column = st.columns(3)

with mode_column:
    selected_mode = st.selectbox(
        "Origine de l'exécution",
        options=list(mode_options),
    )

with status_column:
    selected_status = st.selectbox(
        "Statut de l'agent",
        options=status_options,
    )

with tool_column:
    selected_tool = st.selectbox(
        "Outil appelé",
        options=tool_options,
    )


# ------------------------------------------------------------
# Apply filters and calculate statistics
# ------------------------------------------------------------

traces = filter_traces(
    all_traces,
    mode=mode_options[selected_mode],
    status=selected_status,
    tool=selected_tool,
)

summary = summarize_traces(traces)

st.caption(
    f"{len(traces)} trace(s) affichée(s) "
    f"sur {len(all_traces)} trace(s) chargée(s). "
    "Les statistiques reflètent les filtres sélectionnés."
)

if mode_options[selected_mode] == "all":
    st.info(
        "La vue globale mélange potentiellement "
        "des requêtes Ollama, des tests avec clients "
        "injectés et des traces anciennes non classées. "
        "Filtre par origine pour comparer ces modes."
    )


# ------------------------------------------------------------
# Execution KPIs
# ------------------------------------------------------------

st.subheader("Indicateurs d'exécution")

first, second, third, fourth = st.columns(4)

first.metric(
    "Exécutions",
    summary["total_runs"],
)

second.metric(
    "Terminées",
    summary["completed_runs"],
)

third.metric(
    "Appels d'outils",
    summary["tool_calls"],
)

fourth.metric(
    "Latence moyenne",
    format_latency(summary["mean_latency_ms"]),
)

st.caption(
    "Le statut 'completed' signifie que l'agent "
    "a terminé sa réponse. Il ne garantit pas "
    "la réussite de tous les appels d'outils."
)


# ------------------------------------------------------------
# Tool success and failure metrics
# ------------------------------------------------------------

st.subheader("Fiabilité des appels d'outils")

success_col, error_col, rate_col = st.columns(3)

success_col.metric(
    "Appels réussis",
    summary["tool_successes"],
)

error_col.metric(
    "Appels en échec",
    summary["tool_errors"],
)

error_rate = summary["tool_error_rate_pct"]

rate_col.metric(
    "Taux d'échec des appels",
    (
        f"{error_rate:.2f} %"
        if error_rate is not None
        else "—"
    ),
)

st.caption(
    "Le taux d'échec est calculé sur les appels "
    "d'outils des traces actuellement filtrées. "
    "Les refus de sécurité, les erreurs de validation "
    "et les ressources introuvables sont inclus. "
    "Ce n'est pas un taux d'incidents en production."
)


# ------------------------------------------------------------
# Evaluation reports
# ------------------------------------------------------------

st.subheader("Évaluations locales")

tool_report = load_report_summary(
    TOOL_REPORT,
    kind="tools",
)

quality_report = load_report_summary(
    QUALITY_REPORT,
    kind="quality",
)

evaluation_left, evaluation_right = st.columns(2)

with evaluation_left:
    st.metric(
        "Sélection des outils et arguments",
        (
            f"{tool_report['passed']}/{tool_report['total']}"
            if tool_report is not None
            else "Non disponible"
        ),
    )

with evaluation_right:
    st.metric(
        "Langue et couverture des faits",
        (
            f"{quality_report['passed']}/{quality_report['total']}"
            if quality_report is not None
            else "Non disponible"
        ),
    )

st.caption(
    "Ces scores proviennent des derniers rapports "
    "locaux et ne sont pas recalculés par les filtres."
)


# ------------------------------------------------------------
# Charts and history
# ------------------------------------------------------------

if not traces:
    st.info(
        "Aucune trace ne correspond aux filtres "
        "sélectionnés."
    )

else:
    chart_left, chart_right = st.columns(2)

    # --------------------------------------------------------
    # Agent execution statuses
    # --------------------------------------------------------

    with chart_left:
        st.subheader("Statuts des exécutions")

        status_rows = [
            {
                "Statut": name,
                "Nombre": count,
            }
            for name, count
            in summary["status_counts"].items()
        ]

        if status_rows:
            status_df = pd.DataFrame(status_rows)

            st.bar_chart(
                status_df,
                x="Statut",
                y="Nombre",
            )
        else:
            st.info("Aucun statut disponible.")

    # --------------------------------------------------------
    # Tool calls: successful versus failed
    # --------------------------------------------------------

    with chart_right:
        st.subheader("Résultats des appels par outil")

        outcome_rows = [
            {
                "Outil": name,
                "Réussis": counts["success"],
                "En échec": counts["failed"],
            }
            for name, counts
            in summary["tool_outcomes"].items()
        ]

        if outcome_rows:
            outcome_df = pd.DataFrame(outcome_rows)

            st.bar_chart(
                outcome_df,
                x="Outil",
                y=["Réussis", "En échec"],
            )

        else:
            st.info(
                "Aucun appel d'outil dans "
                "les traces sélectionnées."
            )

    st.caption(
        "Un appel réussi signifie que l'outil a retourné "
        "ok=True. Pour prepare_incident_ticket, "
        "il s'agit uniquement d'une proposition : "
        "aucun ticket n'est créé ou approuvé."
    )

    # --------------------------------------------------------
    # Detailed tool outcome table
    # --------------------------------------------------------

    st.subheader("Détail des appels par outil")

    if summary["tool_outcomes"]:
        detail_rows = []

        for name, counts in summary["tool_outcomes"].items():
            successes = counts["success"]
            failures = counts["failed"]
            total = successes + failures

            detail_rows.append({
                "Outil": name,
                "Appels": total,
                "Réussis": successes,
                "En échec": failures,
                "Taux d'échec (%)": round(
                    100 * failures / total,
                    2,
                ),
            })

        st.dataframe(
            detail_rows,
            hide_index=True,
            use_container_width=True,
        )

    else:
        st.info("Aucun résultat d'outil disponible.")

    # --------------------------------------------------------
    # Execution history
    # --------------------------------------------------------

    st.subheader("Historique des dernières exécutions")

    history_rows = [
        {
            "Date UTC": event["timestamp_utc"],
            "Trace": event["trace_id"],
            "Origine": event["execution_mode"],
            "Statut": event["status"],
            "Modèle": event["model"],
            "Latence": format_latency(
                event["latency_ms"]
            ),
            "Outils appelés": ", ".join(
                item["tool"]
                for item in event["tools_used"]
            ),
            "Appels en échec": sum(
                item["ok"] is False
                for item in event["tools_used"]
            ),
        }
        for event in reversed(traces)
    ]

    st.dataframe(
        history_rows,
        hide_index=True,
        use_container_width=True,
    )


    # --------------------------------------------------------
    # Interactive event timeline
    # --------------------------------------------------------

    st.subheader("Chronologie des événements de l'agent")

    st.caption(
        "Sélectionne une exécution pour consulter "
        "ses événements horodatés. "
        "Aucun prompt, réponse ou argument sensible "
        "n'est affiché."
    )

    # Only display traces containing a valid event timeline.
    # Show the most recent executions first.
    timeline_traces = [
        event
        for event in reversed(traces)
        if event.get("trace_id") and event.get("events")
    ]

    if not timeline_traces:
        st.info(
            "Aucune chronologie disponible pour "
            "les traces actuellement filtrées. "
            "Les anciennes traces peuvent ne pas "
            "contenir d'événements détaillés."
        )

    else:
        trace_ids = [
            event["trace_id"]
            for event in timeline_traces
        ]

        selected_trace_id = st.selectbox(
            "Sélectionner une exécution (trace_id)",
            options=trace_ids,
            key="event_timeline_trace_id",
        )

        selected_trace = next(
            event
            for event in timeline_traces
            if event["trace_id"] == selected_trace_id
        )

        timeline = selected_trace["events"]

        st.caption(
            f"Origine : {selected_trace['execution_mode']} | "
            f"Statut : {selected_trace['status']} | "
            f"Nombre d'événements : {len(timeline)}"
        )

        timeline_rows = []

        for index, event in enumerate(timeline, start=1):
            outcome = event.get("ok")

            if outcome is True:
                outcome_label = "Succès"
            elif outcome is False:
                outcome_label = "Échec"
            else:
                outcome_label = "—"

            timeline_rows.append({
                "N°": index,
                "Date UTC": event.get(
                    "timestamp_utc",
                    "—",
                ),
                "Événement": event.get(
                    "event_type",
                    "—",
                ),
                "Étape": event.get(
                    "step",
                    "—",
                ),
                "Outil": event.get(
                    "tool",
                    "—",
                ),
                "Résultat": outcome_label,
                "Code d'erreur": event.get(
                    "error",
                    "—",
                ),
            })

        st.dataframe(
            timeline_rows,
            hide_index=True,
            use_container_width=True,
        )

        st.caption(
            "Les événements sont lus à partir du "
            "journal JSONL local. Le tableau de bord "
            "fonctionne uniquement en lecture seule."
        )

# ------------------------------------------------------------
# Safety notice
# ------------------------------------------------------------

st.divider()

st.caption(
    "OpsGuard AI — Tableau de bord local en lecture seule. "
    "Aucune création de ticket, approbation "
    "ou exécution d'outil MLOps n'est déclenchée."
)
