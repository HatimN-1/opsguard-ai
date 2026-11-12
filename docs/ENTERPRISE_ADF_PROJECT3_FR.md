# OpsGuard AI — Scénario de référence : 12 pipelines ADF

**Sujet de cours : Projet 3 — Agent intelligent : orchestration d'outils, observabilité et gouvernance**
**Entreprise : Northstar Retail (fictive)**
**Cloud métier : Azure Data Factory simulé**
**Version du catalogue : `data/company_adf_catalog.json`**

## 1. Scénario et frontière du système

Une entreprise exploite exactement **douze pipelines ETL métier** définis à l'avance. Leur identifiant, leur objectif, leur provenance, leur destination, leur cadence et leur séquence de neuf activités sont conservés dans un **catalogue versionné non modifiable par l'application**. Le moteur local simule seulement **de nouvelles exécutions et leurs journaux**, pas l'ETL ni la création/suppression de pipelines.

Les événements synthétiques sont inspirés des schémas `ADFActivityRun` et `ADFPipelineRun` de Microsoft Learn. Un enregistrement d'activité représente **une exécution d'activité** ; ce n'est pas un message quelconque de console. Les erreurs illustrées correspondent à des classes documentées dans les guides ADF, mais les logs et l'entreprise ne sont **pas authentiques**.

Sources de schémas :
- https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/adfactivityrun
- https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/adfpipelinerun
- https://learn.microsoft.com/en-us/azure/data-factory/monitor-configure-diagnostics
- https://learn.microsoft.com/en-us/azure/data-factory/data-factory-troubleshoot-guide
- https://learn.microsoft.com/en-us/azure/data-factory/connector-troubleshoot-guide

Le corpus documentaire local `docs/microsoft_adf_index.json` contient des **résumés français édités** avec URL officielle et termes de recherche. Le moteur BM25 recherche des passages : il ne consulte pas le Web à chaque question et ne dispose pas d'un corpus exhaustif. La documentation fournit des **causes possibles**, jamais une preuve automatique de cause racine.

## 2. Catalogue métier figé

| Pipeline | Rôle métier | Cadence |
|---|---|---|
| `adf_01_orders` | Ingestion commandes | Toutes les heures |
| `adf_02_customers` | Synchronisation clients CRM | Toutes les 4 h |
| `adf_03_payments` | Rapprochement paiements | Toutes les heures |
| `adf_04_inventory` | Inventaire entrepôt | Toutes les 2 h |
| `adf_05_orders` | Retours commandes | Chaque jour |
| `adf_06_customers` | Préférences clients | Chaque jour |
| `adf_07_payments` | Réconciliation bancaire | Chaque jour |
| `adf_08_inventory` | Prévisions des stocks | Chaque jour |
| `adf_09_orders` | Expéditions commandes | Toutes les 2 h |
| `adf_10_customers` | Programme fidélité | Chaque jour |
| `adf_11_payments` | Signaux de fraude | Toutes les heures |
| `adf_12_inventory` | Réapprovisionnement | Chaque jour |

Les définitions détaillées sont dans `data/company_adf_catalog.json`. Toute modification du catalogue exige un **changement de version documenté**, une revue et un nouveau cycle de tests. La fonctionnalité quotidienne ne modifie que les exports de logs externes.

## 3. Parcours agentique et fichiers impliqués

```text
Utilisateur, interface dédiée Streamlit
  app/dashboard/streamlit_app.py
      -> app/dashboard/enterprise_app.py
          -> app/adf_monitor/enterprise_agent.py
              (1) plan_investigation(question, pipeline_id, run_id, hours)
              (2) app/agent/tool_registry.py::execute_tool("query_adf_logs", ...)
                    -> app/adf_monitor/source.py
                    -> externe/ADFActivityRun.jsonl
                    -> externe/ADFPipelineRun.jsonl
              (3) app/agent/tool_registry.py::execute_tool("search_official_docs", ...)
                    -> app/adf_monitor/doc_search.py
                    -> docs/microsoft_adf_index.json
              (3bis) prepare_adf_escalation (si demande explicite sur un Run ID en échec)
                    -> business_escalation.prepare_case (PROPOSAL_ONLY, sans écriture)
              (4) Analyse fondée sur les faits structurés
                    -> synthèse Qwen3 locale automatiquement tentée
                    -> réponse écartée si suspecte ou incomplète
              (5) app/agent/observability.py::record_agent_trace(...)
          -> rapport : exécutions, erreurs, activités, URLs, limites, traces
```

Le plan et l'exécution des outils sont **déterministes et auditables**. Qwen3 participe à la **synthèse**, mais n'obtient ni accès aux fichiers, ni texte brut des logs, ni commandes de création/appréciation des tickets. Si Qwen3 échoue, le rapport factuel reste disponible. L'interface métier ne contient plus de case « Utiliser Qwen3 » : la tentative est automatique lors de l'investigation.

## 4. Outils : entrées, sorties, permissions et erreurs

| Outil | Entrées | Sorties | Erreurs possibles | Autorisations |
|---|---|---|---|---|
| `query_adf_logs` | pipeline_name optionnel, run_id optionnel, hours 1..720, limit 1..500 | événements normalisés, compteurs, erreurs, preuves | INVALID_ARGUMENTS, NOT_FOUND, SOURCE_UNAVAILABLE | Lecture limitée de deux exports fixés, sans chemin libre |
| `search_official_docs` | query, error_code optionnel, limit 1..5 | références avec URL, résumé, vérifications | INVALID_ARGUMENTS, NOT_FOUND | Lecture index local seulement |
| `get_pipeline_status` | pipeline_id | statut simulé historique legacy | NOT_FOUND | Lecture JSON |
| `get_model_metrics` | model_id | métriques simulées historiques legacy | NOT_FOUND | Lecture |
| `search_runbook` | error_code | procédures legacy | NOT_FOUND | Lecture |
| `get_pipeline_logs` | pipeline_id, run_id | ancien format logs simulés | NOT_FOUND | Lecture |
| `prepare_incident_ticket` | incident_id, reason | proposition seulement | INVALID_ARGUMENTS, NOT_FOUND | **Aucune création/approbation** |
| `prepare_adf_escalation` | pipeline_id du catalogue, Run ID UUID d'un échec existant, reason 15..300 caractères | proposition `PROPOSAL_ONLY`, human_approval_required=True, ticket_created=False | INVALID_ARGUMENTS, NOT_FOUND, SOURCE_UNAVAILABLE | **Lecture/validation seulement, aucune écriture ni approbation** |

La nouvelle interface utilise principalement deux outils Azure, et peut appeler un **troisième outil ADF de proposition d'escalade**, sur demande explicite d'un utilisateur ayant sélectionné un pipeline et un Run ID précis. Le registre reste strict : validation Pydantic, liste blanche, **quatre appels au maximum** dans la nouvelle investigation, données d'origine filtrées avant présentation au LLM.

Les actions de démonstration sur un dossier Azure passent par `business_escalation.py` et nécessitent des **clics humains explicites** et deux rôles simulés distincts. Les identités `alice`, `bob` ne sont **pas** une authentification sécurisée.

## 5. Simulation et changements d'exécution

Les **12 définitions** ne changent jamais au moment d'une simulation. Les nouveaux événements sont ajoutés dans le dossier externe défini par `OPSGUARD_ADF_EXTERNAL_DIR`, en deux fichiers JSONL fixes. Un identifiant UUID corrèle chaque événement d'activité et le statut de son pipeline parent. Plusieurs exécutions successives peuvent passer de SUCCESS à FAILED ou inversement, avec d'autres volumes, horodatages et erreurs.

Commande administrative (hors interface métier) :

```powershell
$env:OPSGUARD_ADF_SOURCE = "external_demo"
python -m scripts.simulate_company_adf --all --activities 90
python -m scripts.simulate_company_adf --pipeline adf_04_inventory --scenario 3200
```

La simulation est **déclenchée par la commande**, et non par un véritable événement Azure. Pour simuler une cadence, l'administrateur peut planifier cette commande dans le Planificateur de tâches Windows. Ne pas lancer deux processus d'écriture concurrents. Le système refuse de dépasser les limites de taille et de lignes, il n'efface pas automatiquement les données.

## 6. Observabilité opérationnelle et sécurité

Événements enregistrés : démarrage, demande de chaque outil, résultat, proposition d'escalade éventuelle, refus de planification, demande/réponse LLM et fin de requête. Les traces contiennent `trace_id`, UTC, catégorie de sélection, paramètres **expurgés** (Run ID seulement sous forme d'empreinte SHA-256 courte, motif libre masqué), durée individuelle de l'outil, statut/résultat catégoriel, nombre d'appels, `iteration_count`, `escalation_decision`, statut final et latence totale. **Pas de prompts, de secrets, de réponses textuelles ni de contenu libre des logs** dans les traces. Le tableau de bord montre les exécutions de pipeline sans les confondre avec les événements d'activité.

Mesures de gouvernance : validation Pydantic, noms de pipelines limités au catalogue, contrôle des chemins/symlinks, bornes de taille et période, aucune écriture par les outils IA, injection de prompt non suivie, causes incertaines signalées, erreurs inconnues sans procédure inventée, refus des demandes de redémarrage, suppression ou approbation.

Limites : modèle local `qwen3:1.7b` peu fiable sur certaines synthèses, BM25 non exhaustif, absence d'authentification réelle, absence de pipelines/Azure réels, horodatages synthétiques, taille de fichiers limitée, non prévu pour un accès public.

## 7. Reproductibilité et évaluation

Versions et artefacts suivis : code Git, `config/enterprise_adf.json`, catalogue avec empreinte SHA, index Microsoft avec SHA, graine du simulateur, jeux de scénarios, rapports `outputs/enterprise_adf_evaluation.json` et traces locales. Les sorties générées et les secrets ne doivent pas être committés.

Commandes :

```powershell
python -m compileall -q app scripts tests
python -m ruff check .
python -m pytest -q -rs
python -m pip check
python -m scripts.evaluate_enterprise_adf --check
```

Le banc de test utilise 12 cas synthétiques étiquetés, sans Ollama : erreurs documentées, code inconnu et exécutions réussies. Les gates à **100 % sur ces cas contrôlés** vérifient qu'une régression dans le retrieval n'est pas promue ; ils ne sont **pas** une preuve de précision générale sur des logs d'entreprise. Les tests live déjà présents doivent continuer à évaluer Qwen3 et le refus des actions non autorisées. Mesures : taux de succès, pertinence de retrieval, code inconnu, refus, appels invalides, moyenne des outils, latence moyenne et P95.

La CI additionnelle `.github/workflows/enterprise-adf-quality.yml` exécute Ruff, pytest, pip check et les gates reproductibles ; elle n'exige ni serveur Ollama, ni compte Azure.

## 8. Livrables Projet 3 et exigences communes

- [x] Scénario métier explicite, utilisateurs, tâches autorisées et interdites.
- [x] Huit outils disponibles, dont trois dédiés au parcours ADF, avec entrées/sorties/permissions/erreurs documentées.
- [x] Validation des arguments et limites d'itération/d'appels.
- [x] Gestion des logs manquants, erreurs inconnues, modèle indisponible.
- [x] Traces opérationnelles et chronologie par interaction, refus compris (dans la limite des écritures de fichiers possibles).
- [x] Cas normaux, échecs, ambiguïtés, demandes interdites.
- [x] Tests pytest, quality gates, CI GitHub Actions. Contrôle de conformité ciblé : `python -m scripts.evaluate_enterprise_compliance --check` (6 cas).
- [x] Approvals distinctes, aucune action d'infrastructure par agent.
- [x] Déploiement local reproductible, documentation de versions et limites.
- [ ] Validation de l'expérience UI sur le Windows de l'utilisateur (à faire après installation).
- [ ] Évaluation manuelle d'un lot d'interprétations Qwen3 (l'évaluation automatique déterministe ne la remplace pas).
- [ ] Rapport académique final de 8–12 pages et démonstration vidéo de 2 minutes (à livrer séparément).

Le projet cible le **Projet 3**, pas les exigences spécifiques RAG vectoriel des Projets 1 ou 2. Docker est une extension facultative. Le `README` du dépôt doit être actualisé avant la publication officielle.

## 9. Démonstration de 2 minutes (suggestion)

1. 0:00–0:20 — Montrer les 12 pipelines immuables et la source externe.
2. 0:20–0:35 — Simuler une nouvelle exécution sur `adf_04_inventory` (CLI admin).
3. 0:35–1:10 — Analyser le `run_id` et visualiser les preuves + Microsoft Learn.
4. 1:10–1:35 — Montrer le cas inconnu et le refus d'inventer une procédure.
5. 1:35–1:50 — Montrer le workflow de demande d'escalade et la séparation opérateur/approbateur.
6. 1:50–2:00 — Afficher traces, tests et quality gates.
