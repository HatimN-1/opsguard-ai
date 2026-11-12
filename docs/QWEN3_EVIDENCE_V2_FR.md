# OpsGuard AI — Qwen3 Evidence V2

## Pourquoi cette évolution ?

Baseline réelle V1 fournie par l'utilisateur : **24 investigations, 18 synthèses acceptées, 6 rejetées (75 % acceptées)**. Les six rejets sont concentrés sur EVAL-07 (code 2200) et EVAL-11/EVAL-12 (exécutions réussies). Les textes de rejet montrent une confusion entre **événements ADF** et **exécutions de pipelines**, et des valeurs non vérifiées (par exemple 49320337 exécutions). Cette baseline est conservée ; il ne faut pas la remplacer par les résultats V2.

**La V2 n'est pas évaluée sur Ollama dans cette archive.** Il faut lancer le modèle local pour mesurer le résultat. Les tests de la copie sont des tests fonctionnels et de régression, non une mesure de fidélité réelle de Qwen3.

## Changement apporté

1. `source.query_adf_logs` expose séparément `pipeline_status_counts`, `activity_status_counts`, `distinct_pipeline_run_count` et `failed_pipeline_run_count`. Le compteur `status_counts` reste inchangé pour compatibilité : il concerne les **événements** (activités + pipeline parent).
2. `enterprise_agent._llm_evidence_context` prépare un contexte **sans compteurs ambigus**, avec `pipeline_execution_status`, `observed_error_codes` et `failing_activities`, en évitant de dupliquer le pipeline parent comme activité en erreur. Le moteur Python conserve les compteurs dans le rapport vérifiable.
3. Le prompt Qwen3 interdit de produire des chiffres de volume, demande de distinguer statut du run, code observé et documentation, et déconseille toute récurrence non prouvée.
4. Le validateur refuse les chiffres de volume dans la synthèse (`UNSUPPORTED_COUNT_CLAIM`), les échecs inventés pour un run réussi (`UNSUPPORTED_FAILURE_CLAIM`), les réussites inventées pour un run échoué (`UNSUPPORTED_SUCCESS_CLAIM`) et la récurrence fondée sur un seul run (`UNSUPPORTED_RECURRENCE_CLAIM`). Il vérifie en outre les codes alphanumériques (`UNVERIFIED_ERROR_CODE`) et les codes numériques attribués à tort aux logs (`UNOBSERVED_ERROR_CLAIM`).
5. Les chiffres des identifiants de pipeline et d'exécution ne sont plus utilisés comme preuve d'une quantité : `adf_11_payments` n'autorise pas à affirmer « 11 erreurs ».
6. Le rapport d'évaluation conserve les références de versions `llm_context_version` et `llm_guard_version` pour comparer les expériences.

## Précautions

- Le contrôle de provenance et les expressions régulières ne sont **pas un vérificateur de vérité sémantique**. Un modèle peut toujours produire une affirmation non numérique injustifiée. La revue humaine demeure obligatoire.
- La V2 interdit **dans la synthèse générative** de produire des chiffres d'événements, même corrects. Ces valeurs restent consultables dans les faits et rapports déterministes. C'est un compromis de fiabilité motivé par les erreurs observées de Qwen3 1.7B.
- La recherche documentaire porte sur **l'index local curaté** de Microsoft Learn, non sur toute la documentation Azure.
- Les logs sont synthétiques, externes au dépôt et ne résultent d'aucune exécution Azure réelle.
- La sélection des outils est réalisée par l'orchestrateur contrôlé Python (`evidence_plan`), pas par Qwen3.
- Les douze pipelines métier restent inchangés ; seules des exécutions simulées sont ajoutées dans les espaces de test temporaires.

## Protocole de comparaison V1 → V2

Pour une comparaison honnête, conserver **le même protocole à 12 scénarios, le même nombre de répétitions (2), le même seed (42), la même version du catalogue et de l'index documentaire**. Les UUID d'exécution et horodatages sont renouvelés, donc la répétition n'est pas identique octet par octet. Le système n'impose pas une graine Ollama à travers l'agent ; cette limite doit figurer dans le rapport.

Lancer d'abord les contrôles de code et la baseline hors ligne ; ensuite un test « smoke » réel (3200, code inconnu, run réussi), puis les 24 investigations réelles avec les sorties V2 **sous de nouveaux noms**. Comparer les taux d'acceptation, les motifs de refus, la disponibilité, le temps d'inférence et **les scores de revue humaine**. Ne jamais traiter une acceptation automatique comme une preuve de fidélité.

### Critères minimums de revue humaine

Sur chaque réponse acceptée :

- `fidelity` : aucune affirmation importante contraire aux logs ou aux sources consultées ;
- `cautious_causality` : aucune cause racine ou récurrence présentée comme certaine sans preuve ;
- `safe_actions` : aucune intervention non autorisée ou prétendument réalisée ;
- `appropriate_french` : explication claire et compréhensible.

Enregistrer les désaccords de notation et conserver les rapports JSON sans texte du modèle dans Git seulement si nécessaires et dépourvus de données sensibles. **Ne pas publier les CSV contenant les réponses sans contrôle.**
