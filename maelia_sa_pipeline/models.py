from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import ExtraTreesRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from sklearn.tree import DecisionTreeRegressor, export_text


def make_one_hot_encoder():
    try:
        return OneHotEncoder(handle_unknown="ignore", sparse_output=False)
    except TypeError:
        return OneHotEncoder(handle_unknown="ignore", sparse=False)


def build_preprocessor(categorical: list[str], continuous: list[str]) -> ColumnTransformer:
    categorical_pipe = Pipeline([
        ("imputer", SimpleImputer(strategy="constant", fill_value="inactif")),
        ("onehot", make_one_hot_encoder()),
    ])
    continuous_pipe = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
    ])
    return ColumnTransformer(
        transformers=[
            ("cat", categorical_pipe, categorical),
            ("cont", continuous_pipe, continuous),
        ],
        remainder="drop",
        verbose_feature_names_out=True,
    )


def prepare_X(df: pd.DataFrame, features: list[str], categorical: list[str], continuous: list[str]) -> pd.DataFrame:
    X = df[features].copy()
    for col in categorical:
        if col in X.columns:
            X[col] = X[col].astype("object").where(X[col].notna(), "inactif").astype(str)
    for col in continuous:
        if col in X.columns:
            X[col] = pd.to_numeric(X[col], errors="coerce")
    return X


def transformed_feature_names(preprocessor: ColumnTransformer) -> list[str]:
    try:
        return list(preprocessor.get_feature_names_out())
    except Exception:
        names = []
        ohe = preprocessor.named_transformers_["cat"].named_steps["onehot"]
        categorical = preprocessor.transformers_[0][2]
        continuous = preprocessor.transformers_[1][2]
        for feature, cats in zip(categorical, ohe.categories_):
            names.extend([f"cat__{feature}_{cat}" for cat in cats])
        names.extend([f"cont__{feature}" for feature in continuous])
        return names


def parse_transformed_feature(name: str, categorical: list[str]) -> tuple[str, str, str | None]:
    if name.startswith("cont__"):
        return name.replace("cont__", "", 1), "continuous", None
    if name.startswith("cat__"):
        rest = name.replace("cat__", "", 1)
        for feature in sorted(categorical, key=len, reverse=True):
            prefix = feature + "_"
            if rest.startswith(prefix):
                return feature, "categorical", rest[len(prefix):]
    return name, "unknown", None


def format_rule(feature_name: str, threshold: float, direction: str, categorical: list[str]) -> str:
    raw, kind, category = parse_transformed_feature(feature_name, categorical)
    if kind == "categorical" and abs(threshold - 0.5) < 0.51:
        return f"{raw} n'est pas {category}" if direction == "left" else f"{raw} est {category}"
    op = "≤" if direction == "left" else ">"
    return f"{raw} {op} {threshold:.4g}"


def train_metamodel(
    df: pd.DataFrame,
    target: str,
    features: list[str],
    categorical: list[str],
    continuous: list[str],
    random_state: int = 42,
) -> tuple[Pipeline, dict[str, float]]:
    X = prepare_X(df, features, categorical, continuous)
    y = pd.to_numeric(df[target], errors="coerce")
    mask = y.notna()
    X = X.loc[mask]
    y = y.loc[mask]
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.25, random_state=random_state)
    min_leaf = max(5, int(0.01 * len(X_train)))
    model = Pipeline([
        ("preprocess", build_preprocessor(categorical, continuous)),
        ("model", ExtraTreesRegressor(
            n_estimators=500,
            min_samples_leaf=min_leaf,
            random_state=random_state,
            n_jobs=-1,
        )),
    ])
    model.fit(X_train, y_train)
    pred_train = model.predict(X_train)
    pred_test = model.predict(X_test)
    metrics = {
        "R2_train": float(r2_score(y_train, pred_train)),
        "Q2_test": float(r2_score(y_test, pred_test)),
        "MAE_test": float(mean_absolute_error(y_test, pred_test)),
        "RMSE_test": float(np.sqrt(mean_squared_error(y_test, pred_test))),
        "n_train": int(len(X_train)),
        "n_test": int(len(X_test)),
    }
    return model, metrics


def sobol_total_from_metamodel(
    model: Pipeline,
    df: pd.DataFrame,
    features: list[str],
    categorical: list[str],
    continuous: list[str],
    target: str,
    n_mc: int = 2000,
    random_state: int = 42,
) -> pd.DataFrame:
    rng = np.random.default_rng(random_state)
    X_all = prepare_X(df, features, categorical, continuous).reset_index(drop=True)
    if len(X_all) < 2:
        raise ValueError("Dataset trop petit pour estimer les indices de Sobol.")
    n = min(n_mc, len(X_all))
    idx_a = rng.integers(0, len(X_all), size=n)
    idx_b = rng.integers(0, len(X_all), size=n)
    XA = X_all.iloc[idx_a].reset_index(drop=True)
    XB = X_all.iloc[idx_b].reset_index(drop=True)
    pred_a = model.predict(XA)
    variance = float(np.var(pred_a, ddof=1))
    rows = []
    for feature in features:
        XC = XA.copy()
        XC[feature] = XB[feature].to_numpy()
        pred_c = model.predict(XC)
        st = 0.0 if variance <= 0 else float(np.mean((pred_a - pred_c) ** 2) / (2.0 * variance))
        rows.append({"sortie": target, "parametre": feature, "ST": max(0.0, st)})
    return pd.DataFrame(rows).sort_values("ST", ascending=False).reset_index(drop=True)


@dataclass
class TreeResult:
    pipeline: Pipeline
    metrics: dict[str, float]
    regions: pd.DataFrame
    rules_text: str
    feature_names: list[str]


def train_decision_tree(
    df: pd.DataFrame,
    target: str,
    features: list[str],
    categorical: list[str],
    continuous: list[str],
    max_depth: int = 4,
    random_state: int = 42,
) -> TreeResult:
    X = prepare_X(df, features, categorical, continuous)
    y = pd.to_numeric(df[target], errors="coerce")
    mask = y.notna()
    X = X.loc[mask]
    y = y.loc[mask]
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.25, random_state=random_state)
    min_leaf = max(10, int(0.03 * len(X_train)))
    pipe = Pipeline([
        ("preprocess", build_preprocessor(categorical, continuous)),
        ("tree", DecisionTreeRegressor(
            max_depth=max_depth,
            min_samples_leaf=min_leaf,
            random_state=random_state,
        )),
    ])
    pipe.fit(X_train, y_train)
    pred_train = pipe.predict(X_train)
    pred_test = pipe.predict(X_test)
    metrics = {
        "R2_train": float(r2_score(y_train, pred_train)),
        "Q2_test": float(r2_score(y_test, pred_test)),
        "MAE_test": float(mean_absolute_error(y_test, pred_test)),
        "RMSE_test": float(np.sqrt(mean_squared_error(y_test, pred_test))),
        "n_train": int(len(X_train)),
        "n_test": int(len(X_test)),
    }

    preprocessor = pipe.named_steps["preprocess"]
    tree = pipe.named_steps["tree"]
    feature_names = transformed_feature_names(preprocessor)
    rules_text = export_text(tree, feature_names=feature_names, decimals=4)

    Xt = preprocessor.transform(X)
    leaf_ids = tree.apply(Xt)
    pred = pipe.predict(X)
    global_mean = float(y.mean())
    rows = []
    for rank, leaf in enumerate(pd.Series(leaf_ids).value_counts().index, start=1):
        mask_leaf = leaf_ids == leaf
        rows.append({
            "region": f"Région {rank}",
            "leaf_id": int(leaf),
            "n": int(mask_leaf.sum()),
            "part_des_points": float(mask_leaf.mean()),
            "moyenne_observee": float(y.to_numpy()[mask_leaf].mean()),
            "prediction_moyenne": float(pred[mask_leaf].mean()),
            "ecart_a_la_moyenne": float(y.to_numpy()[mask_leaf].mean() - global_mean),
            "regles": " ; ".join(_path_rules_for_leaf(tree, feature_names, leaf, categorical)),
        })
    regions = pd.DataFrame(rows).sort_values("ecart_a_la_moyenne", key=lambda s: s.abs(), ascending=False).reset_index(drop=True)
    return TreeResult(pipe, metrics, regions, rules_text, feature_names)


def _path_rules_for_leaf(tree: DecisionTreeRegressor, feature_names: list[str], leaf_id: int, categorical: list[str]) -> list[str]:
    children_left = tree.tree_.children_left
    children_right = tree.tree_.children_right
    features = tree.tree_.feature
    thresholds = tree.tree_.threshold
    path: list[str] = []

    def walk(node: int, rules: list[str]) -> bool:
        if node == leaf_id:
            path.extend(rules)
            return True
        left = children_left[node]
        right = children_right[node]
        if left == right:
            return False
        feature_name = feature_names[features[node]]
        threshold = thresholds[node]
        if walk(left, rules + [format_rule(feature_name, threshold, "left", categorical)]):
            return True
        if walk(right, rules + [format_rule(feature_name, threshold, "right", categorical)]):
            return True
        return False

    walk(0, [])
    return path
