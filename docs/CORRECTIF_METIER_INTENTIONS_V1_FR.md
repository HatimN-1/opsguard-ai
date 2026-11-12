# OpsGuard AI — Correctif métier « intent & evidence » V1

## Objectif

Réparer les défauts observés dans les tests métier T01–T04, B01–B04 et C01–C03 :
rapport générique d'incidents pour toutes les intentions, mauvaise prise en compte
des codes exclus, questions « pipeline sélectionné » non résolues, comparaison
de Run IDs absente et recherche documentaire inutile pour les demandes de statut.

Le catalogue des **12 pipelines ADF** est figé et **inchangé**. Les fichiers JSONL
externes sont lus uniquement, jamais régénérés ou modifiés par ce correctif.
Les erreurs sont **synthétiques**, et aucun pipeline Azure réel n'est exécuté.

## Comportements livrés

1. **`LATEST_STATUS`** : un tableau déterministe des douze derniers Run IDs,
   horodatages et statuts, sans Qwen ni recherche documentaire.
2. **`RUN_COMPARISON`** : les N derniers runs (quatre pour la question de test),
   dans l'ordre décroissant. Le code demandé pour calculer la récurrence ne
   filtre **pas** les autres runs nécessaires à la comparaison.
3. **`RECURRENCE`** : répétition d'un **code sur des Run IDs distincts** ; la
   cause racine identique n'est jamais déduite automatiquement.
4. **`INCIDENT_DIAGNOSIS`** : les codes explicitement demandés et exclus sont
   réellement filtrés dans `query_adf_logs` et dans les documents consultés.
   Les activités responsables figurent dans les lignes d'incident.
5. **Anaphores et menu** : un contexte précis peut être repris pour « cette
   erreur » ; si plusieurs codes sont possibles, le système demande un code.
   Avec « Tous les pipelines » et « pipeline sélectionné », l'agent exige une
   sélection précise au lieu d'analyser toute l'entreprise silencieusement.
6. **LLM** : contrôle additionnel des Run IDs inventés, vérifications humaines
   présentées comme réalisées, preuves causales non établies, statuts « en cours »
   non observés, documentation prétendument inexistante sur Internet et
   négation fausse d'erreurs présentes. Le garde-fou reste **heuristique** :
   `ACCEPTED` ne certifie **pas** la fidélité sémantique.

La limite existante de **quatre appels d'outils** est conservée. Les réponses
structurées sont calculées même si Ollama ne répond pas.

## Installation Windows PowerShell

Depuis `opsguard-ai`, Streamlit arrêté avec `Ctrl+C` :

```powershell
$zip = ".\OpsGuard_AI_Correctif_Investigations_Metier_V1.zip"

Compress-Archive -Path ".\app\adf_monitor", ".\app\agent\tool_registry.py", ".\app\dashboard\enterprise_app.py", ".\tests" -DestinationPath ".\sauvegarde_avant_correctif_metier.zip" -Force

Expand-Archive -Path $zip -DestinationPath "." -Force

python -m compileall -q app scripts tests
python -m ruff check .
python -m pytest -q -rs
python -m scripts.evaluate_enterprise_llm --check
python -m pip check
git diff --check
```

Si Ruff propose un **I001** sur un fichier livré, appliquer uniquement sa
correction sûre (`python -m ruff check . --fix`), puis relancer Ruff et pytest.
Les anciennes alertes CRLF et les deux tests ignorés pour les liens symboliques
Windows ne nécessitent pas de modifier la logique applicative.

**Résultat de contrôle disponible ici** : 98 tests ciblés réussis, dont les 22
nouveaux tests métier, et 12/12 scénarios de récupération hors ligne validés.
Ce n'est pas un résultat du modèle Qwen3 sur ton ordinateur. Le contrôle
complet des 270 anciens tests doit être relancé sur ton installation Windows
(soit environ 292 tests réussis attendus si rien d'autre n'a changé).

## Vérification dans l'interface métier

Lancer comme précédemment :

```powershell
$env:OPSGUARD_ADF_SOURCE = "external_demo"
$env:OPSGUARD_ADF_EXTERNAL_DIR = Join-Path (Split-Path (Get-Location).Path -Parent) "opsguard-adf-realistic-workspace"
python -m streamlit run app/dashboard/streamlit_app.py --server.address 127.0.0.1 --server.port 8501
```

**Test 1** — `Tous les pipelines` :

> Pour chacun des 12 pipelines de Northstar Retail, affiche sa dernière
> exécution : nom, Run ID, date UTC et statut exact.

Attendu : 12 lignes, **une recherche de logs, zéro recherche documentaire**.
Statut Qwen3 `NOT_REQUESTED` (volontaire pour cette question factuelle).

**Test 2** — Choisir `adf_04_inventory` :

> Analyse uniquement le code d'erreur 3200. Exclue du rapport les événements
> et documents du code 20000.

Attendu : aucun incident ni document `20000`, uniquement les événements
`3200`. Les totaux concernent la sélection **filtrée**, pas tous les runs.

**Test 3** — Même pipeline :

> Compare les quatre dernières exécutions de adf_04_inventory. Cite les Run IDs,
> statuts et codes. Indique combien de runs distincts portent le code 3200.

Attendu : quatre lignes comprenant éventuellement les runs réussis et les
runs en erreur, triées de la plus récente à la plus ancienne. Une recherche
de logs, zéro recherche documentaire. Pas de réponse libre Qwen3 nécessaire.

**Test 4** — Même pipeline :

> Pour les erreurs 3200 et 20000, sépare les faits observés et les hypothèses
> Microsoft Learn. Ne présente aucune cause racine comme confirmée.

Attendu : uniquement les deux codes recherchés, les docs pertinentes si elles
sont présentes dans l'index, et aucune réparation déclenchée.

**Test 5** — Remettre `Tous les pipelines` et demander « Analyse uniquement
cette exécution ». Attendu : **message demandant un Run ID**, pas de recherche
globale de 4 447 événements.

## Limites connues

- Le routeur d'intentions repose sur un ensemble **borné d'expressions
  françaises** ; il n'est pas un interpréteur universel de toutes les demandes.
- Le format des questions non reconnues garde la route de diagnostic générique.
- La restitution des Run IDs est bornée aux **200** derniers Run IDs issus du
  filtre, et la recherche externe respecte ses limites de taille et d'événements.
- La documentation Microsoft est un **index local référencé**, pas une recherche
  web en temps réel. `NOT_SEARCHED_TOOL_LIMIT` reste possible sur une enquête
  globale avec de nombreux codes d'erreur.
- Qwen3 reste un petit modèle local ; des erreurs sémantiques peuvent encore
  franchir les contrôles. Une revue humaine des diagnostics sensibles reste
  nécessaire.
- Ce correctif n'ajoute **ni authentification réelle, ni connecteur Cloud, ni
  actions de réparation**.

## Réversibilité

En cas de régression sur ton environnement, arrêter Streamlit et restaurer la
sauvegarde ZIP réalisée avant installation. Conserver les rapports V1/V2/V2.1
existants ; ce correctif ne doit pas être présenté comme faisant partie de
ces anciennes expériences.
