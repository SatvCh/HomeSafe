"""
=============================================================
  AEIS — Autonomous Edge Immune System
  Model Training  |  aeis_train_random_forest.py
  -----------------------------------------------------------
  Model   : Random Forest  (supervised classifier)
  Purpose : High-accuracy detection of known attack patterns.
  -----------------------------------------------------------
  Usage   : python aeis_train_random_forest.py
  Outputs : outputs_rf/
              model_random_forest.pkl
              rf_threshold.npy
              rf_feature_names.npy
              cm_random_forest.png
              roc_random_forest.png
              rf_feature_importance.png
              drift_robustness_rf.png
=============================================================
"""

import os
import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import (
    StratifiedKFold,
    RandomizedSearchCV,
    cross_val_score,
    train_test_split,
)
from sklearn.metrics import f1_score, recall_score
import joblib

from aeis_utils import (
    BASE_FEATURES,
    engineer_features,
    smote_lite,
    optimal_threshold,
    print_metrics,
    save_cm,
    save_roc,
)

# ─────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────
DATASET_PATH  = "camera_dataset.csv"
OUTPUT_DIR    = "outputs_rf"
RANDOM_STATE  = 42
CV_FOLDS      = 5
TEST_SIZE     = 0.20

# Time features removed from RF — RF detects traffic behaviour
# (packet size, rate, destinations), not time-of-day patterns.
# Time features are kept in Isolation Forest for baseline deviation.
TIME_FEATURES = ['activity_hour', 'hour_sin', 'hour_cos', 'high_hour_flag']

os.makedirs(OUTPUT_DIR, exist_ok=True)
np.random.seed(RANDOM_STATE)

# ─────────────────────────────────────────────────────────────
# 1.  LOAD & SPLIT DATA
# ─────────────────────────────────────────────────────────────
print("=" * 60)
print("  AEIS — RANDOM FOREST TRAINING")
print("=" * 60)
print("\n[1] Loading data from camera_dataset.csv ...")

df = pd.read_csv(DATASET_PATH)

required = BASE_FEATURES + ["label"]
missing  = [c for c in required if c not in df.columns]
if missing:
    raise ValueError(f"Missing columns {missing}. Found: {list(df.columns)}")

X = df[BASE_FEATURES]
y = df["label"]

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=TEST_SIZE, stratify=y, random_state=RANDOM_STATE
)

print(f"   Dataset : {len(df)} rows")
print(f"   Split   : {len(X_train)} train / {len(X_test)} test  (80/20)")
print(f"   Train   -> Normal: {(y_train==0).sum()}  "
      f"Attack: {(y_train==1).sum()}  "
      f"({y_train.mean()*100:.1f}% attack)")
print(f"   Test    -> Normal: {(y_test==0).sum()}   "
      f"Attack: {(y_test==1).sum()}   "
      f"({y_test.mean()*100:.1f}% attack)")

# ─────────────────────────────────────────────────────────────
# 2.  FEATURE ENGINEERING + DROP TIME FEATURES
# ─────────────────────────────────────────────────────────────
print("\n[2] Engineering features then dropping time-based columns...")

# Drop time features BEFORE converting to numpy
# FEATURE_NAMES captured here so it always matches importances length
X_train_fe  = engineer_features(X_train).drop(columns=TIME_FEATURES)
X_test_fe   = engineer_features(X_test).drop(columns=TIME_FEATURES)
FEATURE_NAMES = list(X_train_fe.columns)

print(f"   Features used ({len(FEATURE_NAMES)}) : {FEATURE_NAMES}")
print(f"   Dropped ({len(TIME_FEATURES)})        : {TIME_FEATURES}")

# Convert to numpy AFTER drop so shapes are consistent everywhere
X_tr = X_train_fe.values.astype(np.float64)
X_te = X_test_fe.values.astype(np.float64)
y_tr = y_train.values.astype(int)
y_te = y_test.values.astype(int)

# ─────────────────────────────────────────────────────────────
# 3.  CLASS IMBALANCE - SMOTE-lite
# ─────────────────────────────────────────────────────────────
print("\n[3] Handling class imbalance (SMOTE-lite oversampling)...")

X_tr_bal, y_tr_bal = smote_lite(X_tr, y_tr, random_state=RANDOM_STATE)

print(f"   Before -> Normal: {(y_tr==0).sum()}  Attack: {(y_tr==1).sum()}")
print(f"   After  -> Normal: {(y_tr_bal==0).sum()}  "
      f"Attack: {(y_tr_bal==1).sum()}")

# ─────────────────────────────────────────────────────────────
# 4.  HYPERPARAMETER TUNING
# ─────────────────────────────────────────────────────────────
print(f"\n[4] Hyperparameter tuning "
      f"(RandomizedSearchCV - 20 iter x {CV_FOLDS}-fold CV)...")

param_dist = {
    "n_estimators":      [100, 200, 300, 400],
    "max_depth":         [None, 5, 10, 15, 20],
    "min_samples_split": [2, 5, 10],
    "min_samples_leaf":  [1, 2, 4],
    "max_features":      ["sqrt", "log2", 0.5],
}

cv_inner = StratifiedKFold(
    n_splits=CV_FOLDS, shuffle=True, random_state=RANDOM_STATE
)

rscv = RandomizedSearchCV(
    RandomForestClassifier(random_state=RANDOM_STATE, n_jobs=-1),
    param_distributions=param_dist,
    n_iter=20,
    cv=cv_inner,
    scoring="f1",
    refit=True,
    random_state=RANDOM_STATE,
    n_jobs=-1,
    verbose=0,
)
rscv.fit(X_tr_bal, y_tr_bal)
best_rf = rscv.best_estimator_

print(f"   Best params : {rscv.best_params_}")
print(f"   Best CV F1  : {rscv.best_score_:.4f}")

# ─────────────────────────────────────────────────────────────
# 5.  CROSS-VALIDATION (variance estimate)
# ─────────────────────────────────────────────────────────────
print(f"\n[5] {CV_FOLDS}-fold cross-validation (variance check)...")

cv_outer = StratifiedKFold(
    n_splits=CV_FOLDS, shuffle=True, random_state=RANDOM_STATE
)
cv_f1  = cross_val_score(best_rf, X_tr, y_tr,
                          cv=cv_outer, scoring="f1",      n_jobs=-1)
cv_auc = cross_val_score(best_rf, X_tr, y_tr,
                          cv=cv_outer, scoring="roc_auc", n_jobs=-1)

print(f"   CV F1      : {cv_f1.mean():.4f} +/- {cv_f1.std():.4f}")
print(f"   CV ROC-AUC : {cv_auc.mean():.4f} +/- {cv_auc.std():.4f}")
if cv_f1.std() < 0.03:
    print("   [OK] Low variance - model is stable across folds.")
else:
    print("   [WARN] High variance - consider more training data.")

# ─────────────────────────────────────────────────────────────
# 6.  TRAIN FINAL MODEL
# ─────────────────────────────────────────────────────────────
print("\n[6] Training final model on balanced training set...")

best_rf.fit(X_tr_bal, y_tr_bal)

rf_scores_tr = best_rf.predict_proba(X_tr)[:, 1]
rf_scores_te = best_rf.predict_proba(X_te)[:, 1]

# ─────────────────────────────────────────────────────────────
# 7.  THRESHOLD OPTIMISATION
# ─────────────────────────────────────────────────────────────
print("\n[7] Optimising decision threshold (target: max F1)...")

threshold = optimal_threshold(y_tr, rf_scores_tr, metric="f1")
rf_pred   = (rf_scores_te >= threshold).astype(int)

print(f"   Optimised threshold : {threshold:.4f}")

# ─────────────────────────────────────────────────────────────
# 8.  EVALUATION
# ─────────────────────────────────────────────────────────────
print("\n[8] Evaluating on test set...")
print("\n" + "-" * 50)
result = print_metrics("Random Forest", y_te, rf_pred, rf_scores_te)
print("-" * 50)

# Overfitting check
rf_pred_tr   = (rf_scores_tr >= threshold).astype(int)
train_f1     = f1_score(y_tr, rf_pred_tr, zero_division=0)
test_f1      = result["f1"]
train_recall = recall_score(y_tr, rf_pred_tr, zero_division=0)
test_recall  = result["recall"]

print(f"\n[9] Overfitting check:")
print(f"   {'Metric':<12} {'Train':>8} {'Test':>8} {'Gap':>8}")
print(f"   {'-'*40}")
print(f"   {'F1':<12} {train_f1:>8.4f} {test_f1:>8.4f} "
      f"{abs(train_f1 - test_f1):>8.4f}")
print(f"   {'Recall':<12} {train_recall:>8.4f} {test_recall:>8.4f} "
      f"{abs(train_recall - test_recall):>8.4f}")
if abs(train_f1 - test_f1) < 0.05:
    print("   [OK] No overfitting detected (gap < 0.05).")
else:
    print("   [WARN] Gap > 0.05 - increase min_samples_leaf or reduce max_depth.")

# ─────────────────────────────────────────────────────────────
# 10. FEATURE IMPORTANCE
# ─────────────────────────────────────────────────────────────
print("\n[10] Feature importances:")

importances = best_rf.feature_importances_

# FEATURE_NAMES set at step 2 - always matches importances length
imp_df = pd.DataFrame({
    "feature":    FEATURE_NAMES,
    "importance": importances,
}).sort_values("importance", ascending=False).reset_index(drop=True)

print(f"\n   {'Rank':<6} {'Feature':<22} {'Importance':>10}")
print(f"   {'-'*42}")
for rank, row in imp_df.iterrows():
    tag = "* " if row["feature"] not in BASE_FEATURES else "  "
    bar = "#" * int(row["importance"] * 60)
    print(f"   {rank+1:<6} {tag}{row['feature']:<20} "
          f"{row['importance']:>10.4f}  {bar}")

imp_sorted = imp_df.sort_values("importance", ascending=True)
colors = [
    "#EF5350" if f not in BASE_FEATURES else "#1565C0"
    for f in imp_sorted["feature"]
]
fig, ax = plt.subplots(figsize=(8, 6))
ax.barh(imp_sorted["feature"], imp_sorted["importance"],
        color=colors, alpha=0.85)
ax.set_title("Random Forest - Feature Importance\n"
             "(blue = original  |  red = engineered)")
ax.set_xlabel("Importance Score")
plt.tight_layout()
plt.savefig(os.path.join(OUTPUT_DIR, "rf_feature_importance.png"), dpi=120)
plt.close()

# ─────────────────────────────────────────────────────────────
# 11. DRIFT / ROBUSTNESS TEST
# ─────────────────────────────────────────────────────────────
print("\n[11] Robustness test - simulating feature drift / sensor noise...")

rng          = np.random.default_rng(RANDOM_STATE)
noise_levels = [0.0, 0.05, 0.10, 0.20, 0.30, 0.50]
drift_rows   = []

for sigma in noise_levels:
    noise   = rng.normal(0, sigma, X_te.shape)
    X_noisy = X_te + noise
    scores  = best_rf.predict_proba(X_noisy)[:, 1]
    pred    = (scores >= threshold).astype(int)
    drift_rows.append({
        "noise_sigma": sigma,
        "F1":     f1_score(y_te, pred, zero_division=0),
        "Recall": recall_score(y_te, pred, zero_division=0),
    })

drift_df = pd.DataFrame(drift_rows)
print(f"\n   {'Noise sigma':<12} {'F1':>8} {'Recall':>10}")
print(f"   {'-'*32}")
for _, row in drift_df.iterrows():
    print(f"   {row['noise_sigma']:<12.2f} {row['F1']:>8.4f} "
          f"{row['Recall']:>10.4f}")

fig, ax = plt.subplots(figsize=(7, 4))
ax.plot(drift_df["noise_sigma"], drift_df["F1"],
        "o-", color="#1565C0", label="F1")
ax.plot(drift_df["noise_sigma"], drift_df["Recall"],
        "s--", color="#C62828", label="Recall")
ax.set_xlabel("Noise sigma (feature drift intensity)")
ax.set_ylabel("Score")
ax.set_title("Random Forest - Drift Robustness")
ax.set_ylim(0, 1.05)
ax.legend()
plt.tight_layout()
plt.savefig(os.path.join(OUTPUT_DIR, "drift_robustness_rf.png"), dpi=120)
plt.close()

# ─────────────────────────────────────────────────────────────
# 12. SAVE PLOTS
# ─────────────────────────────────────────────────────────────
print("\n[12] Saving plots...")

save_cm(y_te, rf_pred,
        title="Random Forest - Confusion Matrix",
        output_dir=OUTPUT_DIR,
        fname="cm_random_forest.png")

save_roc(y_te, rf_scores_te,
         title="Random Forest - ROC Curve",
         output_dir=OUTPUT_DIR,
         fname="roc_random_forest.png")

# ─────────────────────────────────────────────────────────────
# 13. SAVE MODEL
# ─────────────────────────────────────────────────────────────
print("\n[13] Saving model artefacts...")

joblib.dump(best_rf, os.path.join(OUTPUT_DIR, "model_random_forest.pkl"))
np.save(os.path.join(OUTPUT_DIR, "rf_threshold.npy"), threshold)
np.save(os.path.join(OUTPUT_DIR, "rf_feature_names.npy"),
        np.array(FEATURE_NAMES))

print(f"   [OK] outputs_rf/model_random_forest.pkl")
print(f"   [OK] outputs_rf/rf_threshold.npy  (value={threshold:.4f})")
print(f"   [OK] outputs_rf/rf_feature_names.npy")
print(f"   [OK] outputs_rf/cm_random_forest.png")
print(f"   [OK] outputs_rf/roc_random_forest.png")
print(f"   [OK] outputs_rf/rf_feature_importance.png")
print(f"   [OK] outputs_rf/drift_robustness_rf.png")

print("\n" + "=" * 60)
print("  INFERENCE USAGE")
print("=" * 60)
print("""
  import joblib, numpy as np, pandas as pd
  from aeis_utils import engineer_features

  rf            = joblib.load("outputs_rf/model_random_forest.pkl")
  threshold     = float(np.load("outputs_rf/rf_threshold.npy"))
  TIME_FEATURES = ['activity_hour','hour_sin','hour_cos','high_hour_flag']

  def detect(packets_per_window, avg_packet_size,
             dest_count, activity_hour):
      raw  = pd.DataFrame([[packets_per_window, avg_packet_size,
                             dest_count, activity_hour]],
                           columns=["packets_per_window", "avg_packet_size",
                                    "dest_count", "activity_hour"])
      feat = engineer_features(raw).drop(columns=TIME_FEATURES).values
      prob = rf.predict_proba(feat)[0, 1]
      return {
          "attack"     : bool(prob >= threshold),
          "attack_prob": round(float(prob), 4),
          "threshold"  : round(threshold, 4),
      }
""")

print("=" * 60)
print("  RANDOM FOREST TRAINING COMPLETE")
print("=" * 60)