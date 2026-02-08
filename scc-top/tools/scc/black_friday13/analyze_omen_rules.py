#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import GridSearchCV, TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from sklearn.tree import DecisionTreeClassifier, export_text


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, obj: Any) -> None:
    _ensure_dir(path.parent)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", errors="replace")


def _write_text(path: Path, text: str) -> None:
    _ensure_dir(path.parent)
    path.write_text(text, encoding="utf-8", errors="replace")


def _feature_frame(days: pd.Series) -> pd.DataFrame:
    dt = pd.to_datetime(days, errors="coerce")
    df = pd.DataFrame({"day": dt})
    df["dow"] = df["day"].dt.dayofweek.astype(int)  # Mon=0
    df["dom"] = df["day"].dt.day.astype(int)
    df["month"] = df["day"].dt.month.astype(int)
    df["is_friday_13"] = (df["dow"] == 4) & (df["dom"] == 13)
    df["is_weekend"] = df["dow"].isin([5, 6])
    df["is_month_start"] = df["day"].dt.is_month_start
    df["is_month_end"] = df["day"].dt.is_month_end
    df["is_quarter_start"] = df["day"].dt.is_quarter_start
    df["is_quarter_end"] = df["day"].dt.is_quarter_end
    df["is_year_start"] = df["day"].dt.is_year_start
    df["is_year_end"] = df["day"].dt.is_year_end
    df["is_leap_day"] = (df["day"].dt.month == 2) & (df["day"].dt.day == 29)
    return df


@dataclass(frozen=True)
class ModelScore:
    target: str
    prevalence: float
    cv_metric: str
    cv_best_score: float
    holdout_ap: float
    holdout_roc_auc: float


def _safe_auc(y_true: np.ndarray, y_score: np.ndarray) -> float:
    try:
        return float(roc_auc_score(y_true, y_score))
    except Exception:
        return float("nan")


def _safe_ap(y_true: np.ndarray, y_score: np.ndarray) -> float:
    try:
        return float(average_precision_score(y_true, y_score))
    except Exception:
        return float("nan")


def main(argv: Optional[Iterable[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Build 'scientific omen' rules predicting bad days from date-only attributes.")
    ap.add_argument("--luck-daily", default="artifacts/black_friday13/luck_index_world_td/luck_index_daily.parquet")
    ap.add_argument("--out-dir", default="artifacts/black_friday13/omen_rules_world_td")
    ap.add_argument("--targets", default="is_bad_5p,is_bad_1p", help="Comma-separated target columns in luck_daily.")
    args = ap.parse_args(list(argv) if argv is not None else None)

    luck_path = Path(args.luck_daily)
    out_dir = Path(args.out_dir)
    _ensure_dir(out_dir)

    d = pd.read_parquet(luck_path)
    if "day" not in d.columns:
        raise SystemExit("luck_daily must include 'day'")
    d["day"] = pd.to_datetime(d["day"], errors="coerce")
    d = d.dropna(subset=["day"]).sort_values("day").reset_index(drop=True)

    targets = [t.strip() for t in str(args.targets).split(",") if t.strip()]
    missing = [t for t in targets if t not in d.columns]
    if missing:
        raise SystemExit(f"missing target columns: {missing}")

    feat = _feature_frame(d["day"])
    X = feat.drop(columns=["day"]).copy()

    # Separate columns: categorical vs boolean.
    cat_cols = ["dow", "dom", "month"]
    bool_cols = [c for c in X.columns if c not in cat_cols]
    pre = ColumnTransformer(
        transformers=[
            ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), cat_cols),
            ("bool", "passthrough", bool_cols),
        ]
    )

    # Time-based evaluation: last 20% as holdout.
    n = len(X)
    split = int(np.floor(n * 0.8))
    X_train, X_test = X.iloc[:split].copy(), X.iloc[split:].copy()
    day_test = d["day"].iloc[split:].copy().reset_index(drop=True)

    scores: list[ModelScore] = []
    coef_rows: list[dict[str, Any]] = []
    pred_rows: list[pd.DataFrame] = []
    tree_texts: list[str] = []

    for tgt in targets:
        y = d[tgt].astype(bool).to_numpy(dtype=int)
        y_train, y_test = y[:split], y[split:]
        prevalence = float(y.mean())

        if int(y_train.sum()) == 0 or int(y_train.sum()) == int(len(y_train)):
            raise SystemExit(f"target {tgt}: training window has only one class; cannot train omen model")

        # L1 logistic with CV over C (regularization strength).
        # Use elasticnet with l1_ratio=1.0 to avoid penalty deprecation in sklearn>=1.8.
        clf = LogisticRegression(penalty="elasticnet", l1_ratio=1.0, solver="saga", max_iter=2000)
        pipe = Pipeline([("pre", pre), ("clf", clf)])
        grid = {"clf__C": [0.1, 0.3, 1.0, 3.0]}
        tscv = TimeSeriesSplit(n_splits=5)
        gs = GridSearchCV(pipe, grid, scoring="average_precision", cv=tscv, n_jobs=1)
        gs.fit(X_train, y_train)

        best = gs.best_estimator_
        proba = best.predict_proba(X_test)[:, 1]
        # Holdout metrics may be undefined if the holdout contains no positives (esp. 1% tail).
        ap_holdout = _safe_ap(y_test, proba) if int(y_test.sum()) > 0 else float("nan")
        auc_holdout = _safe_auc(y_test, proba) if 0 < int(y_test.sum()) < int(len(y_test)) else float("nan")
        scores.append(
            ModelScore(
                target=tgt,
                prevalence=prevalence,
                cv_metric="average_precision",
                cv_best_score=float(gs.best_score_) if gs.best_score_ is not None else float("nan"),
                holdout_ap=ap_holdout,
                holdout_roc_auc=auc_holdout,
            )
        )

        # Coefficients (non-zero).
        ohe = best.named_steps["pre"].named_transformers_["cat"]
        cat_names = ohe.get_feature_names_out(cat_cols).tolist()
        feat_names = cat_names + bool_cols
        coefs = best.named_steps["clf"].coef_.ravel().astype(float)
        for name, c in sorted(zip(feat_names, coefs), key=lambda x: abs(x[1]), reverse=True)[:80]:
            coef_rows.append({"target": tgt, "feature": str(name), "coef": float(c)})

        # Prediction series for later visualization (dow x dom heatmap can use this).
        pr = pd.DataFrame({"day": day_test, "target": tgt, "y_true": y_test.astype(int), "p_bad": proba.astype(float)})
        pred_rows.append(pr)

        # Simple tree for rule-like description (uses raw numeric + booleans, no one-hot).
        tree_X = X_train.copy()
        tree = DecisionTreeClassifier(max_depth=3, min_samples_leaf=max(20, int(0.01 * len(tree_X))), random_state=42)
        tree.fit(tree_X, y_train)
        rules = export_text(tree, feature_names=list(tree_X.columns))
        tree_texts.append(f"## {tgt}\n{rules}\n")

    score_df = pd.DataFrame([asdict(s) for s in scores])
    score_df.to_csv(out_dir / "model_scores.csv", index=False, encoding="utf-8")
    pd.DataFrame(coef_rows).to_csv(out_dir / "logit_l1_top_coefs.csv", index=False, encoding="utf-8")
    pd.concat(pred_rows, ignore_index=True).to_parquet(out_dir / "holdout_predictions.parquet", index=False)
    _write_text(out_dir / "tree_rules.txt", "\n".join(tree_texts).strip() + "\n")

    overview = {
        "generated_utc": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "luck_daily": str(luck_path).replace("\\", "/"),
        "out_dir": str(out_dir).replace("\\", "/"),
        "n_days": int(len(d)),
        "holdout_days": int(len(X_test)),
        "features": {"categorical": cat_cols, "boolean": bool_cols},
        "targets": targets,
    }
    _write_json(out_dir / "overview.json", overview)

    # Markdown summary.
    lines: list[str] = []
    lines.append("# Checkpoint E (Q5) — Omen rules from date-only attributes")
    lines.append("")
    lines.append("- Goal: predict whether a day is 'bad' (top-tail of U_t) using only calendar/formal attributes.")
    lines.append(f"- Input: `{overview['luck_daily']}`")
    lines.append(f"- Days: {overview['n_days']}, holdout(last 20%): {overview['holdout_days']}")
    lines.append("")
    lines.append("## Performance (holdout)")
    for r in scores:
        lines.append(
            f"- {r.target}: prevalence={r.prevalence:.3%}, CV(AP)={r.cv_best_score:.3f}, holdout AP={r.holdout_ap:.3f}, ROC-AUC={r.holdout_roc_auc:.3f}"
        )
    lines.append("")
    lines.append("## Outputs")
    lines.append("- `model_scores.csv`: CV + holdout metrics")
    lines.append("- `logit_l1_top_coefs.csv`: top non-zero omen coefficients (interpretable)")
    lines.append("- `tree_rules.txt`: shallow decision-tree rules (human-readable)")
    lines.append("- `holdout_predictions.parquet`: predicted probabilities for the holdout window")
    _write_text(out_dir / "report.md", "\n".join(lines) + "\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
