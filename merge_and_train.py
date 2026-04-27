# """
# AEIS — merge_and_retrain.py
# ----------------------------
# Run this on Laptop 1 after copying normal_live_traffic.csv from Laptop 2.
# Merges new normal traffic with existing dataset, checks balance,
# then retrains both models cleanly.

# Usage:
#   python merge_and_retrain.py
# """

# import os
# import warnings
# warnings.filterwarnings("ignore")

# import numpy as np
# import pandas as pd

# # ── Config ────────────────────────────────────────────────────
# ORIGINAL_DATASET = "camera_dataset.csv"
# NEW_NORMAL_FILE  = "normal_live_traffic.csv"
# MERGED_DATASET   = "camera_dataset.csv"   # overwrites original (original backed up)
# BACKUP_FILE      = "camera_dataset_backup.csv"

# print("=" * 60)
# print("  AEIS — Merge & Retrain")
# print("=" * 60)

# # ── Step 1: Load both files ───────────────────────────────────
# print("\n[1] Loading datasets...")

# if not os.path.exists(NEW_NORMAL_FILE):
#     print(f"\n  ❌ {NEW_NORMAL_FILE} not found.")
#     print(f"     Copy it from Laptop 2 first, then re-run.")
#     exit(1)

# df_orig = pd.read_csv(ORIGINAL_DATASET)
# df_new  = pd.read_csv(NEW_NORMAL_FILE)

# print(f"  Original dataset : {len(df_orig)} rows  "
#       f"(normal={len(df_orig[df_orig.label==0])}, "
#       f"attack={len(df_orig[df_orig.label==1])})")
# print(f"  New normal data  : {len(df_new)} rows")

# # Verify new file has correct columns
# required = ["packets_per_window", "avg_packet_size", "dest_count",
#             "activity_hour", "label"]
# missing = [c for c in required if c not in df_new.columns]
# if missing:
#     print(f"\n  ❌ New file is missing columns: {missing}")
#     exit(1)

# if df_new["label"].nunique() > 1 or df_new["label"].iloc[0] != 0:
#     print(f"\n  ⚠  New file contains non-zero labels — setting all to 0 (normal)")
#     df_new["label"] = 0

# # ── Step 2: Check balance before merging ─────────────────────
# print("\n[2] Checking class balance...")

# n_orig_normal = len(df_orig[df_orig.label == 0])
# n_orig_attack = len(df_orig[df_orig.label == 1])
# n_new_normal  = len(df_new)
# n_total_normal_after = n_orig_normal + n_new_normal

# ratio_after = n_orig_attack / (n_total_normal_after + n_orig_attack) * 100
# print(f"  After merge: {n_total_normal_after} normal + {n_orig_attack} attack")
# print(f"  Attack ratio: {ratio_after:.1f}%  (target: 15–25%)")

# if ratio_after < 10:
#     # Need more attack samples — duplicate existing ones with small noise
#     print(f"\n  ⚠  Attack ratio too low ({ratio_after:.1f}%) — augmenting attack samples...")
#     target_attack = int(n_total_normal_after * 0.20)
#     extra_needed  = target_attack - n_orig_attack
#     df_attacks    = df_orig[df_orig.label == 1]

#     rng = np.random.default_rng(42)
#     aug_rows = []
#     for _ in range(extra_needed):
#         row = df_attacks.sample(1, random_state=rng.integers(9999)).iloc[0].copy()
#         # Add small Gaussian noise to numeric features (2% std)
#         for col in ["packets_per_window", "avg_packet_size", "dest_count"]:
#             noise = rng.normal(0, row[col] * 0.02)
#             row[col] = round(max(0, row[col] + noise), 2)
#         aug_rows.append(row)

#     df_aug_attacks = pd.DataFrame(aug_rows)
#     df_orig = pd.concat([df_orig, df_aug_attacks], ignore_index=True)
#     print(f"  Added {extra_needed} augmented attack rows")
#     print(f"  New attack total: {len(df_orig[df_orig.label==1])}")

# # ── Step 3: Merge ─────────────────────────────────────────────
# print("\n[3] Merging datasets...")

# # Backup original first
# df_orig_clean = pd.read_csv(ORIGINAL_DATASET)
# df_orig_clean.to_csv(BACKUP_FILE, index=False)
# print(f"  ✅ Original backed up to {BACKUP_FILE}")

# df_merged = pd.concat([df_orig, df_new[required]], ignore_index=True)
# df_merged  = df_merged.sample(frac=1, random_state=42).reset_index(drop=True)  # shuffle

# final_normal = len(df_merged[df_merged.label == 0])
# final_attack = len(df_merged[df_merged.label == 1])
# final_ratio  = final_attack / len(df_merged) * 100

# print(f"  Merged dataset   : {len(df_merged)} rows")
# print(f"  Normal           : {final_normal}")
# print(f"  Attack           : {final_attack}")
# print(f"  Attack ratio     : {final_ratio:.1f}%")

# df_merged.to_csv(MERGED_DATASET, index=False)
# print(f"  ✅ Saved to {MERGED_DATASET}")

# # ── Step 4: Retrain both models ───────────────────────────────
# print("\n[4] Retraining models...")
# print("  Running aeis_train_isolation_forest.py ...")
# ret = os.system("python aeis_train_isolation_forest.py")
# if ret != 0:
#     print("  ❌ Isolation Forest training failed")
#     exit(1)

# print("\n  Running aeis_train_random_forest.py ...")
# ret = os.system("python aeis_train_random_forest.py")
# if ret != 0:
#     print("  ❌ Random Forest training failed")
#     exit(1)

# # ── Step 5: Sanity check new thresholds ──────────────────────
# print("\n[5] New threshold values:")
# iso_thresh = float(np.load("outputs_if/iso_threshold.npy"))
# rf_thresh  = float(np.load("outputs_rf/rf_threshold.npy"))
# print(f"  ISO threshold : {iso_thresh:.5f}")
# print(f"  RF  threshold : {rf_thresh:.5f}")

# print("\n" + "=" * 60)
# print("  ✅ Retrain complete — restart server.py to load new models")
# print("=" * 60)