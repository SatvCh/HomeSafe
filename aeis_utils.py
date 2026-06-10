"""
=============================================================
  AEIS — Autonomous Edge Immune System
  Shared Utilities  |  aeis_utils.py
  -----------------------------------------------------------
  Contains:
    - Feature engineering  (engineer_features)
    - SMOTE-lite oversampling  (smote_lite)
    - Optimal threshold finder  (optimal_threshold)
    - Metric printer  (print_metrics)
    - Plot helpers  (save_cm, save_roc)

  Imported by:
    aeis_train_isolation_forest.py
    aeis_train_random_forest.py
=============================================================
"""

import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns

from sklearn.metrics import (
    classification_report, confusion_matrix,
    roc_auc_score, roc_curve,
    accuracy_score, precision_score, recall_score, f1_score,
    precision_recall_curve,
)
from sklearn.utils import resample

# ── Column names ─────────────────────────────────────────────
# Must match exactly what process_data.py outputs in camera_dataset.csv
BASE_FEATURES = [
    "packets_per_window",   # was packets_per_min — fixed to match dataset
    "avg_packet_size",
    "dest_count",
    "activity_hour",
]

ENGINEERED_FEATURES = [
    "pkt_size_x_ppw",    # volume proxy  (ppw = packets per window)
    "hour_sin",           # cyclical time encoding
    "hour_cos",
    "ppw_sq",             # burst sensitivity
    "size_sq",            # jumbo-frame sensitivity
    "ppw_dest_ratio",     # scan / C2C indicator
    "high_hour_flag",     # off-hours binary flag
]

ALL_FEATURES = BASE_FEATURES + ENGINEERED_FEATURES


# ── Feature engineering ───────────────────────────────────────
def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Adds 7 network-behaviour features on top of the 4 base features.

    Feature rationale
    -----------------
    pkt_size_x_ppw  : Large packets at high rate → DDoS / exfiltration.
    hour_sin/cos    : Cyclical hour encoding; hour 23 ≈ hour 0.
    ppw_sq          : Non-linear burst detection.
    size_sq         : Non-linear jumbo-frame anomaly detection.
    ppw_dest_ratio  : Spreading traffic across many destinations at
                      high rate → port scan / C2C beacon.
    high_hour_flag  : Binary off-hours flag (hours 0–6 = night)
                      → known APT / botnet indicator.
    """
    fe = df.copy()
    fe["pkt_size_x_ppw"] = fe["avg_packet_size"] * fe["packets_per_window"]
    fe["hour_sin"]        = np.sin(2 * np.pi * fe["activity_hour"] / 24.0)
    fe["hour_cos"]        = np.cos(2 * np.pi * fe["activity_hour"] / 24.0)
    fe["ppw_sq"]          = fe["packets_per_window"] ** 2
    fe["size_sq"]         = fe["avg_packet_size"] ** 2
    fe["ppw_dest_ratio"]  = fe["packets_per_window"] / (
        np.abs(fe["dest_count"]) + 1e-6
    )
    # Off-hours: midnight to 6 AM (known botnet / APT window)
    fe["high_hour_flag"]  = ((fe["activity_hour"] >= 0) &
                              (fe["activity_hour"] < 6)).astype(float)
    return fe


# ── SMOTE-lite (no imblearn dep) ──────────────────────────────
def smote_lite(X: np.ndarray, y: np.ndarray,
               random_state: int = 42):
    """
    Minority-class oversampling with small Gaussian noise.
    Equivalent to SMOTE without the imblearn dependency.
    """
    rng = np.random.default_rng(random_state)
    classes, counts = np.unique(y, return_counts=True)
    minority_cls    = classes[np.argmin(counts)]
    majority_cls    = classes[np.argmax(counts)]
    n_majority      = counts[np.argmax(counts)]

    X_min = X[y == minority_cls]
    X_maj = X[y == majority_cls]

    X_min_up = resample(X_min, replace=True,
                        n_samples=n_majority,
                        random_state=random_state)
    noise    = rng.normal(0, 0.05 * X_min.std(axis=0), X_min_up.shape)
    X_min_up = X_min_up + noise

    X_bal = np.vstack([X_maj, X_min_up])
    y_bal = np.hstack([
        np.full(n_majority, majority_cls),
        np.full(n_majority, minority_cls),
    ])
    idx = rng.permutation(len(y_bal))
    return X_bal[idx], y_bal[idx]


# ── Threshold optimisation ────────────────────────────────────
def optimal_threshold(y_true: np.ndarray, y_scores: np.ndarray,
                      metric: str = "recall",
                      min_precision: float = 0.40) -> float:
    """
    Find the decision threshold that maximises the chosen metric.

    Parameters
    ----------
    metric        : 'f1' or 'recall'
    min_precision : minimum precision floor when metric='recall'
                    (prevents flagging every sample as attack)
    """
    prec_arr, rec_arr, thresh_arr = precision_recall_curve(
        y_true, y_scores
    )
    if metric == "f1":
        f1_arr   = (2 * prec_arr[:-1] * rec_arr[:-1]) / (
            prec_arr[:-1] + rec_arr[:-1] + 1e-9
        )
        best_idx = np.argmax(f1_arr)
    else:   # recall — minimise false negatives
        valid    = prec_arr[:-1] >= min_precision
        if not valid.any():
            valid = np.ones(len(thresh_arr), dtype=bool)
        best_idx = np.argmax(rec_arr[:-1] * valid)
    return float(thresh_arr[best_idx])


# ── Metrics printer ───────────────────────────────────────────
def print_metrics(name: str, y_true, y_pred,
                  y_scores=None) -> dict:
    acc  = accuracy_score(y_true, y_pred)
    prec = precision_score(y_true, y_pred, zero_division=0)
    rec  = recall_score(y_true, y_pred, zero_division=0)
    f1   = f1_score(y_true, y_pred, zero_division=0)
    auc  = roc_auc_score(y_true, y_scores) if y_scores is not None else None
    fn   = int(confusion_matrix(y_true, y_pred)[1, 0])

    print(f"\n  {'Metric':<22} {'Value':>8}")
    print(f"  {'-'*32}")
    print(f"  {'Accuracy':<22} {acc:>8.4f}")
    print(f"  {'Precision':<22} {prec:>8.4f}")
    print(f"  {'Recall':<22} {rec:>8.4f}")
    print(f"  {'F1 Score':<22} {f1:>8.4f}")
    if auc is not None:
        print(f"  {'ROC-AUC':<22} {auc:>8.4f}")
    print(f"  {'False Negatives':<22} {fn:>8d}  ← missed attacks")
    print(f"\n  Classification Report:\n")
    print(classification_report(
        y_true, y_pred,
        target_names=["Normal", "Attack"],
        zero_division=0, digits=4,
    ))
    return {
        "model": name, "accuracy": acc, "precision": prec,
        "recall": rec, "f1": f1,
        "roc_auc": auc, "false_negatives": fn,
    }


# ── Plot helpers ──────────────────────────────────────────────
def save_cm(y_true, y_pred, title: str,
            output_dir: str, fname: str) -> None:
    cm = confusion_matrix(y_true, y_pred)
    fig, ax = plt.subplots(figsize=(5, 4))
    sns.heatmap(cm, annot=True, fmt="d", cmap="Blues",
                xticklabels=["Normal", "Attack"],
                yticklabels=["Normal", "Attack"], ax=ax)
    ax.set_xlabel("Predicted")
    ax.set_ylabel("Actual")
    ax.set_title(title)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, fname), dpi=120)
    plt.close()


def save_roc(y_true, y_scores, title: str,
             output_dir: str, fname: str) -> float:
    fpr, tpr, _ = roc_curve(y_true, y_scores)
    auc = roc_auc_score(y_true, y_scores)
    fig, ax = plt.subplots(figsize=(5, 4))
    ax.plot(fpr, tpr, lw=2, color="#1565C0", label=f"AUC = {auc:.4f}")
    ax.plot([0, 1], [0, 1], "k--", lw=1)
    ax.fill_between(fpr, tpr, alpha=0.1, color="#1565C0")
    ax.set_xlabel("False Positive Rate")
    ax.set_ylabel("True Positive Rate")
    ax.set_title(title)
    ax.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, fname), dpi=120)
    plt.close()
    return auc