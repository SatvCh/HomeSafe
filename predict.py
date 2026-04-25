import joblib
import numpy as np
import pandas as pd
import sys
import os

# Add current folder to path so aeis_utils imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from aeis_utils import BASE_FEATURES, engineer_features

# ── Load models ───────────────────────────────────────────────
iso       = joblib.load("outputs_if/model_isolation_forest.pkl")
threshold_if = float(np.load("outputs_if/iso_threshold.npy"))

rf        = joblib.load("outputs_rf/model_random_forest.pkl")
threshold_rf = float(np.load("outputs_rf/rf_threshold.npy"))

print("=" * 55)
print("  AEIS — Enter Traffic Data for Prediction")
print("=" * 55)

# ── Get input ─────────────────────────────────────────────────
print("\nEnter the traffic values when prompted.\n")

packets_per_min  = float(input("  packets_per_min  (e.g. 1200) : "))
avg_packet_size  = float(input("  avg_packet_size  (e.g.  500) : "))
activity_hour    = float(input("  activity_hour    (e.g.   14) : "))
dest_count       = float(input("  dest_count       (e.g.    3) : "))

# ── Build feature row ─────────────────────────────────────────
raw  = pd.DataFrame(
    [[packets_per_min, avg_packet_size, activity_hour, dest_count]],
    columns=BASE_FEATURES
)
feat = engineer_features(raw)

print("\n  Engineered features:")
for col, val in zip(feat.columns, feat.values[0]):
    print(f"    {col:<22} = {val:.4f}")

# ── Isolation Forest ──────────────────────────────────────────
iso_score = -iso.score_samples(feat.values)[0]
if_attack = iso_score >= threshold_if

# ── Random Forest ─────────────────────────────────────────────
rf_prob   = rf.predict_proba(feat.values)[0, 1]
rf_attack = rf_prob >= threshold_rf

# ── Print result ──────────────────────────────────────────────
print("\n" + "=" * 55)
print("  RESULTS")
print("=" * 55)

print(f"\n  Isolation Forest")
print(f"    Anomaly score : {iso_score:.5f}")
print(f"    Threshold     : {threshold_if:.5f}")
print(f"    Decision      : {'⚠️  ATTACK' if if_attack else '✅  NORMAL'}")

print(f"\n  Random Forest")
print(f"    Attack prob   : {rf_prob:.4f}")
print(f"    Threshold     : {threshold_rf:.4f}")
print(f"    Decision      : {'⚠️  ATTACK' if rf_attack else '✅  NORMAL'}")

print("\n" + "=" * 55)
if if_attack and rf_attack:
    verdict = "🔴  BOTH MODELS AGREE — HIGH CONFIDENCE ATTACK"
elif if_attack or rf_attack:
    verdict = "🟡  ONE MODEL FLAGGED — POSSIBLE ANOMALY"
else:
    verdict = "🟢  BOTH MODELS AGREE — NORMAL TRAFFIC"
print(f"  FINAL VERDICT: {verdict}")
print("=" * 55 + "\n")