# Azure Data Factory external log investigation — OpsGuard AI

## Objectif

Cette extension est une démonstration de récupération de preuves, recherche documentaire et investigation d'incidents MLOps. Elle **ne déploie, ne modifie, ne corrige ni ne redémarre** les ressources Azure. Deux modes :

1. `external_demo` (par défaut) : **exports JSONL synthétiques à forme Azure Data Factory** dans `../opsguard-adf-external-workspace`, séparément du dépôt, générés par `scripts.seed_adf_workspace`. Aucun compte Azure requis, **aucune exécution ETL réelle**.
2. `azure` : connecteur facultatif en lecture seule avec Log Analytics et `DefaultAzureCredential`. Demande un workspace configuré et les rôles nécessaires ; **non testé sur un vrai tenant dans le pack**.

## Architecture

```text
Streamlit (Azure ADF · Analyse)  ou  Assistant IA
  -> app.agent.orchestrator.run_agent
     -> tool_registry.execute_tool('query_adf_logs')
        -> app.adf_monitor.source
           -> EXTERNAL JSONL (dossier frère du dépôt) ou Azure Log Analytics
     -> tool_registry.execute_tool('search_official_docs')
        -> app.adf_monitor.doc_search (classement lexical BM25)
           -> docs/microsoft_adf_index.json
     -> app.adf_monitor.investigation.compose_adf_investigation
        -> faits filtrés + anomalies + références Microsoft Learn
     -> (facultatif) Qwen3 pour une interprétation distincte NON vérifiée
     -> observability.record_agent_trace
```

Les deux outils supplémentaires s'ajoutent aux **cinq existants** : **sept outils déclarés**, maximum **quatre appels d'outils par exécution** dans l'orchestrateur. La requête KQL est construite avec des identifiants validés, sans chemins ou KQL arbitraires fournis au LLM.

## Schéma et sources Microsoft Learn

La configuration « Resource-Specific » d'Azure Data Factory peut exporter les événements dans les tables `ADFPipelineRun` et `ADFActivityRun`. Les champs normalisés exploités sont `TimeGenerated`, `PipelineName`, `RunId`/`PipelineRunId`, `ActivityName`, `ActivityType`, `Status`, `ErrorCode` et `Level`.

L'index documentaire contient de **courtes synthèses originales en français** de pages Microsoft Learn avec leurs URLs officielles. Il n'est **pas** une copie de la documentation entière, pas un moteur de recherche Internet en direct et pas un moteur vectoriel ; c'est un **corpus documentaire local, vérifiable et daté par la version du dépôt**. Chaque code reconnu est relié à une source réelle et à des vérifications possibles, sans conclusion automatique de cause racine.

Sources :

- [Configurer les diagnostics ADF et Log Analytics](https://learn.microsoft.com/en-us/azure/data-factory/monitor-configure-diagnostics)
- [Table ADFPipelineRun](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/adfpipelinerun)
- [Table ADFActivityRun](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/adfactivityrun)
- [Résolution des erreurs de pipeline ADF](https://learn.microsoft.com/en-us/azure/data-factory/data-factory-troubleshoot-guide)
- [Dépannage des connecteurs ADF](https://learn.microsoft.com/en-us/azure/data-factory/connector-troubleshoot-guide)
- [Dépannage du runtime auto-hébergé](https://learn.microsoft.com/en-us/azure/data-factory/self-hosted-integration-runtime-troubleshoot-guide)
- [SDK Azure Monitor Query pour Python](https://learn.microsoft.com/en-us/python/api/overview/azure/monitor-query-readme)

## Mode démo, sans Cloud

Depuis la racine du dépôt Windows PowerShell :

```powershell
$env:OPSGUARD_ADF_SOURCE = "external_demo"
python -m scripts.seed_adf_workspace --pipelines 12 --runs 3 --activities 80
python -m scripts.investigate_adf "Analyse les logs Azure ADF du pipeline adf_04_inventory sur les 24 heures."
python -m scripts.investigate_adf "Quels pipelines Azure ADF échouent ?"
python -m scripts.investigate_adf "Analyse les logs Azure ADF du pipeline adf_08_inventory."
python -m streamlit run app/dashboard/streamlit_app.py
```

Pour une synthèse complémentaire provenant réellement de Qwen3 (sans mise en œuvre de nouveaux outils ni validation automatique de toutes les hypothèses) :

```powershell
python -m scripts.investigate_adf "Analyse les logs Azure ADF du pipeline adf_04_inventory." --llm
```

À chaque génération, le script ajoute des exécutions dans le répertoire externe à Git. Les fichiers `ADFPipelineRun.jsonl` et `ADFActivityRun.jsonl` utilisent la forme des champs Azure, **mais les valeurs proviennent uniquement du générateur Python**.

## Mode Azure réel (facultatif)

Prérequis : compte Azure, Azure Data Factory, workspace Log Analytics, diagnostics ADF configurés en tables **Resource-Specific**, autorisations de consultation des logs. Les données peuvent mettre un certain temps à apparaître après exécution du pipeline.

```powershell
python -m pip install -r requirements-azure-optional.txt
# Installer Azure CLI si nécessaire, puis se connecter à Azure :
az login
$env:OPSGUARD_ADF_SOURCE = "azure"
$env:OPSGUARD_ADF_WORKSPACE_ID = "VOTRE-WORKSPACE-GUID"
python -m scripts.investigate_adf "Analyse les logs Azure ADF sur les 24 heures."
```

En production, préférer une identité managée ou une identité de service dotée du seul droit de **lire** les journaux de ce workspace. Ne pas enregistrer de secret dans `.env` publié ni dans le dépôt. Le mode Azure réel utilise `LogsQueryClient.query_workspace` (KQL borné et lecture seule). Le connecteur n'a pas été vérifié avec un compte Azure dans ce pack.

## Contrôles de sécurité / limites

- Les requêtes provenant du LLM ne contiennent ni chemin de fichier, ni requête KQL libre, ni opération d'écriture.
- Les fichiers externes autorisés sont exactement `ADFPipelineRun.jsonl` et `ADFActivityRun.jsonl`; protection contre le parcours de chemins et les liens symboliques, taille/ligne bornées.
- L'outil retire `ErrorMessage`, `Input`, `Output`, `Parameters`, `UserProperties` et tout champ non explicitement autorisé avant transmission au LLM.
- Les données externes restent **non fiables** ; ne pas interpréter un texte de log comme une instruction.
- `matching_events` et le taux d'échec sont des informations de la **fenêtre filtrée**, pas des métriques de production certifiées ; le mode Azure réel peut être tronqué par la limite KQL.
- La documentation est indexée hors ligne : une erreur inconnue ne produit pas de résolution inventée. L'absence d'un code dans le corpus ne signifie pas que Microsoft n'a jamais documenté ce problème.
- `--llm` active une interprétation générative facultative, explicitement marquée comme hypothèse non vérifiée ; les faits et URLs restent indépendants du modèle.
- Ne jamais publier l'interface Streamlit sans authentification ni contrôle d'accès.

## Limites explicites et prochaine évolution

1. Index documentaire initial réduit : intégrer d'autres pages Microsoft Learn par une étape d'ingestion revue et versionnée (nettoyage, qualité, dates, re-indexation).
2. Pas de recherche sémantique par embeddings ; BM25 dépend des termes présents, notamment des codes d'erreur.
3. Source externe simulée sur filesystem local ; pour un vrai stockage hors machine, utiliser un service Azure et un connecteur adapté.
4. Le mode Azure réel n'est pas validé en environnement utilisateur : tester avec un workspace de développement, limites de débit, coût et gestion des erreurs réseau.
5. Pas d'écriture ni d'automatisation de remédiation. L'humain reste responsable des actions sensibles.
