# OpsGuard AI — Gouvernance, sécurité et supervision humaine

**Projet :** Intelligent MLOps Incident Management & Observability Agent  
**Version :** Prototype académique  
**Date de référence :** 10 novembre 2026  
**Modèle utilisé :** Qwen3 1.7B via Ollama local

---

## 1. Objectif et périmètre

OpsGuard AI est un prototype d'agent intelligent destiné à assister le diagnostic d'incidents MLOps.

Il permet de consulter l'état de pipelines ETL, d'analyser les métriques de modèles Machine Learning, de rechercher des procédures de résolution et de préparer des propositions de tickets d'incident.

Le projet utilise des données simulées stockées localement. Il n'est pas connecté à une infrastructure MLOps de production.

L'objectif de la gouvernance est de garantir une séparation claire entre l'analyse produite par le modèle de langage, l'exécution d'outils autorisés et les décisions nécessitant une intervention humaine.

## 2. Principes de gouvernance

| Principe | Application dans OpsGuard AI |
|---|---|
| Privilège minimal | Le LLM dispose uniquement de quatre outils autorisés |
| Validation systématique | Les arguments des outils sont contrôlés avec Pydantic |
| Supervision humaine | La création et l'approbation de tickets ne sont pas accessibles au LLM |
| Traçabilité | Les exécutions produisent des traces et des événements horodatés |
| Minimisation des données | Les journaux visent à conserver des métadonnées plutôt que les contenus des conversations |
| Séparation des responsabilités | Le LLM propose des appels, le registre valide et les fonctions Python exécutent |
| Transparence | Les réponses distinguent les faits vérifiés des analyses générées |
| Gestion des échecs | Les erreurs prévues et plusieurs exceptions d'exécution sont traitées explicitement |

Ces principes réduisent les risques, mais ne constituent pas une garantie complète de sécurité.

## 3. Architecture des responsabilités

### 3.1 Utilisateur

L'utilisateur formule une demande de diagnostic ou d'analyse.

Les demandes sont transmises à l'orchestrateur, qui valide notamment leur présence et leur longueur.

### 3.2 Modèle de langage

Le modèle Qwen3 interprète la demande et peut proposer des appels d'outils.

Il ne dispose d'aucun accès direct aux fonctions de création, d'approbation ou de modification d'infrastructure.

### 3.3 Orchestrateur

Le module `app/agent/orchestrator.py` contrôle les échanges avec Ollama, les limites d'exécution, les réponses d'outils et la construction des résultats.

L'orchestrateur applique un maximum de trois étapes de sélection d'outils et de quatre appels d'outils. Une requête finale au LLM peut être effectuée sans exposer de nouveaux outils.

### 3.4 Registre des outils

Le module `app/agent/tool_registry.py` constitue la frontière d'autorisation.

Il vérifie que le nom demandé appartient à la liste blanche et que les arguments respectent le schéma Pydantic correspondant.

### 3.5 Services MLOps simulés

Les fonctions Python interrogent des fichiers JSON locaux contenant les pipelines, les métriques ML, les runbooks et les incidents.

Elles ne manipulent aucune infrastructure de production.

### 3.6 Opérateur et approbateur

La démonstration API prévoit des rôles distincts pour demander et approuver un ticket simulé.

Ces rôles sont contrôlés par l'application, mais leur identité repose sur un en-tête de démonstration. Ils ne constituent pas une authentification sécurisée.

## 4. Matrice des permissions

| Action | Agent LLM | API de démonstration |
|---|---|---|
| Consulter un pipeline | Autorisée | Autorisée |
| Consulter les métriques d'un modèle | Autorisée | Autorisée |
| Rechercher un runbook | Autorisée | Autorisée |
| Préparer une proposition de ticket | Autorisée | Pas d'endpoint dédié |
| Demander la création d'un ticket simulé | Interdite | Rôle opérateur simulé |
| Approuver un ticket simulé | Interdite | Rôle approbateur simulé |
| Supprimer un pipeline | Interdite | Non implémentée |
| Déployer ou modifier un modèle | Interdite | Non implémentée |
| Exécuter une commande système arbitraire | Interdite | Non implémentée |

La liste blanche de l'agent comprend exactement les outils suivants :

`get_pipeline_status`, `get_model_metrics`, `search_runbook` et `prepare_incident_ticket`.

Tout outil inconnu transmis au registre est refusé avec le code `UNKNOWN_TOOL`.

## 5. Processus d'escalade humaine

### 5.1 Identification d'une situation nécessitant une intervention

Les données simulées peuvent signaler qu'une intervention humaine est nécessaire.

Par exemple, le runbook `RB-001`, associé à `SCHEMA_VALIDATION_ERROR`, contient la propriété `human_approval_required: true`.

L'agent doit présenter cette exigence lorsqu'il a effectivement consulté ce runbook.

### 5.2 Proposition de ticket

L'outil `prepare_incident_ticket` prépare uniquement une proposition.

Une proposition valide contient les informations suivantes :

| Champ | Valeur attendue |
|---|---|
| `status` | `PROPOSAL_ONLY` |
| `human_approval_required` | `true` |
| `ticket_created` | `false` |

Une proposition ne représente ni une création de ticket ni une approbation.

### 5.3 Demande et approbation simulées

L'API FastAPI expose séparément les routes `POST /tickets` et `POST /tickets/{ticket_id}/approve`.

Le module `app/tools/incident_tool.py` utilise les rôles de démonstration suivants :

| Utilisateur simulé | Rôle |
|---|---|
| `alice` | Opérateur |
| `charlie` | Opérateur |
| `bob` | Approbateur |
| `eve` | Observateur |

Un opérateur peut soumettre une demande de ticket, qui reçoit le statut `PENDING_APPROVAL`.

Un approbateur peut ensuite approuver une demande en attente, ce qui fait passer son statut à `APPROVED`.

Ces opérations sont simulées et stockées temporairement en mémoire.

**Limite critique :** l'en-tête HTTP `X-Demo-User` peut être fourni par le client. Il ne prouve pas l'identité de l'appelant. Cette API ne doit donc pas être considérée comme sécurisée pour une exposition publique.

## 6. Validation et gestion des erreurs

L'application utilise plusieurs mécanismes complémentaires.

| Situation | Comportement prévu |
|---|---|
| Nom d'outil inconnu | Refus avec `UNKNOWN_TOOL` |
| Arguments non conformes | Refus avec `INVALID_ARGUMENTS` |
| Ressource inexistante | Retour `NOT_FOUND` |
| Exception interne d'un outil | Réponse contrôlée `TOOL_EXECUTION_ERROR` |
| Réponse Ollama malformée | Statut `invalid_response` |
| Erreur HTTP ou timeout Ollama pris en charge | Statut `llm_error` |
| Dépassement des limites d'outils | Statut `limit_reached` |

Le client Ollama par défaut dispose d'un timeout configuré à 180 secondes.

Ces traitements ne couvrent pas nécessairement toutes les exceptions imprévues de l'application. Certaines erreurs intervenant avant la finalisation d'une exécution peuvent également empêcher l'écriture d'une trace complète.

Le statut `completed` signifie que l'agent a terminé son traitement. Il ne garantit ni l'exécution de tous les outils demandés ni la satisfaction complète de l'objectif utilisateur.

## 7. Protection contre les réponses incorrectes

Le module `app/agent/grounded_answer.py` construit des réponses à partir des résultats d'outils ayant réussi.

Il peut notamment restituer les identifiants de pipelines, les états d'exécution, les codes d'erreur, les métriques ML, les références de runbooks et les exigences d'approbation humaine.

Des contrôles supplémentaires visent à détecter certaines contradictions entre les données observées et le texte produit par le modèle.

Lorsque la réponse libre n'est pas jugée suffisamment fiable, le système peut conserver les faits vérifiés et écarter le texte généré.

Les contrôles linguistiques restent heuristiques. Ils peuvent produire des erreurs de classification.

Les instructions présentes dans les résultats des outils sont considérées comme des données non fiables. Les protections existantes sont limitées aux comportements et scénarios effectivement testés.

## 8. Observabilité et confidentialité

### 8.1 Traces d'exécution

Les traces sont enregistrées localement dans :

`logs/agent_traces.jsonl`

Chaque exécution journalisée peut contenir un identifiant `trace_id`, un horodatage UTC, le modèle utilisé, le statut final, la latence et des métadonnées d'appels d'outils.

### 8.2 Chronologie événementielle

Le système prend en charge les événements suivants :

| Événement | Signification |
|---|---|
| `AGENT_STARTED` | Début du traitement |
| `LLM_REQUESTED` | Requête adressée au modèle |
| `LLM_RESPONDED` | Réponse reçue et validée |
| `TOOL_REQUESTED` | Appel d'outil demandé |
| `TOOL_COMPLETED` | Résultat d'outil obtenu |
| `AGENT_COMPLETED` | Traitement terminé |
| `AGENT_FAILED` | Échec traité |
| `LIMIT_REACHED` | Limite d'exécution atteinte |

Les événements sont regroupés au sein d'une même trace et peuvent être consultés dans le dashboard Streamlit.

### 8.3 Minimisation des données

Le format de journalisation exclut les champs contenant directement les questions utilisateur, les réponses du modèle et les arguments des outils.

Les événements détaillés sont filtrés selon une liste de champs autorisés et limités en nombre.

Les métadonnées globales des outils nécessitent toutefois une vigilance supplémentaire : les noms d'outils et les codes d'erreur conservés dans `tools_used` ne bénéficient pas exactement du même filtrage strict que la chronologie événementielle.

Il ne faut donc pas considérer les journaux comme adaptés à des données sensibles sans audit complémentaire.

### 8.4 Conservation et accès

Les répertoires `logs/` et `outputs/` sont exclus du dépôt Git selon la configuration du projet.

Le prototype ne met pas en œuvre de politique automatisée de durée de conservation, de chiffrement des journaux ou de contrôle d'accès avancé aux fichiers locaux.

Ces mécanismes seraient nécessaires dans un environnement réel.

## 9. Registre des risques

| Risque | Niveau estimé | Mesures actuelles | Limite résiduelle |
|---|---|---|---|
| Utilisation d'un outil interdit | Élevé | Liste blanche et refus `UNKNOWN_TOOL` | Les tentatives peuvent toujours être proposées par le LLM |
| Création ou approbation non autorisée | Élevé | Outil LLM limité à la proposition | API de démonstration sans authentification réelle |
| Réponse inexacte ou inventée | Élevé | Restitution des faits et contrôles de contradictions | Vérifications non exhaustives |
| Omission d'un outil requis | Moyen | Instructions d'orchestration et évaluations | Le LLM peut oublier un appel |
| Injection de prompt | Élevé | Séparation des données d'outils et des instructions | Défense incomplète contre les attaques avancées |
| Divulgation dans les journaux | Moyen | Minimisation et filtrage des événements | Contrôles complémentaires nécessaires sur les métadonnées globales |
| Indisponibilité du modèle | Moyen | Timeout et gestion d'erreurs | Dépendance à Ollama local |
| Perte des tickets de démonstration | Faible | Stockage temporaire explicite | État non persistant après redémarrage |

Ces niveaux sont des appréciations qualitatives adaptées au prototype académique. Ils ne résultent pas d'une analyse quantitative de sécurité.

## 10. Tests et résultats expérimentaux

Au 10 novembre 2026, les résultats locaux validés sont les suivants :

| Évaluation | Résultat | Portée |
|---|---|---|
| Suite pytest | 117 tests réussis | Tests automatisés locaux |
| Ruff | Aucune erreur | Vérification statique |
| Escalades déterministes | 7/7 | Protections testées avec clients simulés |
| Escalades Qwen3 réelles | 3/3 | Sélection d'outils sur trois exécutions |
| Respect de la frontière d'autorisation | 3/3 | Aucun outil interdit exécuté dans cette campagne |

Les rapports sont générés localement dans le répertoire `outputs/`.

Le score déterministe ne mesure pas les capacités de raisonnement du modèle.

Le score obtenu avec Qwen3 porte sur un très petit ensemble de scénarios. Il ne doit pas être présenté comme une preuve de fiabilité générale ou comme une garantie de sécurité.

L'évaluation des réponses doit rester distincte de la simple réussite d'exécution des outils.

## 11. Conditions nécessaires avant tout usage réel

Le prototype ne doit pas être déployé tel quel dans un environnement de production.

Une évolution vers un usage réel nécessiterait notamment une authentification forte, des autorisations vérifiées côté serveur, une gestion sécurisée des secrets, une politique de conservation des journaux, une surveillance opérationnelle et des tests adversariaux plus étendus.

Il faudrait également définir un processus de validation humaine adapté aux incidents réels et aux conséquences possibles de chaque action.

Les connexions aux systèmes MLOps externes devraient respecter des permissions minimales et des mécanismes d'audit indépendants du modèle.

## 12. Conclusion

OpsGuard AI illustre une architecture d'agent MLOps dans laquelle le LLM peut analyser des données et proposer des actions, tandis que l'application conserve le contrôle de l'exécution.

La liste blanche des outils, les validations d'arguments, les limites d'exécution, les réponses fondées sur des données vérifiées, les traces événementielles et la séparation des approbations constituent les principaux mécanismes de gouvernance.

Les résultats des tests fournissent des éléments de validation pour le périmètre académique étudié.

Le projet reste un **prototype local, simulé et supervisé**, qui nécessite des protections supplémentaires avant toute utilisation opérationnelle réelle.