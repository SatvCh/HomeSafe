import joblib
import numpy as np
import pandas as pd
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from aeis_utils import BASE_FEATURES, engineer_features

# RF was trained WITHOUT these 4 time features (matches aeis_train_random_forest.py)
# ISO was trained WITH all 11 features
RF_DROP_COLS = ["activity_hour", "hour_sin", "hour_cos", "high_hour_flag"]

# ── Load models ───────────────────────────────────────────────
iso          = joblib.load("outputs_if/model_isolation_forest.pkl")
threshold_if = float(np.load("outputs_if/iso_threshold.npy"))

rf           = joblib.load("outputs_rf/model_random_forest.pkl")
threshold_rf = float(np.load("outputs_rf/rf_threshold.npy"))

print("=" * 55)
print("  AEIS — Enter Traffic Data for Prediction")
print("=" * 55)
print("\nEnter the traffic values when prompted.\n")

packets_per_min = float(input("  packets_per_min  (e.g. 1200) : "))
avg_packet_size = float(input("  avg_packet_size  (e.g.  500) : "))
dest_count      = float(input("  dest_count       (e.g.    3) : "))   # ← FIXED ORDER
activity_hour   = float(input("  activity_hour    (e.g.   14) : "))   # ← FIXED ORDER

# ── Build feature row in EXACT BASE_FEATURES order ───────────
# BASE_FEATURES = ["packets_per_window", "avg_packet_size", "dest_count", "activity_hour"]
raw = pd.DataFrame(
    [[packets_per_min, avg_packet_size, dest_count, activity_hour]],
    columns=BASE_FEATURES
)

# ── Feature engineering ───────────────────────────────────────
feat_all = engineer_features(raw)           # 11 features — for Isolation Forest
feat_rf  = feat_all.drop(columns=RF_DROP_COLS)  # 7 features — for Random Forest

print("\n  Engineered features (all 11):")
for col, val in zip(feat_all.columns, feat_all.values[0]):
    dropped = " [RF drops]" if col in RF_DROP_COLS else ""
    print(f"    {col:<22} = {val:.4f}{dropped}")

# ── Isolation Forest (uses all 11) ───────────────────────────
iso_score = float(-iso.score_samples(feat_all.values)[0])
if_attack = iso_score >= threshold_if

# ── Random Forest (uses 7, time features dropped) ────────────
rf_prob   = float(rf.predict_proba(feat_rf.values)[0, 1])
rf_attack = rf_prob >= threshold_rf

# ── Print result ──────────────────────────────────────────────
print("\n" + "=" * 55)
print("  RESULTS")
print("=" * 55)

print(f"\n  Isolation Forest  (11 features)")
print(f"    Anomaly score : {iso_score:.5f}")
print(f"    Threshold     : {threshold_if:.5f}")
print(f"    Decision      : {'ATTACK' if if_attack else 'NORMAL'}")

print(f"\n  Random Forest  (7 features, time cols dropped)")
print(f"    Attack prob   : {rf_prob:.4f}")
print(f"    Threshold     : {threshold_rf:.5f}")
print(f"    Decision      : {'ATTACK' if rf_attack else 'NORMAL'}")

print("\n" + "=" * 55)
if if_attack and rf_attack:
    verdict = "BOTH MODELS AGREE — HIGH CONFIDENCE ATTACK"
elif if_attack or rf_attack:
    verdict = "ONE MODEL FLAGGED — POSSIBLE ANOMALY"
else:
    verdict = "BOTH MODELS AGREE — NORMAL TRAFFIC"
print(f"  FINAL VERDICT: {verdict}")
print("=" * 55 + "\n")
