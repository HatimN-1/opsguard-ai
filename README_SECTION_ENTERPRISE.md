## OpsGuard AI — Scénario entreprise Azure Data Factory

Le projet 3 est démontré au sein de **Northstar Retail**, entreprise fictive possédant **12 pipelines ETL Azure Data Factory définis et versionnés** (`data/company_adf_catalog.json`). L'agent consulte des exécutions ADF synthétiques dans des **exports JSONL externes** au dépôt, recherche les références Microsoft Learn dans un index documenté et tente une synthèse locale Qwen3 contrôlée. Les 12 pipelines métier ne changent jamais dans la démonstration ; seules les nouvelles traces de leurs exécutions évoluent.

**Interface unique** : `python -m streamlit run app/dashboard/streamlit_app.py`.

**Générer une nouvelle exécution simulée** :
`python -m scripts.simulate_company_adf --pipeline adf_04_inventory --scenario 3200 --activities 90`.

**Quality gates** : `python -m scripts.evaluate_enterprise_adf --check`.

Voir `docs/ENTERPRISE_ADF_PROJECT3_FR.md` pour le schéma, les outils, le modèle de confiance, les tests, les limites et le protocole de soutenance. Aucun compte Azure réel n'est nécessaire ; l'environnement est une démonstration locale sans authentification de production.
