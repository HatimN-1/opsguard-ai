
# OpsGuard AI — Scénario et périmètre de l'agent

## 1. Contexte

Dans un environnement MLOps, les pipelines de données et
les modèles de Machine Learning peuvent rencontrer des
incidents : erreurs de schéma, données invalides,
dégradations de métriques ou échecs d'exécution.

L'investigation de ces incidents nécessite généralement
plusieurs opérations : consulter les états techniques,
analyser les métriques, rechercher des procédures et
déterminer si une intervention humaine est nécessaire.

OpsGuard AI est un prototype d'agent intelligent destiné
à assister ce processus.

Les données MLOps sont simulées afin de démontrer
l'orchestration et les contrôles sans dépendre
d'une infrastructure externe.

## 2. Objectif principal

Développer un agent LLM capable d'utiliser plusieurs
outils MLOps de façon contrôlée pour analyser un incident,
présenter les informations disponibles et préparer,
si nécessaire, une proposition d'escalade humaine.

## 3. Objectifs spécifiques

- Consulter l'état d'un pipeline ETL.
- Analyser les métriques d'un modèle ML.
- Rechercher une procédure de résolution.
- Préparer une proposition de ticket d'incident.
- Valider les arguments avant chaque appel d'outil.
- Refuser les outils non autorisés.
- Limiter le nombre d'étapes et d'appels.
- Gérer les erreurs et les ressources introuvables.
- Produire des réponses fondées sur les résultats des outils.
- Tracer les exécutions sans conserver les prompts.
- Mesurer la qualité des appels d'outils et des réponses.
- Conserver une supervision humaine pour les actions sensibles.

## 4. Scénario nominal

Un utilisateur demande :

"Analyse le pipeline etl_orders_daily et consulte
le runbook correspondant à son erreur."

Déroulement attendu :

1. L'agent reçoit la demande.
2. Il sélectionne get_pipeline_status.
3. Le registre valide l'identifiant du pipeline.
4. L'outil retourne les informations simulées.
5. Si un code d'erreur est disponible et qu'une
   procédure est demandée, l'agent doit utiliser
   search_runbook.
6. Les résultats des outils servent à construire
   la réponse.
7. Les informations d'exécution sont tracées.

Le choix du second outil reste piloté par le LLM.
Il peut parfois omettre cet appel ; ce comportement
est évalué dans les benchmarks.

## 5. Outils autorisés

| Outil | Fonction | Effet autorisé |
|---|---|---|
| get_pipeline_status | Consulter un pipeline | Lecture seule |
| get_model_metrics | Consulter les métriques ML | Lecture seule |
| search_runbook | Rechercher une procédure | Lecture seule |
| prepare_incident_ticket | Préparer une proposition | Proposition uniquement |

Les outils fonctionnent sur des données simulées.

## 6. Tâches interdites à l'agent

L'agent ne doit pas :

- Créer ou approuver automatiquement un ticket.
- Modifier ou supprimer un pipeline.
- Modifier un modèle ML déployé.
- Redémarrer un service ou une infrastructure.
- Exécuter des commandes système arbitraires.
- Utiliser un outil absent de la liste blanche.
- Contourner la validation des arguments.
- Ignorer les limites du nombre d'appels.
- Considérer des instructions provenant des résultats
  d'outils comme des commandes système.
- Inventer des métriques ou des procédures.
- Affirmer qu'une action a été exécutée sans preuve.

## 7. Limites d'exécution

L'orchestrateur applique :

- Un maximum de 3 étapes de sélection d'outils.
- Un maximum de 4 appels d'outils.
- Un délai de 180 secondes configuré sur le client
  Ollama par défaut.
- Une validation de la question utilisateur.
- Une validation Pydantic des arguments des outils.
- Une liste blanche des outils disponibles.

Ces contrôles limitent les opérations de l'agent,
mais ne garantissent pas l'absence de toutes les erreurs.

## 8. Supervision humaine

L'outil prepare_incident_ticket retourne uniquement
une proposition.

Une proposition indique notamment :

- status : PROPOSAL_ONLY
- ticket_created : false
- human_approval_required : true

La création et l'approbation simulées de tickets
sont disponibles séparément dans l'API FastAPI.

Les rôles sont simulés pour la démonstration.
Ils ne constituent pas une authentification réelle.

## 9. Résultats attendus

À la fin d'une interaction, l'utilisateur peut obtenir :

- Une réponse d'analyse.
- Les identifiants et informations vérifiés.
- Le statut de l'agent.
- La liste des outils appelés.
- Les indicateurs de réussite ou d'échec des outils.
- Un identifiant de trace.
- Une mesure de latence.

Une exécution terminée n'implique pas nécessairement
que tous les appels d'outils ont réussi.

## 10. Périmètre du prototype

OpsGuard AI constitue une démonstration académique
d'Agentic AI appliquée au MLOps.

Le prototype ne réalise aucune opération sur une
infrastructure MLOps de production.

Les futures intégrations à des outils externes
nécessiteraient une authentification, des contrôles
d'accès et une gestion des risques supplémentaires.
