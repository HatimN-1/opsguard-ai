# OpsGuard AI — Initialisation du projet

Socle de depart pour un projet d'agent intelligent d'aide au diagnostic d'incidents Data/ML.

> Phase 1 uniquement : API de sante, tests, CI, structure de projet. Les outils, l'agent LLM et MLflow seront ajoutes aux phases suivantes.

## Prerequis

- Windows 10 avec VS Code et Python 3.11 ou 3.12 conseille
- Git
- Docker Desktop (facultatif pendant cette phase)

## Installation (PowerShell de VS Code)

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m uvicorn app.api.main:app --reload
```

Ouvrir http://127.0.0.1:8000/health et http://127.0.0.1:8000/docs.

## Verification du code

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest -q
```

## Etapes suivantes

1. Donnees simulees et contrats des outils
2. Outils Python et tests
3. Agent LLM et permissions
4. Evaluation, MLflow et quality gates
5. Interface Streamlit, monitoring et livraison

## Confidentialite

Ne jamais pousser de `.env`, de donnees personnelles ni de cles API sur GitHub. Utiliser `.env.example` sans secret.
