# OpsGuard AI — Journaux détaillés Azure Data Factory (démonstration)

## Objectif et provenance

Ce module génère des **événements synthétiques** dans deux exports JSONL **hors du dépôt** :
`ADFActivityRun.jsonl` et `ADFPipelineRun.jsonl`. Les noms de colonnes suivent les
schémas **Azure Monitor / Log Analytics** documentés par Microsoft. Il ne lit
aucune ressource Azure et aucun identifiant ou jeton de connexion n'est requis.

**Ce ne sont pas des journaux capturés dans Azure.** Les scénarios décrivent des
problèmes techniques réellement documentés par Microsoft Learn. Les messages
sont reformulés et les identifiants sont générés pour l'exercice ; ils ne
constituent pas des preuves d'incidents réels.

### Pourquoi ce ne sont pas de simples lignes de console ?

- Une ligne `ADFActivityRun` correspond à une **exécution d'activité**.
- Une ligne `ADFPipelineRun` correspond à une **exécution de pipeline**.
- Une activité peut contenir `Start`, `End`, `ActivityName`, `ActivityType`,
  `Status`, `ActivityRunId`, `EffectiveIntegrationRuntime`, `LinkedServiceName`,
  `FailureType`, `ErrorCode`, `ErrorMessage`, ainsi qu'un champ `Output` JSON.
- Pour les activités Copy réussies, le simulateur génère des compteurs
  `rowsRead`, `rowsCopied`, `dataRead`, `dataWritten` et `copyDuration`.
- Des branches parallèles sont plausibles : certaines activités réussissent
  même si une autre activité a échoué.

Le lecteur sécurisé `query_adf_logs` **n'envoie jamais** les champs libres
`ErrorMessage`, `Error`, `Input` ou `Output` au LLM. Il les remplace par un
ensemble strict de métadonnées et quelques **compteurs numériques contrôlés**.
Les fichiers JSONL complets restent accessibles localement pour inspection
manuelle par le démonstrateur.

## Scénarios métier

Le fichier `app/adf_monitor/scenarios.json` est le **catalogue du générateur**.
Il ne sert pas de réponse précalculée à l'agent. Celui-ci interroge les logs
puis cherche dans l'index documentaire Microsoft Learn.

| Code | Incident technique documenté | Source |
| --- | --- | --- |
| `2003` | Trop d'activités externes concurrentes | [Guide Data Factory](https://learn.microsoft.com/en-us/azure/data-factory/data-factory-troubleshoot-guide) |
| `2010` | Self-hosted Integration Runtime hors ligne | [Guide Data Factory](https://learn.microsoft.com/en-us/azure/data-factory/data-factory-troubleshoot-guide) |
| `2105` | Type de paramètre incohérent | [Guide Data Factory](https://learn.microsoft.com/en-us/azure/data-factory/data-factory-troubleshoot-guide) |
| `3200` | Azure Databricks renvoie 403 / jeton expiré | [Guide Data Factory](https://learn.microsoft.com/en-us/azure/data-factory/data-factory-troubleshoot-guide) |
| `3201` | Notebook Databricks mal configuré | [Guide Data Factory](https://learn.microsoft.com/en-us/azure/data-factory/data-factory-troubleshoot-guide) |
| `20000` | JRE introuvable pour Parquet/ORC en runtime auto-hébergé | [Guide des connecteurs](https://learn.microsoft.com/en-us/azure/data-factory/connector-troubleshoot-guide) |
| `2200` | Échec de connexion ODBC | [Guide des connecteurs](https://learn.microsoft.com/en-us/azure/data-factory/connector-troubleshoot-guide) |
| `3202` | Limitation du taux de création de jobs Databricks | [Guide Data Factory](https://learn.microsoft.com/en-us/azure/data-factory/data-factory-troubleshoot-guide) |
| `2108` | Appel Web : URL ou connectivité en échec | [Guide Data Factory](https://learn.microsoft.com/en-us/azure/data-factory/data-factory-troubleshoot-guide) |
| `UNLISTED_AZURE_98765` | Erreur **volontairement fictive** pour tester l'incertitude | Aucune source spécifique |

Les documents sont retrouvés au moyen de la recherche BM25 sur les **résumés
sourcés** dans `docs/microsoft_adf_index.json`. Il ne s'agit pas d'une
consultation web en direct, ni d'un RAG sémantique complet.

## Commandes Windows (depuis `opsguard-ai`)

```powershell
$env:OPSGUARD_ADF_SOURCE = "external_demo"
$env:OPSGUARD_ADF_EXTERNAL_DIR = Join-Path (Split-Path (Get-Location).Path -Parent) "opsguard-adf-realistic-workspace"
python -m scripts.seed_adf_workspace --pipelines 12 --runs 3 --activities 120 --seed 42 --reset
python -m scripts.investigate_adf "Analyse les logs Azure ADF du pipeline adf_04_inventory sur les 24 heures."
```

**Attention :** `--reset` remplace uniquement les deux fichiers de tables ADF
existants dans le workspace de démonstration configuré. Il ne supprime pas
le reste du dossier. Utiliser un nouveau dossier si vous voulez conserver
les anciennes simulations.

Le jeu ci-dessus comporte **36 exécutions de pipelines et 4 320 exécutions
d'activités** (soit 4 356 lignes JSONL). L'outil renvoie au maximum
**500 événements dans sa réponse**, mais sur la source JSONL externe il
calcule les statistiques et les anomalies sur l'ensemble de la période
filtrée tant que les limites de lecture ne sont pas dépassées. Les exports
sont bornés en taille et en nombre de lignes pour éviter une lecture sans fin.

Quelques questions utiles :

1. « Quels pipelines Azure ADF sont en échec sur les dernières 24 heures ? »
2. « Analyse les logs d'adf_04_inventory : quelle activité a échoué et dans quel runtime ? »
3. « Est-ce une anomalie Databricks ou un problème du runtime auto-hébergé ? Cite les exécutions. »
4. « Pour le code 3200, retrouve les vérifications officielles Microsoft. »
5. « Quels problèmes ADF n'ont aucun document correspondant dans notre index ? »

## Limites explicites

- Aucun vrai pipeline ADF, compte Azure ou workspace Log Analytics.
- Les messages techniques sont inspirés de docs officielles ; la fréquence
  des incidents et les volumes sont **fictifs**.
- Les activités sont simulées, pas exécutées ; aucune sortie de copie de
  données réelle n'est produite.
- La recherche documentaire est **lexicale sur un index restreint**, pas une
  lecture en ligne de toutes les pages Microsoft Learn.
- Les synthèses facultatives Qwen3 restent des hypothèses contrôlées.
- Le générateur est une fixture de validation du diagnostiqueur, **pas une
  preuve que l'agent a diagnostiqué une panne de production**.

## Sources Microsoft

- [Colonnes de `ADFActivityRun`](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/adfactivityrun)
- [Colonnes de `ADFPipelineRun`](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/adfpipelinerun)
- [Surveiller Azure Data Factory](https://learn.microsoft.com/en-us/azure/data-factory/monitor-data-factory)
- [Résoudre les problèmes Data Factory](https://learn.microsoft.com/en-us/azure/data-factory/data-factory-troubleshoot-guide)
- [Résoudre les problèmes des connecteurs](https://learn.microsoft.com/en-us/azure/data-factory/connector-troubleshoot-guide)
