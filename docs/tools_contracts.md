# OpsGuard AI — Contrats des outils MLOps

## 1. Objectif

Ce document décrit les quatre outils mis à disposition de l'agent OpsGuard AI.

Pour chaque outil, il précise :

- Son objectif et son rôle dans le scénario MLOps.
- Les entrées attendues et leurs contraintes.
- Les données renvoyées.
- Les erreurs possibles.
- Les autorisations et les limites de sécurité.

Les outils utilisent des données simulées et ne sont pas connectés à une infrastructure de production.

## 2. Architecture de validation

Tous les appels d'outils de l'agent passent par le registre :

`app/agent/tool_registry.py`

Ce registre utilise des modèles Pydantic pour vérifier les arguments avant l'exécution.

Les paramètres supplémentaires sont interdits par `extra="forbid"`.

Seuls les quatre outils explicitement autorisés peuvent être exécutés.

### Structure commune d'une réponse réussie

```json
{
  "ok": true,
  "tool": "get_pipeline_status",
  "data": {}
}
```

La propriété `data` contient le résultat réel de l'outil concerné.

### Structure commune d'une réponse en erreur

```json
{
  "ok": false,
  "tool": "get_pipeline_status",
  "error": "INVALID_ARGUMENTS"
}
```

Les erreurs de validation sont renvoyées sans exécuter l'outil demandé.

---

## 3. Outil 1 — get_pipeline_status

### Objectif

Consulter l'état d'un pipeline ETL simulé afin de détecter les échecs et identifier leur code d'erreur.

### Entrée

| Paramètre | Type | Contraintes |
|---|---|---|
| `pipeline_id` | string | Obligatoire, 3 à 80 caractères, lettres minuscules, chiffres et `_` |

Exemple :

```json
{
  "pipeline_id": "etl_orders_daily"
}
```

### Sortie

Exemple issu des données simulées :

```json
{
  "ok": true,
  "tool": "get_pipeline_status",
  "data": {
    "pipeline_id": "etl_orders_daily",
    "name": "Daily Orders ETL",
    "status": "FAILED",
    "last_run": "2026-11-08T08:30:00Z",
    "records_processed": 1500,
    "invalid_records": 245,
    "error_code": "SCHEMA_VALIDATION_ERROR"
  }
}
```

### Erreurs possibles

- `INVALID_ARGUMENTS` : identifiant absent, malformé ou paramètres supplémentaires.
- `NOT_FOUND` : pipeline absent du fichier de données.
- `TOOL_EXECUTION_ERROR` : certaines erreurs de lecture ou d'exécution interceptées par l'orchestrateur.

### Autorisation

**Lecture seule.**

L'agent ne peut ni redémarrer, ni supprimer, ni modifier un pipeline avec cet outil.

**Source des données :** `data/pipelines.json`

---

## 4. Outil 2 — get_model_metrics

### Objectif

Consulter les métriques d'inférence d'un modèle Machine Learning afin d'identifier des anomalies de fonctionnement.

### Entrée

| Paramètre | Type | Contraintes |
|---|---|---|
| `model_id` | string | Obligatoire, 3 à 80 caractères, lettres minuscules, chiffres et `_` |

Exemple :

```json
{
  "model_id": "fraud_detection_v1"
}
```

### Sortie

L'outil fournit notamment :

| Champ | Description |
|---|---|
| `model_id` | Identifiant du modèle |
| `model_name` | Nom du modèle |
| `version` | Version |
| `window_start` | Début de la période observée |
| `window_end` | Fin de la période observée |
| `requests_total` | Nombre total de requêtes |
| `failed_requests` | Nombre de requêtes en échec |
| `invalid_input_requests` | Nombre d'entrées invalides |
| `error_rate_pct` | Pourcentage de requêtes en erreur |
| `invalid_input_rate_pct` | Pourcentage d'entrées invalides |
| `latency_avg_ms` | Latence moyenne |
| `latency_p95_ms` | 95e percentile des latences |
| `latency_sample_size` | Nombre de latences observées |
| `data_mode` | Indique le mode simulé |

Exemple de résultat :

```json
{
  "ok": true,
  "tool": "get_model_metrics",
  "data": {
    "model_id": "fraud_detection_v1",
    "model_name": "Fraud Detection",
    "version": "1.0.0",
    "window_start": "2026-11-08T09:00:00Z",
    "window_end": "2026-11-08T10:00:00Z",
    "requests_total": 1000,
    "failed_requests": 45,
    "invalid_input_requests": 80,
    "error_rate_pct": 4.5,
    "invalid_input_rate_pct": 8.0,
    "latency_avg_ms": 111.5,
    "latency_p95_ms": 150,
    "latency_sample_size": 10,
    "data_mode": "simulated"
  }
}
```

Les pourcentages peuvent être `null` si le nombre de requêtes est nul. Les latences calculées peuvent être `null` si aucun échantillon n'est disponible.

### Erreurs possibles

- `INVALID_ARGUMENTS` : identifiant invalide.
- `NOT_FOUND` : modèle inexistant.
- `TOOL_EXECUTION_ERROR` : certaines erreurs de lecture ou de traitement interceptées par l'orchestrateur.

### Autorisation

**Lecture seule.**

L'outil ne peut pas entraîner, déployer ou supprimer un modèle ML.

**Source des données :** `data/model_metrics.json`

---

## 5. Outil 3 — search_runbook

### Objectif

Retrouver une procédure technique correspondant à un code d'erreur MLOps.

### Entrée

| Paramètre | Type | Contraintes |
|---|---|---|
| `error_code` | string | Obligatoire, 3 à 80 caractères, lettres, chiffres et `_` |

Exemple :

```json
{
  "error_code": "SCHEMA_VALIDATION_ERROR"
}
```

La recherche normalise le code en majuscules.

### Sortie

L'outil renvoie une liste de procédures contenant notamment :

- `runbook_id`
- `error_code`
- `title`
- `version`
- `severity`
- `description`
- `diagnostic_steps`
- `human_approval_required`
- `source`

Exemple simplifié d'une réponse réussie :

```json
{
  "ok": true,
  "tool": "search_runbook",
  "data": [
    {
      "runbook_id": "RB-001",
      "error_code": "SCHEMA_VALIDATION_ERROR",
      "title": "ETL Schema Validation Failure",
      "severity": "HIGH",
      "human_approval_required": true
    }
  ]
}
```

Cet exemple affiche seulement quelques champs de la procédure ; la réponse réelle contient également les étapes de diagnostic et les autres métadonnées.

### Erreurs possibles

- `INVALID_ARGUMENTS` : code d'erreur invalide.
- `NOT_FOUND` : aucune procédure correspondante.
- `TOOL_EXECUTION_ERROR` : certaines erreurs de lecture interceptées par l'orchestrateur.

### Autorisation

**Lecture seule.**

L'agent peut consulter les procédures, mais ne peut pas exécuter automatiquement leurs recommandations.

Le champ `human_approval_required` indique qu'une intervention humaine peut être nécessaire. Il ne déclenche pas lui-même une approbation.

**Source des données :** `data/runbooks.json`

---

## 6. Outil 4 — prepare_incident_ticket

### Objectif

Préparer une proposition de ticket à partir d'un incident simulé.

Cet outil sert à illustrer l'escalade vers une supervision humaine.

### Entrées

| Paramètre | Type | Contraintes |
|---|---|---|
| `incident_id` | string | Format `INC-000` avec exactement trois chiffres |
| `reason` | string | Obligatoire, 10 à 500 caractères |

Exemple :

```json
{
  "incident_id": "INC-001",
  "reason": "Investigate the ETL schema validation failure"
}
```

### Sortie

Exemple :

```json
{
  "ok": true,
  "tool": "prepare_incident_ticket",
  "data": {
    "incident_id": "INC-001",
    "reason": "Investigate the ETL schema validation failure",
    "status": "PROPOSAL_ONLY",
    "human_approval_required": true,
    "ticket_created": false
  }
}
```

### Erreurs possibles

- `INVALID_ARGUMENTS` : identifiant incorrect, raison trop courte ou trop longue.
- `NOT_FOUND` : incident inexistant.
- `TOOL_EXECUTION_ERROR` : certaines erreurs de lecture interceptées par l'orchestrateur.

### Autorisation

**Proposition uniquement.**

Cet outil ne crée aucun ticket et n'approuve aucune demande.

Les opérations simulées de création et d'approbation sont séparées du registre d'outils LLM.

Elles sont accessibles via des endpoints FastAPI utilisant des rôles de démonstration.

Ces rôles ne constituent pas une authentification sécurisée.

**Source des données :** `data/incidents.json`

---

## 7. Matrice récapitulative des permissions

| Fonction | Agent LLM | API de démonstration |
|---|---|---|
| Lire un pipeline | Autorisé | Autorisé |
| Consulter les métriques ML | Autorisé | Autorisé |
| Rechercher un runbook | Autorisé | Autorisé |
| Préparer une proposition | Autorisé | Non exposé comme endpoint dédié |
| Demander un ticket simulé | Non autorisé | Opérateur simulé |
| Approuver un ticket simulé | Non autorisé | Approbateur simulé |
| Supprimer un pipeline | Non autorisé | Non implémenté |
| Modifier une infrastructure | Non autorisé | Non implémenté |

Les permissions de démonstration sont appliquées côté application à partir de rôles prédéfinis.

L'en-tête HTTP `X-Demo-User` ne prouve pas l'identité d'un utilisateur.

---

## 8. Erreurs et limites globales

### Erreurs du registre

| Code | Signification |
|---|---|
| `UNKNOWN_TOOL` | Outil absent de la liste blanche |
| `INVALID_ARGUMENTS` | Arguments non conformes au schéma |
| `NOT_FOUND` | Ressource ou procédure introuvable |
| `TOOL_EXECUTION_ERROR` | Certaines exceptions d'exécution interceptées |

### Limites de l'orchestrateur

- Au maximum 3 étapes de sélection d'outils.
- Au maximum 4 appels d'outils.
- Validation Pydantic avant l'exécution.
- Délai configuré de 180 secondes sur le client Ollama par défaut.
- Aucun outil de modification d'infrastructure.
- Aucun outil d'approbation automatique de ticket.

Une expiration de délai Ollama ou une erreur HTTP prise en charge peut produire le statut `llm_error`.

Une limite dépassée peut produire le statut `limit_reached`.

Ces mécanismes ne couvrent pas encore toutes les exceptions imprévues.

---

## 9. Traçabilité et validation

Les exécutions de l'agent produisent des métadonnées contenant :

- Le statut de traitement.
- Les noms des outils appelés.
- Le succès ou l'échec des appels.
- Les codes d'erreur.
- Un identifiant de trace.
- La latence de l'exécution.

Les prompts, les réponses et les arguments d'outils ne sont pas conservés dans les traces JSONL.

Les tests automatisés couvrent les appels autorisés, les erreurs de validation, les outils inconnus et les tentatives d'actions interdites.

## 10. Conclusion

OpsGuard AI fournit quatre outils contrôlés, cohérents avec le scénario de diagnostic et de gestion d'incidents MLOps.

Chaque outil dispose d'un contrat d'entrée, d'un résultat défini, d'erreurs identifiables et de permissions explicites.

La simulation permet de vérifier le comportement de l'agent sans dépendre d'une infrastructure de production.

L'escalade humaine est représentée par une proposition de ticket et un mécanisme distinct d'approbation simulée.
