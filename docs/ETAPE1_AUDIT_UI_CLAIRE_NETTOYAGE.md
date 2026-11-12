# Étape 1 — Audit, interface claire, nettoyage contrôlé

## Périmètre et honnêteté de la démonstration

OpsGuard AI présente le scénario opérationnel Northstar Retail : **12 pipelines ADF fixes**, analyse de journaux, investigation via Qwen3 et escalade supervisée. La **connexion Azure n'est pas réelle** et les journaux restent synthétiques. L'information exacte est placée dans la page **Sources & gouvernance**, sans multiplier les messages de démonstration dans chaque bloc métier. Il serait incorrect d'afficher « Azure connecté » ou une authentification réelle inexistante.

L'interface est conçue comme un portail métier en thème clair ; l'agent n'obtient aucune permission supplémentaire.

## Modifications

- Palette claire persistante configurée par `.streamlit/config.toml` (option native Streamlit).
- CSS applicatif autonome dans `app/dashboard/assets/enterprise.css`, injecté à chaque réexécution avec `st.html(CSS_FILE)` ; retour de compatibilité possible via `st.markdown`.
- Navigation par boutons professionnels avec icônes Material et identité SVG locale. Plus de pictogrammes Unicode des anciennes pages ni de boutons radio ronds.
- Barre latérale réduite à la navigation et aux repères métier. Mention de la simulation conservée dans **Sources & gouvernance** ; pas de déclaration mensongère de connexion Azure.
- Nouveaux scripts d'audit de trace et d'archivage sûr ; **aucune suppression automatique**.

## Installation sous PowerShell

Exécuter à la racine du dépôt `opsguard-ai` (arrêter d'abord Streamlit avec Ctrl+C) :

```powershell
# Sauvegarde des éléments qui vont être remplacés
Compress-Archive -Path ".\app\dashboard\enterprise_app.py", ".\app\dashboard\assets\enterprise.css" `
    -DestinationPath ".\sauvegarde_avant_interface_claire.zip" -Force

# Le ZIP livré doit se trouver à la racine du dépôt
Expand-Archive -Path ".\OpsGuard_AI_Etape1_Audit_UI_Claire.zip" -DestinationPath "." -Force

python -m compileall -q app scripts tests
python -m ruff check .
python -m pytest -q -rs
python -m scripts.evaluate_enterprise_compliance --check
python -m scripts.audit_project3_traces --check
python -m pip check
```

**Note :** si `.streamlit/config.toml` existait déjà avec des réglages voulus, en faire aussi une copie avant extraction. Si l'audit révèle des traces anciennes sans chronologie d'événements, elles sont comptées comme `legacy_without_timeline_count` : ne pas les interpréter comme une erreur de la nouvelle version.

Relancer ensuite Streamlit **depuis la racine** pour qu'il prenne le nouveau thème :

```powershell
$env:OPSGUARD_ADF_SOURCE = "external_demo"
$env:OPSGUARD_ADF_EXTERNAL_DIR = Join-Path (Split-Path (Get-Location).Path -Parent) "opsguard-adf-realistic-workspace"
python -m streamlit run app/dashboard/streamlit_app.py --server.address 127.0.0.1 --server.port 8501
```

Dans le navigateur, effectuer `Ctrl+F5` après relance pour écarter les styles en cache, puis naviguer entre les cinq onglets et changer la sélection de pipeline/run.

## Audit des événements opérationnels

```powershell
python -m scripts.audit_project3_traces --check
```

Le script examine `logs/agent_traces.jsonl` sans exporter de question, de réponse, ni de Run ID. Il vérifie les `trace_id`, l'horodatage, la chronologie `AGENT_STARTED` → outils → conclusion, les refus, la séparation `PROPOSAL_ONLY`, les durées et la présence de champs sensibles interdits. Il écrit des **comptages et catégories uniquement** dans `outputs/project3_trace_audit.json`.

En l'absence de traces, `--check` échoue explicitement. Un audit réussi signifie que les événements enregistrés sont structurés selon le contrat observé ; il **ne démontre pas** la vérité des hypothèses générées par Qwen3 ni une authentification de production.

## Nettoyage sans perte de données

Faire d'abord l'aperçu, puis le déplacement réversible des ZIP d'installation et anciennes sauvegardes ZIP présents à la **racine** du dépôt :

```powershell
python -m scripts.archive_old_zip_files
# Après contrôle de la liste :
python -m scripts.archive_old_zip_files --apply
```

Les ZIP sont **déplacés, jamais détruits**, dans un dossier frère du dépôt nommé `OpsGuard_archives_installation`. Les fichiers `.py`, données, tests, `.venv`, sorties d'évaluation, configurations, Git et le répertoire de journaux ADF externes restent intacts. Les noms déjà présents dans le dossier d'archives ne sont pas écrasés.

Pour inspecter les modifications Git avant tout commit :

```powershell
git status --short
git diff --check
```

## Contrôle visuel final

1. Le thème reste clair en passant de « Centre de contrôle » à « Agent d'investigation » et à « Exécutions & preuves ».
2. Les 12 pipelines, les nombres et les Run IDs visibles restent inchangés (aucun changement de logique métier).
3. Un refus de redémarrage reste un refus, avec trace d'audit.
4. Une proposition d'escalade nécessite un Run ID valide et ne crée pas de ticket.
5. « Sources & gouvernance » donne une description exacte de la provenance et des limites de l'environnement.
