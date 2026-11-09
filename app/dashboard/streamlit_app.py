
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
# Load safe local traces
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
        options=list(mode_options.keys()),
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
# Apply filters
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
    "Les indicateurs ci-dessous reflètent les filtres."
)

if mode_options[selected_mode] == "all":
    st.info(
        "La vue globale peut mélanger de vraies requêtes "
        "Ollama, des tests avec clients injectés "
        "et des traces anciennes non classées. "
        "Sélectionne 'Client Ollama par défaut' "
        "pour analyser ce mode séparément."
    )


# ------------------------------------------------------------
# Main execution indicators
# ------------------------------------------------------------

st.subheader("Indicateurs d'exécution")

first, second, third, fourth = st.columns(4)

first.metric(
    label="Exécutions",
    value=summary["total_runs"],
)

second.metric(
    label="Terminées",
    value=summary["completed_runs"],
)

third.metric(
    label="Appels d'outils en erreur",
    value=summary["tool_errors"],
)

mean_latency = summary["mean_latency_ms"]

fourth.metric(
    label="Latence moyenne",
    value=(
        f"{mean_latency / 1000:.2f} s"
        if mean_latency is not None
        else "—"
    ),
)

st.caption(
    "Une exécution 'completed' indique que l'agent "
    "a terminé sa réponse, pas qu'une action sensible "
    "a été autorisée ou exécutée."
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
        label="Sélection des outils et arguments",
        value=(
            f"{tool_report['passed']}/{tool_report['total']}"
            if tool_report is not None
            else "Non disponible"
        ),
    )

with evaluation_right:
    st.metric(
        label="Langue et couverture des faits",
        value=(
            f"{quality_report['passed']}/{quality_report['total']}"
            if quality_report is not None
            else "Non disponible"
        ),
    )

st.caption(
    "Les résultats des évaluations proviennent "
    "des derniers rapports locaux disponibles. "
    "Ils ne sont pas recalculés lors du filtrage."
)


# ------------------------------------------------------------
# Charts and recent executions
# ------------------------------------------------------------

if not traces:
    st.info(
        "Aucune trace ne correspond aux filtres "
        "sélectionnés. Modifie les filtres ou lance "
        "une nouvelle requête à l'agent."
    )

else:
    chart_left, chart_right = st.columns(2)

    # --------------------------------------------------------
    # Execution status distribution
    # --------------------------------------------------------

    with chart_left:
        st.subheader("Statuts des exécutions")

        status_rows = [
            {
                "Statut": name,
                "Nombre": count,
            }
            for name, count in (
                summary["status_counts"].items()
            )
        ]

        if status_rows:
            status_df = pd.DataFrame(status_rows)

            st.bar_chart(
                status_df,
                x="Statut",
                y="Nombre",
            )
        else:
            st.info("Aucun statut à afficher.")

    # --------------------------------------------------------
    # Tool calls distribution
    # --------------------------------------------------------

    with chart_right:
        st.subheader("Tentatives d'appels par outil")

        st.caption(
            "Les tentatives refusées sont comptabilisées. "
            "Une tentative ne signifie pas qu'une action "
            "a réellement été exécutée."
        )

        tool_rows = [
            {
                "Outil": name,
                "Appels": count,
            }
            for name, count in (
                summary["tool_counts"].items()
            )
        ]

        if tool_rows:
            tool_df = pd.DataFrame(tool_rows)

            st.bar_chart(
                tool_df,
                x="Outil",
                y="Appels",
            )
        else:
            st.info(
                "Aucun appel d'outil dans "
                "les traces sélectionnées."
            )

    # --------------------------------------------------------
    # Recent execution history
    # --------------------------------------------------------

    st.subheader("Historique des dernières exécutions")

    rows = [
        {
            "Date UTC": event["timestamp_utc"],
            "Trace": event["trace_id"],
            "Origine": event["execution_mode"],
            "Statut": event["status"],
            "Modèle": event["model"],
            "Latence (ms)": event["latency_ms"],
            "Outils appelés": ", ".join(
                item["tool"]
                for item in event["tools_used"]
            ),
            "Appels en erreur": sum(
                item["ok"] is False
                for item in event["tools_used"]
            ),
        }
        for event in reversed(traces)
    ]

    st.dataframe(
        rows,
        hide_index=True,
        use_container_width=True,
    )


# ------------------------------------------------------------
# Security and limitations notice
# ------------------------------------------------------------

st.divider()

st.caption(
    "OpsGuard AI — Observabilité locale. "
    "Le tableau de bord ne crée aucun ticket, "
    "n'approuve aucune action et n'exécute "
    "aucun outil MLOps."
)
