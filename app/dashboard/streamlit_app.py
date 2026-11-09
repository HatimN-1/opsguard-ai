
"""Local, read-only observability dashboard for OpsGuard AI."""

import pandas as pd
import streamlit as st

from app.dashboard.data import (
    QUALITY_REPORT,
    TOOL_REPORT,
    load_report_summary,
    load_traces,
    summarize_traces,
)

st.set_page_config(
    page_title="OpsGuard AI",
    layout="wide",
)

st.title("OpsGuard AI — Tableau de bord MLOps")

st.caption(
    "Données simulées et traces locales ; "
    "lecture seule, sans prompts ni réponses."
)

if st.button("Actualiser les données"):
    st.rerun()


# ------------------------------------------------------------
# Load local execution traces
# ------------------------------------------------------------

traces = load_traces(limit=500)

summary = summarize_traces(traces)


# ------------------------------------------------------------
# Main KPI cards
# ------------------------------------------------------------

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
    "Erreurs d'outil",
    summary["tool_errors"],
)

fourth.metric(
    "Latence moyenne",
    (
        f"{summary['mean_latency_ms'] / 1000:.2f} s"
        if summary["mean_latency_ms"] is not None
        else "—"
    ),
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

left, right = st.columns(2)

with left:
    st.metric(
        "Outils et arguments",
        (
            f"{tool_report['passed']}"
            f"/{tool_report['total']}"
            if tool_report
            else "Non disponible"
        ),
    )

with right:
    st.metric(
        "Langue et faits attendus",
        (
            f"{quality_report['passed']}"
            f"/{quality_report['total']}"
            if quality_report
            else "Non disponible"
        ),
    )


# ------------------------------------------------------------
# Charts and execution history
# ------------------------------------------------------------

if not traces:
    st.info(
        "Aucune trace disponible. "
        "Lance une requête à l'agent local."
    )

else:
    left_chart, right_chart = st.columns(2)

    with left_chart:
        st.subheader("Statuts des exécutions")

        chart = pd.DataFrame([
            {
                "Statut": name,
                "Nombre": count,
            }
            for name, count
            in summary["status_counts"].items()
        ])

        st.bar_chart(
            chart,
            x="Statut",
            y="Nombre",
        )

    with right_chart:
        st.subheader("Appels par outil")

        if summary["tool_counts"]:
            chart = pd.DataFrame([
                {
                    "Outil": name,
                    "Appels": count,
                }
                for name, count
                in summary["tool_counts"].items()
            ])

            st.bar_chart(
                chart,
                x="Outil",
                y="Appels",
            )

        else:
            st.info(
                "Aucun outil appelé dans "
                "les traces chargées."
            )

    st.subheader("Dernières exécutions")

    rows = [
        {
            "Date UTC": event["timestamp_utc"],
            "Trace": event["trace_id"],
            "Statut": event["status"],
            "Latence (ms)": event["latency_ms"],
            "Outils": ", ".join(
                item["tool"]
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


st.caption(
    "Ce tableau de bord ne crée aucun ticket "
    "et n'exécute aucun outil MLOps."
)
