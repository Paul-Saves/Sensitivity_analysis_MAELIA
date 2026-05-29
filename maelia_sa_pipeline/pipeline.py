from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pandas as pd

from .config import DEFAULT_OUTPUT_ROOT, FEATURE_LABELS, TARGET_LABELS
from .data import load_dataset
from .models import sobol_total_from_metamodel, train_decision_tree, train_metamodel
from .stats import discretize_factors, one_factor_anova, two_factor_interaction
from .viz import plot_interaction_heatmap, plot_metamodel_performance, plot_one_factor, plot_regions, plot_sobol_total, plot_tree_figure


def _safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in value)


def _write_html_report(manifest: dict, output_dir: Path) -> Path:
    cards = []
    for target, artifacts in manifest["targets"].items():
        title = TARGET_LABELS.get(target, target)
        cards.append(f"<h2>{title}</h2>")
        for key, label in [
            ("anova_1factor_png", "ANOVA à un facteur"),
            ("anova_2factor_interaction_png", "Interactions à deux facteurs"),
            ("metamodel_performance_png", "Performance du métamodèle"),
            ("sobol_total_png", "Indices de Sobol total"),
            ("decision_tree_regions_png", "Régions sensibles"),
            ("decision_tree_png", "Arbre de décision"),
        ]:
            path = artifacts.get(key)
            if not path:
                continue
            rel = Path(path).relative_to(output_dir)
            cards.append(
                f'<section class="figure-card"><h3>{label}</h3>'
                f'<img src="{rel.as_posix()}" alt="{label} - {title}"></section>'
            )
    warnings = "".join(f"<li>{w}</li>" for w in manifest.get("warnings", []))
    html = f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Rapport d'analyse de sensibilité MAELIA</title>
  <style>
    :root {{ color-scheme: light; --ink:#263238; --muted:#667085; --line:#E5E7EB; --paper:#FAFBFC; --accent:#2A9D8F; }}
    body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; color:var(--ink); background:white; }}
    header {{ padding:40px clamp(24px,6vw,80px) 24px; border-bottom:1px solid var(--line); background:var(--paper); }}
    main {{ padding:28px clamp(24px,6vw,80px) 56px; }}
    h1 {{ margin:0 0 8px; font-size:clamp(28px,4vw,44px); }}
    h2 {{ margin:44px 0 18px; font-size:28px; }}
    h3 {{ margin:0 0 12px; font-size:18px; }}
    p, li {{ color:var(--muted); line-height:1.55; }}
    code {{ background:#EEF2F7; padding:2px 6px; border-radius:4px; }}
    .figure-card {{ margin:18px 0 30px; padding:18px; border:1px solid var(--line); border-radius:8px; background:white; }}
    img {{ max-width:100%; height:auto; display:block; border-radius:6px; }}
    .meta {{ display:grid; gap:6px; margin-top:14px; }}
    .pill {{ display:inline-block; background:#E6F4F1; color:#17685E; padding:5px 9px; border-radius:999px; font-size:13px; }}
  </style>
</head>
<body>
<header>
  <span class="pill">MAELIA Sensitivity Analysis</span>
  <h1>Rapport d'analyse de sensibilité</h1>
  <p>Dataset : <code>{manifest['dataset_path']}</code></p>
  <div class="meta">
    <p>Lignes analysées : {manifest['n_rows']} · Paramètres : {manifest['n_features']} · Run : <code>{manifest['run_id']}</code></p>
  </div>
  {f'<ul>{warnings}</ul>' if warnings else ''}
</header>
<main>
  {''.join(cards)}
</main>
</body>
</html>"""
    path = output_dir / "report.html"
    path.write_text(html, encoding="utf-8")
    return path


def run_analysis(
    log_dir: str | Path,
    dataset_path: str | Path | None = None,
    output_dir: str | Path | None = None,
    targets: list[str] | None = None,
    features: list[str] | None = None,
    n_bins: int = 4,
    sobol_n_mc: int = 2000,
    tree_max_depth: int = 4,
    random_state: int = 42,
) -> dict:
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid4().hex[:8]
    out = Path(output_dir).expanduser() if output_dir else DEFAULT_OUTPUT_ROOT / run_id
    out.mkdir(parents=True, exist_ok=True)

    bundle = load_dataset(log_dir=log_dir, dataset_path=dataset_path, targets=targets, features=features)
    df = bundle.dataframe
    factor_frame = discretize_factors(
        df,
        bundle.feature_columns,
        bundle.categorical_columns,
        bundle.continuous_columns,
        n_bins=n_bins,
    )

    manifest: dict = {
        "run_id": run_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "log_dir": str(Path(log_dir).expanduser()),
        "dataset_path": str(bundle.dataset_path),
        "output_dir": str(out),
        "n_rows": int(len(df)),
        "n_features": int(len(bundle.feature_columns)),
        "features": bundle.feature_columns,
        "targets": {},
        "warnings": bundle.warnings,
        "tables": {},
    }

    anova = one_factor_anova(df, factor_frame, bundle.feature_columns, bundle.target_columns)
    anova_path = out / "anova_1facteur.csv"
    anova.to_csv(anova_path, index=False)
    manifest["tables"]["anova_1factor"] = str(anova_path)

    interactions, matrices = two_factor_interaction(df, factor_frame, bundle.feature_columns, bundle.target_columns)
    interactions_path = out / "anova_2facteurs_interactions.csv"
    interactions.to_csv(interactions_path, index=False)
    manifest["tables"]["anova_2factor_interactions"] = str(interactions_path)

    metamodel_rows = []
    for target in bundle.target_columns:
        target_dir = out / _safe_name(target)
        target_dir.mkdir(parents=True, exist_ok=True)
        target_artifacts: dict[str, str | dict] = {}

        p = plot_one_factor(anova, target, target_dir / f"anova_1facteur_{target}.png")
        target_artifacts["anova_1factor_png"] = str(p)

        matrix = matrices[target]
        matrix_path = target_dir / f"anova_2facteurs_R2_interaction_{target}.csv"
        matrix.to_csv(matrix_path)
        target_artifacts["anova_2factor_interaction_csv"] = str(matrix_path)
        p = plot_interaction_heatmap(matrix, target, target_dir / f"anova_2facteurs_R2_interaction_{target}.png")
        target_artifacts["anova_2factor_interaction_png"] = str(p)

        model, model_metrics = train_metamodel(
            df,
            target,
            bundle.feature_columns,
            bundle.categorical_columns,
            bundle.continuous_columns,
            random_state=random_state,
        )
        model_metrics_row = {"sortie": target, **model_metrics}
        metamodel_rows.append(model_metrics_row)
        target_artifacts["metamodel_metrics"] = model_metrics
        p = plot_metamodel_performance(model_metrics, target, target_dir / f"metamodel_performance_{target}.png")
        target_artifacts["metamodel_performance_png"] = str(p)

        sobol = sobol_total_from_metamodel(
            model,
            df,
            bundle.feature_columns,
            bundle.categorical_columns,
            bundle.continuous_columns,
            target,
            n_mc=sobol_n_mc,
            random_state=random_state,
        )
        sobol_path = target_dir / f"sobol_total_{target}.csv"
        sobol.to_csv(sobol_path, index=False)
        target_artifacts["sobol_total_csv"] = str(sobol_path)
        p = plot_sobol_total(sobol, target, target_dir / f"sobol_total_{target}.png")
        target_artifacts["sobol_total_png"] = str(p)

        tree_result = train_decision_tree(
            df,
            target,
            bundle.feature_columns,
            bundle.categorical_columns,
            bundle.continuous_columns,
            max_depth=tree_max_depth,
            random_state=random_state,
        )
        regions_path = target_dir / f"decision_tree_regions_{target}.csv"
        tree_result.regions.to_csv(regions_path, index=False)
        target_artifacts["decision_tree_regions_csv"] = str(regions_path)
        rules_path = target_dir / f"decision_tree_rules_{target}.txt"
        rules_path.write_text(tree_result.rules_text, encoding="utf-8")
        target_artifacts["decision_tree_rules_txt"] = str(rules_path)
        target_artifacts["decision_tree_metrics"] = tree_result.metrics
        p = plot_regions(tree_result.regions, target, target_dir / f"decision_tree_regions_{target}.png")
        target_artifacts["decision_tree_regions_png"] = str(p)
        p = plot_tree_figure(tree_result, target, target_dir / f"decision_tree_{target}.png")
        target_artifacts["decision_tree_png"] = str(p)

        manifest["targets"][target] = target_artifacts

    metamodel_path = out / "metamodel_metrics.csv"
    pd.DataFrame(metamodel_rows).to_csv(metamodel_path, index=False)
    manifest["tables"]["metamodel_metrics"] = str(metamodel_path)

    report_path = _write_html_report(manifest, out)
    manifest["report_html"] = str(report_path)

    manifest_path = out / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest["manifest_json"] = str(manifest_path)
    return manifest
