# import pandas as pd
# import os
# import glob

# def load_csv(filepath):
#     if not os.path.exists(filepath):
#         raise FileNotFoundError(f"File not found: {filepath}")
#     if os.path.getsize(filepath) == 0:
#         raise ValueError(f"File is empty: {filepath}")
#     for encoding in ['utf-8-sig', 'utf-8', 'latin1', 'cp1252']:
#         try:
#             df = pd.read_csv(filepath, encoding=encoding, engine='python')
#             print(f"  [OK] {os.path.basename(filepath)} → {len(df):,} rows")
#             return df
#         except UnicodeDecodeError:
#             continue
#     raise UnicodeDecodeError(f"Could not decode {filepath}")

# def validate_and_clean(df, filepath):
#     required = ['frame.time_epoch', 'ip.dst', 'frame.len']
#     missing = [c for c in required if c not in df.columns]
#     if missing:
#         raise ValueError(f"Missing columns {missing} in {filepath}")
#     df = df.dropna(subset=required)
#     df['frame.time_epoch'] = pd.to_numeric(df['frame.time_epoch'], errors='coerce')
#     df['frame.len']        = pd.to_numeric(df['frame.len'],        errors='coerce')
#     return df.dropna(subset=['frame.time_epoch', 'frame.len'])

# def process_files(pattern, label, window_seconds=5):
#     files = sorted(glob.glob(pattern))
#     if not files:
#         raise FileNotFoundError(f"No files found matching: {pattern}")

#     tag = "NORMAL" if label == 0 else "ATTACK"
#     print(f"\n[{tag}] Found {len(files)} file(s):")

#     all_frames = []
#     for f in files:
#         df = load_csv(f)
#         df = validate_and_clean(df, f)
#         all_frames.append(df)

#     combined = pd.concat(all_frames, ignore_index=True)
#     combined = combined.sort_values('frame.time_epoch').reset_index(drop=True)
#     print(f"  Combined total rows : {len(combined):,}")

#     combined['interval'] = (combined['frame.time_epoch'] // window_seconds).astype(int)
#     grouped = combined.groupby('interval')

#     result = pd.DataFrame({
#         'packets_per_window': grouped.size(),
#         'avg_packet_size':    grouped['frame.len'].mean().round(2),
#         'dest_count':         grouped['ip.dst'].nunique(),
#         'activity_hour':      grouped['frame.time_epoch'].first().apply(
#                                   lambda t: pd.Timestamp(t, unit='s').hour),
#         'label': label
#     }).reset_index(drop=True)

#     print(f"  Feature windows     : {len(result):,}  (window={window_seconds}s, label={label})")
#     return result

# # ── Main ─────────────────────────────────────────────────────
# WINDOW_SECONDS = 5

# try:
#     normal = process_files("raw_data_clean*.csv",   label=0, window_seconds=WINDOW_SECONDS)
#     attack = process_files("attack_raw_clean*.csv", label=1, window_seconds=WINDOW_SECONDS)

#     # ── 80/20 ratio: attack = ~20% of total ──────────────────
#     # Isolation Forest expects anomalies to be rare (10-20%)
#     # RF also benefits from learning realistic class imbalance
#     n_attack_target = int(len(normal) * 0.25)   # 25% of normal ≈ 20% of total
#     attack_sampled  = attack.sample(
#         n=min(n_attack_target, len(attack)),
#         random_state=42
#     )
#     print(f"\n[SAMPLING] Attack windows: {len(attack)} total → "
#           f"{len(attack_sampled)} sampled (target ~20% of dataset)")

#     final = pd.concat([normal, attack_sampled], ignore_index=True)
#     final = final.sample(frac=1, random_state=42).reset_index(drop=True)
#     final.to_csv("camera_dataset.csv", index=False)

#     pct_attack = (final['label']==1).sum() / len(final) * 100
#     pct_normal = 100 - pct_attack

#     print(f"\n{'='*50}")
#     print(f"[DONE] camera_dataset.csv saved")
#     print(f"  Total rows  : {len(final)}")
#     print(f"  Normal rows : {(final['label']==0).sum()}  ({pct_normal:.1f}%)")
#     print(f"  Attack rows : {(final['label']==1).sum()}  ({pct_attack:.1f}%)")
#     print(f"  Columns     : {list(final.columns)}")
#     print(f"{'='*50}")
#     print(f"\n✅ {pct_normal:.1f}% normal / {pct_attack:.1f}% attack")
#     print(f"   Suitable for both Random Forest and Isolation Forest.")

# except (FileNotFoundError, ValueError) as e:
#     print(f"\n[ERROR] {e}")