# Pipeline web d’analyse de sensibilité MAELIA

Cette brique lance une analyse complète à partir d’un répertoire de logs MAELIA et du `dataset_metamodel.csv` exporté par le notebook de simulation `batch_simulations_smt_terrainSA.ipynb`.

Le dataset est indispensable : les logs seuls contiennent les sorties du modèle, mais pas la matrice de paramètres `xt` nécessaire aux ANOVA, aux indices de Sobol et aux arbres de décision. Le notebook `batch_simulations_smt_terrainSA.ipynb` copie maintenant automatiquement ce dataset dans `simulations/log_terrainSA/dataset_metamodel.csv` lors de l’export final.

## Lancer l’application web

```bash
cd /Users/benjamin/files/Repositories/Sensitivity_analysis_MAELIA
uvicorn maelia_sa_pipeline.api:app --reload --host 127.0.0.1 --port 8000
```

Interface utilisateur : http://127.0.0.1:8000/

Documentation API interactive : http://127.0.0.1:8000/docs

## Interface web

La page d’accueil permet de saisir le chemin du répertoire de logs, de préciser éventuellement le chemin du `dataset_metamodel.csv`, puis de lancer l’analyse. Les résultats sont affichés directement dans l’interface : scores R²/Q², figures par sortie, régions sensibles, liens vers les règles et rapport HTML complet.

## Exemple de requête

```bash
curl -X POST http://127.0.0.1:8000/analyses \
  -H "Content-Type: application/json" \
  -d '{
    "log_dir": "/Users/benjamin/files/Repositories/Sensitivity_analysis_MAELIA/simulations/log_terrainSA",
    "sobol_n_mc": 2000,
    "tree_max_depth": 4
  }'
```

La réponse contient un `manifest_json`, un `report_html`, les tableaux CSV et les figures PNG. Par défaut, les résultats sont écrits dans `analysis/web_runs/<run_id>/`.

## Analyses générées

- ANOVA à un facteur : barres de R² par paramètre.
- ANOVA à deux facteurs : heatmap du R² d’interaction uniquement.
- Sobol total : estimation via métamodèle ExtraTrees entraîné sur le dataset exporté, avec affichage séparé du R² d’entraînement et du Q² de test.
- Arbres de décision : régions locales sensibles, règles et figures lisibles.

## Ligne de commande sans serveur

```bash
python -m maelia_sa_pipeline.cli \
  --log-dir /Users/benjamin/files/Repositories/Sensitivity_analysis_MAELIA/simulations/log_terrainSA
```
