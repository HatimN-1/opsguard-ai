"""Single professional ADF operations interface for the 12 fixed business assets.

No Azure account needed; only synthetic external JSONL evidence. Qwen3 is
attempted automatically in investigations, and guarded fallback remains usable.
"""

import json
from collections import Counter
from datetime import datetime
from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st

from app.adf_monitor.business_catalog import (
    catalog_fingerprint,
    catalog_version,
    known_business_ids,
    load_catalog,
    require_business_pipeline,
)
from app.adf_monitor.business_escalation import (
    EscalationError,
    approve_case,
    list_cases,
    prepare_case,
    request_case,
)
from app.adf_monitor.company_monitor import company_snapshot, list_business_runs
from app.adf_monitor.doc_search import search_official_docs
from app.adf_monitor.enterprise_agent import InvestigationPlanError, investigate_company
from app.adf_monitor.source import (
    SourceUnavailable,
    external_workspace,
    query_adf_logs,
    source_mode,
)

st.set_page_config(
    page_title="OpsGuard AI | Northstar ADF Operations",
    page_icon=":material/security:", layout="wide", initial_sidebar_state="expanded",
)

CSS_FILE = Path(__file__).with_name("assets") / "enterprise.css"
# Reinject on every Streamlit rerun. st.html keeps CSS in the app DOM without
# consuming layout space; native config.toml is the persistent light base.
if hasattr(st, "html"):
    st.html(CSS_FILE)
else:  # Compatibility with older Streamlit versions.
    st.markdown("<style>" + CSS_FILE.read_text(encoding="utf-8") + "</style>",
                unsafe_allow_html=True)


NAVIGATION = (
    "Centre de contrôle",
    "Agent d'investigation",
    "Exécutions & preuves",
    "Incidents & validation",
    "Sources & gouvernance",
)

# SVG is static application-owned markup, not external content or a logo image.
BRAND_MARKUP = """<div class="og-brand-wrap">
<svg class="og-brand-mark" viewBox="0 0 48 48" role="img" aria-label="Logo OpsGuard AI"
     xmlns="http://www.w3.org/2000/svg">
  <rect x="2" y="2" width="44" height="44" rx="13" fill="#103d58"/>
  <path d="M24 8 L38 15 V24 C38 33 31 38 24 41 C17 38 10 33 10 24 V15 Z"
        fill="none" stroke="#c7eef0" stroke-width="2.3"/>
  <path d="M14 25 L21 31 L34 17" fill="none" stroke="#54d8bd"
        stroke-width="3.6" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
<div><div class="og-brand">OpsGuard AI</div>
<div class="og-brand-sub">NORTHSTAR · DATA OPERATIONS</div></div></div>"""


def hero(eyebrow: str, title: str, description: str) -> None:
    st.markdown(
        '<div class="og-hero"><div class="og-eyebrow">'
        + escape(eyebrow) + '</div><h1>' + escape(title) + '</h1><p>'
        + escape(description) + '</p></div>',
        unsafe_allow_html=True,
    )


def kpi(label: str, value: str, foot: str = "") -> None:
    st.markdown(
        f'<div class="og-kpi"><div class="og-kpi-label">{escape(label)}</div>'
        f'<div class="og-kpi-value">{escape(value)}</div>'
        f'<div class="og-kpi-foot">{escape(foot)}</div></div>',
        unsafe_allow_html=True,
    )


def section(title: str) -> None:
    st.markdown('<div class="og-section">' + escape(title) + '</div>', unsafe_allow_html=True)


def _fmt_int(number: object) -> str:
    return f"{int(number or 0):,}".replace(",", " ")


def _time_short(value: str | None) -> str:
    if not value:
        return "Aucune exécution"
    try:
        return datetime.fromisoformat(value).strftime("%d/%m/%Y %H:%M UTC")
    except ValueError:
        return "Horodatage indisponible"


def _catalog_rows() -> list[dict]:
    return load_catalog()["pipelines"]


def _get_snapshot() -> dict | None:
    try:
        return company_snapshot(hours=168)
    except (OSError, ValueError, SourceUnavailable) as exc:
        st.error(f"Source de logs inaccessible : {type(exc).__name__}.")
        return None


def _missing_logs() -> None:
    st.markdown(
        '<div class="og-warning">Aucune exécution consultable pour la période sélectionnée. '
        'Vérifiez la disponibilité de la source de télémétrie auprès de '
        'l’administrateur de la plateforme.</div>',
        unsafe_allow_html=True,
    )


def sidebar() -> str:
    with st.sidebar:
        if hasattr(st, "html"):
            st.html(BRAND_MARKUP)
        else:
            st.markdown(BRAND_MARKUP, unsafe_allow_html=True)
        st.divider()
        st.markdown("**ESPACE MÉTIER**")
        active_page = st.session_state.get("enterprise_nav", NAVIGATION[0])
        if active_page not in NAVIGATION:
            active_page = NAVIGATION[0]
        nav_icons = (
            ":material/dashboard:",
            ":material/manage_search:",
            ":material/history:",
            ":material/assignment_turned_in:",
            ":material/policy:",
        )
        for index, (label, icon) in enumerate(zip(NAVIGATION, nav_icons)):
            if st.button(
                label,
                key=f"og_navigation_{index}",
                icon=icon,
                type="primary" if label == active_page else "secondary",
                width="stretch",
            ):
                st.session_state["enterprise_nav"] = label
                st.rerun()
        st.divider()
        st.markdown(
            '<div class="og-environment"><strong>Plateforme ADF · Northstar Retail</strong>'
            '<div>12 pipelines métiers · Analyse des exécutions</div>'
            '<div>Catalogue ' + escape(catalog_version()) + '</div></div>',
            unsafe_allow_html=True,
        )
    return active_page


def page_overview() -> None:
    hero("NORTHSTAR / OPERATIONS OVERVIEW", "Azure Data Factory · Control Center",
         "Surveillez les 12 pipelines de l'entreprise, leurs dernières exécutions "
         "et les incidents constatés. Le patrimoine métier reste fixe.")
    snapshot = _get_snapshot()
    if snapshot is None:
        return
    a, b, c, d = st.columns(4)
    with a:
        kpi("Pipelines métier", "12", "Catalogue versionné, non modifiable")
    with b:
        kpi("Exécutions observées", _fmt_int(snapshot["total_runs_in_window"]), "Fenêtre : 7 jours")
    with c:
        kpi(
            "Exécutions en échec", _fmt_int(snapshot["failed_runs_in_window"]),
            "Exécutions uniques, sans doublons d'activités",
        )
    with d:
        kpi(
            "Pipelines actuellement en échec",
            _fmt_int(snapshot["latest_failed_pipelines"]),
            "Dernier statut observé par pipeline",
        )
    section("État des douze pipelines")
    items = snapshot["pipelines"]
    st.dataframe(pd.DataFrame([{
        "Pipeline": x["pipeline_id"], "Mission": x["display_name"],
        "Domaine": x["domain"], "Criticité": x["criticality"],
        "Dernier statut": x["last_status"], "Dernier signal (UTC)": _time_short(x["last_seen_utc"]),
    } for x in items]), width="stretch", height=495, hide_index=True)
    if not snapshot["runs"]:
        _missing_logs()
        return
    left, right = st.columns([1.35, 1], gap="large")
    with left:
        section("Activité par pipeline — 7 jours")
        counts = Counter(item["pipeline_name"] for item in snapshot["runs"])
        chart = pd.DataFrame({"Pipeline": list(known_business_ids()),
                              "Exécutions": [counts.get(pid, 0) for pid in known_business_ids()]})
        st.bar_chart(chart.set_index("Pipeline"), height=330)
    with right:
        section("Dernières anomalies")
        failed = [r for r in snapshot["runs"] if r["status"] == "Failed"][:8]
        if not failed:
            st.success("Aucune exécution en échec dans cette fenêtre.")
        for event in failed:
            st.markdown(f"**{event['pipeline_name']}** · `{event['error_code'] or 'INCONNU'}`")
            st.caption(_time_short(event["timestamp_utc"]) + "  ·  " + event["run_id"][:13])
    st.markdown(
        '<div class="og-note">Ces indicateurs comptent des exécutions de pipeline. '
        'Une activité échouée et son pipeline parent ne sont pas deux incidents '
        'distincts.</div>',
        unsafe_allow_html=True,
    )


def _available_runs(pipeline_id: str | None) -> list[dict]:
    if not pipeline_id:
        return []
    try:
        return [r for r in list_business_runs(hours=720) if r["pipeline_name"] == pipeline_id][:100]
    except (OSError, ValueError, SourceUnavailable):
        return []


def page_agent() -> None:
    hero("NORTHSTAR / EVIDENCE-DRIVEN AGENT", "Agent d’investigation MLOps",
         "Posez une question. OpsGuard AI planifie la recherche, consulte les "
         "journaux d'exécution et la base documentaire Microsoft Learn, "
         "puis produit un rapport étayé par des preuves. Toute action reste humaine.")
    question = st.text_area(
        "Votre question métier",
        value=(
            "Quelles sont les dernières erreurs dans nos pipelines Azure "
            "Data Factory, et quelles activités sont responsables ?"
        ),
        height=96, max_chars=1500,
    )
    a, b, c = st.columns([1.6, 1.6, .75])
    with a:
        choice = st.selectbox("Pipeline", ["Tous les pipelines", *known_business_ids()])
    pipeline_id = None if choice == "Tous les pipelines" else choice
    with b:
        runs = _available_runs(pipeline_id)
        run_options = ["Toutes les exécutions", *[r["run_id"] for r in runs]]
        chosen_run = st.selectbox("Exécution", run_options)
    with c:
        hours = st.selectbox("Période", [24, 72, 168], index=1,
                             format_func=lambda v: f"{v} h")
    submitted = st.button("✦  Lancer l’investigation", type="primary")
    if submitted:
        with st.spinner(
            "Planification → outils → documentation → synthèse locale..."
        ):
            try:
                prior = st.session_state.get("enterprise_last_investigation") or {}
                prior_plan = prior.get("plan", {})
                result = investigate_company(
                    question, pipeline_id=pipeline_id,
                    run_id=None if chosen_run == "Toutes les exécutions" else chosen_run,
                    hours=hours, use_llm=True,
                    context_pipeline=prior_plan.get("pipeline_id"),
                    context_run=prior_plan.get("run_id"),
                    context_error_codes=list(dict.fromkeys(
                        e["error_code"] for e in (prior.get("facts") or {}).get("errors", [])
                        if e.get("error_code")
                    )),
                )
            except (InvestigationPlanError, SourceUnavailable, OSError, ValueError) as exc:
                # Avoid showing a previous report below an error as if it were current.
                st.session_state.pop("enterprise_last_investigation", None)
                st.error(str(exc))
            else:
                st.session_state["enterprise_last_investigation"] = result
                st.session_state["enterprise_last_question"] = question
    result = st.session_state.get("enterprise_last_investigation")
    if not result:
        st.markdown(
            '<div class="og-note">La recherche commence avec votre demande. '
            'Le modèle n’a aucune autorisation de modification des pipelines.</div>',
            unsafe_allow_html=True,
        )
        return
    section("Rapport d'investigation")
    plan = result["plan"]
    st.caption(
        "Dernière investigation enregistrée : " + _time_short(result["created_at_utc"])
        + f" · pipeline {plan['pipeline_id'] or 'tous'} · run {plan['run_id'] or 'tous'} "
        + f"· période effective {plan['hours']} h"
    )
    with st.expander("Plan exécuté et sélection des outils"):
        for i, instruction in enumerate(plan["steps"], 1):
            st.markdown(f"{i}. {instruction}")
        st.dataframe(pd.DataFrame(result["tools_used"]), width="stretch", hide_index=True)
    facts = result["facts"]
    if not facts:
        if result["status"] == "no_matching_events":
            st.info("Aucun événement correspondant aux filtres. Aucune cause n'est inventée.")
        else:
            st.warning("Source non disponible : le système ne formule pas de cause racine.")
        return
    a, b, c, d = st.columns(4)
    with a:
        st.metric("Événements filtrés", _fmt_int(facts.get("matching_events")))
    with b:
        st.metric("Exécutions de pipeline", _fmt_int(facts.get("pipeline_run_count")))
    with c:
        st.metric("Exécutions d'activité", _fmt_int(facts.get("activity_run_count")))
    with d:
        st.metric("Événements en échec", _fmt_int(facts.get("status_counts", {}).get("Failed", 0)))
    if facts.get("truncated"):
        st.info(
            f"{facts.get('returned_events', 0)} événements affichables sur "
            f"{facts.get('matching_events', 0)} filtrés. Les totaux sont calculés "
            "sur la source externe complète dans les limites de lecture configurées."
        )
    section("Synthèse fondée sur les preuves")
    business = result.get("business_report") or {}
    st.markdown(business.get("summary", "Aucune synthèse déterministe disponible."))
    proposal = result.get("escalation_proposal")
    if proposal:
        st.info(
            "Proposition d'escalade préparée, sans création de ticket ni validation "
            "automatique. Pipeline : " + proposal["pipeline_id"] +
            " · Run ID : " + proposal["run_id"] +
            ". La soumission reste réservée à un opérateur humain."
        )
    elif result.get("escalation_decision") == "REFUSED":
        st.warning("Proposition d'escalade refusée : vérifier le Run ID et son statut.")
    if business.get("kind") in {"LATEST_STATUS", "RUN_COMPARISON", "RECURRENCE"}:
        section(business.get("title", "Exécutions observées"))
        if business.get("rows"):
            st.dataframe(pd.DataFrame(business["rows"]), width="stretch", hide_index=True)
        else:
            st.info("Aucune exécution correspondant à la sélection.")
        if business.get("coverage_note"):
            st.caption(business["coverage_note"])
        st.markdown(
            '<div class="og-safe">Le classement par Run ID est calculé à partir '
            'des événements, sans interprétation LLM.</div>',
            unsafe_allow_html=True,
        )
        st.caption(
            f"Trace {result['trace_id']} · {result['tool_call_count']} outils · "
            f"{result['latency_ms']:.0f} ms · Qwen3 : {result['llm_status']}"
        )
        return
    errors = facts.get("errors", [])
    if result["llm_status"] == "ACCEPTED":
        st.markdown("**Interprétation Qwen3 — hypothèses à vérifier**")
        st.markdown(result["llm_summary"])
    elif result["llm_status"] == "REJECTED_BY_GUARD":
        st.caption(
            "Synthèse Qwen3 non retenue : les preuves restent consultables. "
            f"Motif : {result.get('llm_validation_reason') or 'non précisé'}."
        )
    elif result["llm_status"] == "UNAVAILABLE":
        st.caption("Ollama indisponible : rapport déterministe conservé. Aucun élément inventé.")
    section("Anomalies et exécutions concernées")
    if errors:
        st.dataframe(pd.DataFrame([{
            "Pipeline": e["pipeline_name"], "Run ID": e["run_id"],
            "Code": e["error_code"],
            "Activité(s) en échec": ", ".join(e.get("failing_activities", [])) or "—",
            "Occurrences (pipeline + activité)": e["occurrences"],
            "Documentation": result["document_status"].get(e["error_code"], "INCONNU"),
        } for e in errors]), width="stretch", hide_index=True)
    else:
        st.caption("Aucune anomalie codifiée dans la sélection.")
    section("Preuves techniques vérifiables")
    evidence = facts.get("evidence_events", [])
    if evidence:
        st.dataframe(pd.DataFrame([{
            "UTC": e["timestamp_utc"], "Pipeline": e["pipeline_name"],
            "Run": e["run_id"], "Activité": e.get("activity_name") or "(pipeline)",
            "Type": e.get("activity_type", ""), "Runtime": e.get("integration_runtime", ""),
            "Code": e.get("error_code") or "—",
        } for e in evidence]), width="stretch", hide_index=True)
    else:
        st.caption("Aucun événement d'échec à citer.")
    section("Documentation et vérifications")
    docs = result["documents"]
    if docs:
        for doc in docs:
            st.markdown(f"**{doc['title']}** — [Microsoft Learn]({doc['url']})")
            st.caption(doc.get("summary_fr", ""))
            with st.expander("Vérifications recommandées · " + doc["doc_id"]):
                for check in doc.get("checks_fr", []):
                    st.markdown("- " + check)
    else:
        st.warning(
            "Aucune référence spécifique dans l'index pour les erreurs recherchées."
        )
    for code, status in result["document_status"].items():
        if status == "NOT_SEARCHED_TOOL_LIMIT":
            st.info(f"Code `{code}` : documentation NON RECHERCHÉE (limite de 4 appels).")
        elif status == "NOT_FOUND_IN_INDEX":
            st.warning(
                f"Code `{code}` : aucun passage dans l'index local. "
                "Cela ne prouve pas l'absence de documentation sur Internet."
            )
    st.markdown(
        '<div class="og-safe"><strong>Limite de confiance :</strong> '
        'les événements sont synthétiques ; un code observé est une preuve de journal, '
        'pas la preuve de sa cause racine. Aucune action corrective ni approbation '
        'n’a été exécutée.</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        f"Trace {result['trace_id']} · {result['tool_call_count']} outils · "
        f"{result['latency_ms']:.0f} ms · Qwen3 : {result['llm_status']}"
    )


def page_runs() -> None:
    hero("NORTHSTAR / EXECUTION HISTORY", "Journaux et preuves d’exécution",
         "Sélectionnez un pipeline, un Run ID et le niveau de détail souhaité. "
         "Les journaux externes sont consultés en lecture seule.")
    choice = st.selectbox("Pipeline métier", known_business_ids(), key="enterprise_runs_pipeline")
    company = require_business_pipeline(choice)
    st.caption(
        f"{company['display_name']} · {company['source_system']} → "
        f"{company['target_system']} · {company['frequency']}"
    )
    runs = _available_runs(choice)
    if not runs:
        _missing_logs()
        return
    options = ["Toutes les exécutions", *[r["run_id"] for r in runs]]
    selected = st.selectbox("Exécution (Run ID)", options, key="enterprise_runs_id")
    hours = st.selectbox(
        "Fenêtre (heures)", [24, 72, 168, 720],
        index=2, key="enterprise_runs_hours",
    )
    try:
        data = query_adf_logs(choice, hours=hours, limit=500,
                              run_id=None if selected == options[0] else selected)
    except (OSError, ValueError, SourceUnavailable) as exc:
        st.error(f"Impossible de consulter les logs : {type(exc).__name__}")
        return
    a, b, c = st.columns(3)
    with a:
        st.metric("Événements filtrés", _fmt_int(data["matching_events"]))
    with b:
        st.metric("Exécutions de pipeline", _fmt_int(data["pipeline_run_count"]))
    with c:
        st.metric("Activités en échec", _fmt_int(sum(
            e["status"] == "Failed" and e["table"] == "ADFActivityRun" for e in data["events"]
        )))
    section("Événements structurés")
    a, b = st.columns(2)
    with a:
        only_failures = st.checkbox("Afficher uniquement les échecs", value=True)
    with b:
        types = [
            "Tous", *sorted({e["activity_type"] for e in data["events"] if e["activity_type"]})
        ]
        activity_type = st.selectbox("Type d'activité", types)
    filtered = [x for x in data["events"]
                if (not only_failures or x["status"] == "Failed")
                and (activity_type == "Tous" or x["activity_type"] == activity_type)]
    if filtered:
        st.dataframe(pd.DataFrame([{
            "UTC": x["timestamp_utc"], "Run ID": x["run_id"],
            "Activité": x["activity_name"] or "(pipeline)",
            "Type": x["activity_type"], "État": x["status"],
            "Code": x["error_code"] or "—", "Runtime": x["integration_runtime"],
        } for x in filtered]), width="stretch", hide_index=True)
    else:
        st.info("Aucun événement ne correspond aux filtres.")
    if data["truncated"]:
        st.caption(
            "Au maximum 500 événements récents affichés ; les statistiques "
            "portent sur tous les événements filtrés de la source externe."
        )
    section("Historique des runs sélectionnés")
    st.dataframe(pd.DataFrame([{
        "Run": x["run_id"], "Statut": x["status"],
        "Code": x["error_code"] or "—", "Fin UTC": _time_short(x["timestamp_utc"]),
    } for x in runs[:30]]), width="stretch", hide_index=True)


def page_incidents() -> None:
    hero("NORTHSTAR / HUMAN-IN-THE-LOOP", "Escalades et validation humaine",
         "Préparez une demande documentée, soumettez-la à validation et suivez "
         "les décisions du workflow. Les actions d'infrastructure restent exclues.")
    with st.expander("Périmètre de validation et contrôle d'accès"):
        st.caption(
            "Cette instance utilise des rôles de démonstration : alice/charlie "
            "(opérateurs) et bob (approbateur). Aucune authentification de "
            "production n'est activée."
        )
    a, b = st.columns(2)
    with a:
        pipeline = st.selectbox(
            "Pipeline concerné", known_business_ids(), key="enterprise_case_pipeline"
        )
    runs = _available_runs(pipeline)
    with b:
        ids = [x["run_id"] for x in runs]
        run_id = st.selectbox("Exécution", ids if ids else ["Aucune exécution disponible"],
                              key="enterprise_case_run")
    reason = st.text_area("Motif métier (sans données personnelles)",
                          value=(
                              "Investiguer cet échec ADF et faire vérifier "
                              "les recommandations documentées."
                          ),
                          max_chars=300)
    if st.button("01 · Préparer une proposition", disabled=not bool(ids)):
        try:
            st.session_state["enterprise_proposal"] = prepare_case(pipeline, run_id, reason)
        except (EscalationError, ValueError, OSError, SourceUnavailable) as exc:
            st.error(str(exc))
    proposal = st.session_state.get("enterprise_proposal")
    if proposal:
        st.info("Proposition uniquement : aucun ticket n'a encore été créé.")
        st.json(proposal)
        if st.button("02 · Transmettre pour validation"):
            try:
                created = request_case(proposal, actor="alice")
            except (EscalationError, ValueError, OSError, SourceUnavailable) as exc:
                st.error(str(exc))
            else:
                st.session_state["enterprise_last_case"] = created["case_id"]
                st.success("Demande enregistrée : PENDING_APPROVAL. Aucune modification ADF.")
                st.session_state.pop("enterprise_proposal", None)
    section("File des demandes")
    try:
        cases = list_cases()
    except (EscalationError, OSError) as exc:
        st.error(str(exc))
        cases = []
    if cases:
        st.dataframe(pd.DataFrame([{
            "Dossier": c["case_id"], "Pipeline": c["pipeline_id"],
            "Run ID": c["run_id"], "Statut": c["status"],
            "Demandeur": c["actor"],
        } for c in cases]), width="stretch", hide_index=True)
        pending = [x["case_id"] for x in cases if x["status"] == "PENDING_APPROVAL"]
        if pending:
            chosen = st.selectbox("Dossier en attente", pending)
            if st.button("03 · Valider la demande"):
                try:
                    approved = approve_case(chosen, actor="bob")
                except (EscalationError, OSError) as exc:
                    st.error(str(exc))
                else:
                    st.success(f"Dossier {approved['case_id']} approuvé dans le workflow de démonstration.")
    else:
        st.caption("Aucune demande d'escalade dans cette source.")


def _read_traces(limit: int = 500) -> list[dict]:
    path = Path(__file__).resolve().parents[2] / "logs" / "agent_traces.jsonl"
    if not path.is_file():
        return []
    if path.stat().st_size > 12_000_000:
        return []
    parsed = []
    for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            val = json.loads(line)
            if isinstance(val, dict):
                parsed.append(val)
        except ValueError:
            continue
    return parsed


def page_governance() -> None:
    hero("NORTHSTAR / GOVERNANCE & PROVENANCE", "Sources, qualité et gouvernance",
         "Catalogue versionné, documents Microsoft Learn sourcés, traces "
         "d'outils et contrôles de qualité des investigations.")
    st.info(
        "**Provenance de cette instance :** scénario pédagogique Northstar Retail, "
        "entreprise fictive. Les journaux sont synthétiques et enregistrés "
        "localement ; aucune connexion à un abonnement Azure réel, "
        "aucune authentification de production ni exécution d'infrastructure."
    )
    section("Catalogue métier immuable — 12 pipelines")
    catalog = load_catalog()
    st.caption(
        f"Version {catalog['catalog_version']} · "
        f"Empreinte SHA-256 courte : {catalog_fingerprint()}"
    )
    st.dataframe(pd.DataFrame([{
        "Pipeline": x["pipeline_id"], "Mission": x["display_name"],
        "Source": x["source_system"], "Destination": x["target_system"],
        "Fréquence": x["frequency"], "Responsable": x["owner_team"],
    } for x in _catalog_rows()]), width="stretch", height=495, hide_index=True)
    section("Recherche de connaissances vérifiables")
    term = st.text_input("Documentation Microsoft Learn", value="databricks token 403")
    if term:
        try:
            docs = search_official_docs(term, limit=5)
        except (ValueError, OSError) as exc:
            st.error(str(exc))
            docs = []
        if not docs:
            st.warning(
                "Aucun passage dans l'index local ; recherche Web non exhaustive."
            )
        for doc in docs:
            st.markdown(f"**{doc['title']}** · [Consulter la page Microsoft Learn]({doc['url']})")
            st.caption(doc["summary_fr"])
    section("Observabilité de l'agent")
    traces = _read_traces()
    if traces:
        a, b, c = st.columns(3)
        with a:
            st.metric("Traces récentes", len(traces))
        with b:
            average = sum(float(t.get("latency_ms") or 0) for t in traces) / len(traces)
            st.metric("Latence moyenne", f"{average:.0f} ms")
        with c:
            st.metric("Appels d'outils", sum(int(t.get("tool_call_count") or 0) for t in traces))
        st.dataframe(pd.DataFrame([{
            "Trace": x.get("trace_id", ""), "UTC": x.get("timestamp_utc", ""),
            "Mode": x.get("execution_mode", ""), "Statut": x.get("status", ""),
            "Outils": x.get("tool_call_count", 0), "Durée ms": x.get("latency_ms", 0),
        } for x in traces[-50:][::-1]]), width="stretch", hide_index=True)
    else:
        st.caption("Aucune trace encore enregistrée.")
    section("Reproductibilité et qualité")
    report_path = Path(__file__).resolve().parents[2] / "outputs" / "enterprise_adf_evaluation.json"
    if report_path.is_file():
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
            st.json(report.get("metrics", {}), expanded=False)
            st.caption(
                f"Évaluation : {report.get('timestamp_utc')} · "
                f"Pass : {report.get('passed')}"
            )
        except (ValueError, OSError):
            st.warning("Rapport d'évaluation incomplet.")
    else:
        st.caption("Lancer d'abord : python -m scripts.evaluate_enterprise_adf")
    with st.expander("Administration des journaux — séparée de l'interface métier"):
        st.markdown(
            "**Les 12 pipelines sont fixes.** L'administrateur ajoute "
            "uniquement des événements d'exécution."
        )
        st.code(
            "python -m scripts.simulate_company_adf --all --activities 90",
            language="powershell",
        )
        st.code(
            "python -m scripts.simulate_company_adf "
            "--pipeline adf_04_inventory --scenario 3200",
            language="powershell",
        )
        st.caption("Les exports JSONL sont conservés dans : " + str(external_workspace()))
        st.caption("Aucune clé Azure, aucun secret, aucune modification de pipeline réel.")


def main() -> None:
    if source_mode() != "external_demo":
        st.error(
            "Ce scénario utilise seulement des logs externes synthétiques. "
            "Configurer OPSGUARD_ADF_SOURCE=external_demo."
        )
        return
    page = sidebar()
    if page == NAVIGATION[0]:
        page_overview()
    elif page == NAVIGATION[1]:
        page_agent()
    elif page == NAVIGATION[2]:
        page_runs()
    elif page == NAVIGATION[3]:
        page_incidents()
    else:
        page_governance()
    st.markdown("---")
    st.caption(
        "© 2026 OpsGuard AI · Northstar Retail · Data Operations · "
        "Sources et limites disponibles dans « Sources & gouvernance »."
    )


if __name__ == "__main__":
    main()
