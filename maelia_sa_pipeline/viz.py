from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from sklearn.tree import plot_tree

from .config import FEATURE_LABELS, PALETTE, TARGET_LABELS


def setup_style() -> None:
    sns.set_theme(style="whitegrid", context="talk")
    plt.rcParams.update({
        "figure.facecolor": "white",
        "axes.facecolor": PALETTE["paper"],
        "axes.edgecolor": "#CBD5E1",
        "axes.labelcolor": PALETTE["ink"],
        "xtick.color": PALETTE["ink"],
        "ytick.color": PALETTE["ink"],
        "grid.color": PALETTE["grid"],
        "font.size": 11,
        "axes.titleweight": "bold",
        "axes.titlesize": 15,
    })


def label(name: str) -> str:
    return FEATURE_LABELS.get(name, TARGET_LABELS.get(name, name))


def _save(fig, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=190, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def plot_one_factor(anova: pd.DataFrame, target: str, path: Path, top_n: int = 12) -> Path:
    setup_style()
    data = anova[anova["sortie"] == target].head(top_n).copy()
    data["label"] = data["parametre"].map(label)
    data = data.sort_values("R2", ascending=True)
    fig, ax = plt.subplots(figsize=(10.5, max(5, 0.42 * len(data) + 1.8)))
    colors = sns.color_palette("crest", n_colors=max(3, len(data)))
    ax.barh(data["label"], data["R2"], color=colors, edgecolor="white", linewidth=1.2)
    ax.set_xlabel("Part de variance expliquée seule (R²)")
    ax.set_ylabel("")
    ax.set_title(f"Paramètres les plus influents — {label(target)}")
    ax.set_xlim(0, max(0.02, data["R2"].max() * 1.18))
    for container in ax.containers:
        ax.bar_label(container, labels=[f"{v:.2f}" for v in data["R2"]], padding=4, fontsize=9)
    ax.text(
        0.0, -0.18,
        "Lecture : plus la barre est longue, plus ce paramètre sépare des comportements différents.",
        transform=ax.transAxes,
        color=PALETTE["muted"],
        fontsize=9,
    )
    sns.despine(left=True, bottom=False)
    return _save(fig, path)


def plot_interaction_heatmap(matrix: pd.DataFrame, target: str, path: Path, top_n: int = 16) -> Path:
    setup_style()
    scores = matrix.sum(axis=1).sort_values(ascending=False)
    keep = list(scores.head(min(top_n, len(scores))).index)
    mat = matrix.loc[keep, keep].copy()
    mat.index = [label(c) for c in mat.index]
    mat.columns = [label(c) for c in mat.columns]
    mask = np.triu(np.ones_like(mat, dtype=bool))
    fig, ax = plt.subplots(figsize=(12, 10))
    sns.heatmap(
        mat,
        mask=mask,
        cmap=sns.color_palette("rocket_r", as_cmap=True),
        vmin=0,
        square=True,
        linewidths=0.6,
        linecolor="white",
        cbar_kws={"label": "R² d'interaction"},
        ax=ax,
    )
    ax.set_title(f"Couples de paramètres qui interagissent — {label(target)}")
    ax.set_xlabel("")
    ax.set_ylabel("")
    ax.tick_params(axis="x", rotation=40, labelsize=9)
    ax.tick_params(axis="y", rotation=0, labelsize=9)
    ax.text(
        0.0, -0.13,
        "Lecture : une case foncée indique que le rôle d'un paramètre dépend fortement de l'autre.",
        transform=ax.transAxes,
        color=PALETTE["muted"],
        fontsize=9,
    )
    return _save(fig, path)


def plot_sobol_total(sobol: pd.DataFrame, target: str, path: Path, top_n: int = 12) -> Path:
    setup_style()
    data = sobol[sobol["sortie"] == target].head(top_n).copy()
    data["label"] = data["parametre"].map(label)
    data = data.sort_values("ST", ascending=True)
    fig, ax = plt.subplots(figsize=(10.5, max(5, 0.42 * len(data) + 1.8)))
    colors = sns.color_palette("mako", n_colors=max(3, len(data)))
    ax.barh(data["label"], data["ST"], color=colors, edgecolor="white", linewidth=1.2)
    ax.set_xlabel("Indice de Sobol total estimé")
    ax.set_ylabel("")
    ax.set_title(f"Influence globale avec interactions — {label(target)}")
    ax.set_xlim(0, max(0.02, data["ST"].max() * 1.18))
    for container in ax.containers:
        ax.bar_label(container, labels=[f"{v:.2f}" for v in data["ST"]], padding=4, fontsize=9)
    ax.text(
        0.0, -0.18,
        "Lecture : cet indice inclut l'effet direct du paramètre et ses interactions avec les autres.",
        transform=ax.transAxes,
        color=PALETTE["muted"],
        fontsize=9,
    )
    sns.despine(left=True, bottom=False)
    return _save(fig, path)


def plot_metamodel_performance(metrics: dict, target: str, path: Path) -> Path:
    setup_style()
    values = [float(metrics.get("R2_train", 0.0)), float(metrics.get("Q2_test", 0.0))]
    names = ["R² entraînement", "Q² test"]
    colors = [PALETTE["blue"], PALETTE["amber"]]
    fig, ax = plt.subplots(figsize=(7.5, 5.2))
    bars = ax.bar(names, values, color=colors, edgecolor="white", linewidth=1.4, width=0.58)
    ax.axhline(0, color=PALETTE["ink"], linewidth=1)
    ax.set_ylim(min(-0.05, min(values) - 0.08), min(1.05, max(0.2, max(values) + 0.12)))
    ax.set_ylabel("Score de prédiction")
    ax.set_title(f"Qualité du métamodèle — {label(target)}")
    ax.bar_label(bars, labels=[f"{v:.2f}" for v in values], padding=5, fontsize=11, fontweight="bold")
    ax.text(
        0.0, -0.22,
        "Lecture : R² mesure l'ajustement sur les données vues ; Q² mesure la capacité à prédire des simulations mises de côté.",
        transform=ax.transAxes,
        color=PALETTE["muted"],
        fontsize=9,
    )
    sns.despine(left=False, bottom=True)
    return _save(fig, path)


def plot_regions(regions: pd.DataFrame, target: str, path: Path, top_n: int = 10) -> Path:
    setup_style()
    data = regions.head(top_n).copy()
    if data.empty:
        fig, ax = plt.subplots(figsize=(9, 4))
        ax.text(0.5, 0.5, "Aucune région sensible stable détectée", ha="center", va="center", fontsize=14)
        ax.axis("off")
        return _save(fig, path)
    data = data.sort_values("ecart_a_la_moyenne", ascending=True)
    colors = [PALETTE["coral"] if v < 0 else PALETTE["teal"] for v in data["ecart_a_la_moyenne"]]
    labels = [f"{r}\n{p:.0%} des points" for r, p in zip(data["region"], data["part_des_points"])]
    fig, ax = plt.subplots(figsize=(11, max(5, 0.55 * len(data) + 2)))
    ax.barh(labels, data["ecart_a_la_moyenne"], color=colors, edgecolor="white", linewidth=1.2)
    ax.axvline(0, color=PALETTE["ink"], linewidth=1)
    ax.set_xlabel(f"Écart à la moyenne globale de {label(target)}")
    ax.set_ylabel("")
    ax.set_title(f"Régions locales mises en évidence par l'arbre — {label(target)}")
    for i, (_, row) in enumerate(data.iterrows()):
        x = row["ecart_a_la_moyenne"]
        ha = "left" if x >= 0 else "right"
        offset = max(abs(data["ecart_a_la_moyenne"]).max() * 0.02, 0.01)
        ax.text(x + (offset if x >= 0 else -offset), i, f"moy. {row['moyenne_observee']:.3g}", va="center", ha=ha, fontsize=9)
    ax.text(
        0.0, -0.18,
        "Lecture : chaque barre résume un ensemble de simulations partageant les mêmes règles de seuil.",
        transform=ax.transAxes,
        color=PALETTE["muted"],
        fontsize=9,
    )
    sns.despine(left=True, bottom=False)
    return _save(fig, path)


def plot_tree_figure(tree_result, target: str, path: Path) -> Path:
    setup_style()
    tree = tree_result.pipeline.named_steps["tree"]
    fig_height = max(6, 1.9 * (tree.get_depth() + 1))
    fig, ax = plt.subplots(figsize=(24, fig_height))
    plot_tree(
        tree,
        feature_names=tree_result.feature_names,
        filled=True,
        rounded=True,
        impurity=False,
        fontsize=8,
        ax=ax,
    )
    ax.set_title(f"Arbre de décision — {label(target)} | Q² test = {tree_result.metrics['Q2_test']:.2f}")
    return _save(fig, path)
