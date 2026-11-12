# OpsGuard AI — étape 1 : audit des traces

## Résultat observé (12/11/2026)

- `ruff` : PASS ; `pytest` : 335 passed, 2 skipped ; conformité : 6/6 PASS.
- Audit des traces : **FAIL** ; `records_checked=1643`, `modern_timeline_count=1227`, `legacy_without_timeline_count=416`.
- Écarts : `TOOL_DURATION_MISSING=27` et `TOOL_SELECTION_UNDOCUMENTED=27`.

**Ne pas confondre les deux compteurs** : ils peuvent désigner les mêmes appels d'outil sous deux aspects.
L'historique legacy est un sujet distinct du défaut de métadonnées. Ne jamais inventer a posteriori une durée ou un motif de sélection.

## Diagnostic en lecture seule

Copier `scripts/diagnose_trace_gaps_readonly.py` dans le projet, puis dans PowerShell depuis sa racine :

```powershell
python .\scripts\diagnose_trace_gaps_readonly.py --source .\logs\agent_traces.jsonl --output .\outputs\trace_gaps_diagnostic.json
if ($LASTEXITCODE -ne 0) { throw "Diagnostic des traces impossible" }
```

Le programme n'affiche que des numéros de ligne et catégories d'événement. Il ne conserve pas et n'affiche pas les prompts, arguments, Run IDs, réponses ou identifiants de traces. Il n'écrit que le fichier de **synthèse** indiqué via `--output`.

Le contrôle officiel peut imposer des champs ou des événements différents. Si ses chiffres diffèrent de ce diagnostic, **le contrôle officiel fait foi** : inspecter ses règles dans `scripts/audit_project3_traces.py` avant toute modification.

## Correctif de fond à réaliser dans le code en vigueur

1. Sur le **même chemin de code** que les 27 appels, enregistrer au moment de `TOOL_REQUESTED` une catégorie de sélection autorisée (`selection_source` ou nom exact exigé par l'audit), et au moment de `TOOL_COMPLETED` une durée mesurée avec `time.perf_counter()`, même si le résultat est une erreur.
2. Vérifier que `make_agent_event()` et `sanitize_event_timeline()` **conservent effectivement ces champs** dans leur liste blanche. Ne pas loguer les valeurs libres de requête.
3. Ajouter des tests d'intégration pour succès, `INVALID_ARGUMENTS`, `NOT_FOUND`, timeout, refus et escalade proposée.
4. Les 416 anciennes traces sans timeline restent identifiées `legacy`. Ne pas les enrichir artificiellement. Documenter leur couverture limitée.
5. Rejouer un audit sur de **nouvelles traces** propres pour confirmer la correction et conserver le bilan historique à part. Ne pas effacer ni réécrire les journaux originaux.

## Quality gate : empêcher les faux verts

Un affichage `audit_pass: False` ne signifie pas que la commande PowerShell globale a échoué si les commandes continuent après un `exit code` non nul. Utiliser explicitement :

```powershell
python -m scripts.audit_project3_traces --check
if ($LASTEXITCODE -ne 0) { throw "QUALITY GATE FAIL : traces" }
```

Appliquer cette vérification après chaque commande critique (`ruff`, `pytest`, `evaluate_enterprise_compliance`, audit, `pip check`).

## Audit de présentation / CSS Streamlit

Si la navigation ou le rerun annule parfois l'apparence claire, vérifier que la feuille de style est injectée **à chaque exécution** depuis l'entrée de l'application, sans dépendre d'une branche de navigation. Utiliser la méthode compatible avec la version installée de Streamlit (par exemple `st.html` pour du CSS lorsqu'elle est disponible), et laisser le thème général dans `.streamlit/config.toml`. Ne pas masquer la provenance synthétique dans la section de gouvernance.

## Important

Cette archive est un **outil de diagnostic non destructif**, pas un patch qui modifie l'orchestrateur : le dernier code source de l'application n'était pas joint à cet échange. Modifier ce code à l'aveugle risquerait de casser les 335 tests.
