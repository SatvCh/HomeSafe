"""
generate_synthetic.py
Generates a synthetic camera_dataset.csv that maps directly to
your 4 attack types and the real DroidCam pipeline behavior.

Run: python generate_synthetic.py
Output: camera_dataset.csv (replaces the old one)
"""

import numpy as np
import pandas as pd

rng = np.random.default_rng(42)

# ── CONFIG ────────────────────────────────────────────────────
# These numbers are based on what pipeline_live.py actually sends
# in a 5-second window. Adjust CAMERA_IP_ONLY below to True/False
# depending on whether your pipeline filters to camera IP.
WINDOW_SECONDS = 5
N_NORMAL       = 800   # normal windows
N_PER_ATTACK   = 200   # windows per attack type (4 types = 800 total attack)

# ─────────────────────────────────────────────────────────────
# NORMAL — DroidCam streaming, no attack
# Characteristics: moderate packets, large frames (video), few dests
# packets_per_window: 1000-3000  (video stream at ~400pps over 5s)
# avg_packet_size:    900-1300   (TCP video segments, below MTU)
# dest_count:         1-3        (camera IP, laptop, maybe router ACK)
# activity_hour:      any hour   (demo can run anytime)
# ─────────────────────────────────────────────────────────────
normal = pd.DataFrame({
    'packets_per_window': rng.integers(1000, 3000, N_NORMAL).astype(float),
    'avg_packet_size':    rng.uniform(900, 1300, N_NORMAL),
    'dest_count':         rng.integers(1, 4, N_NORMAL).astype(float),
    'activity_hour':      rng.integers(0, 24, N_NORMAL).astype(float),
    'label': 0
})

# ─────────────────────────────────────────────────────────────
# ATTACK TYPE 1 — DoS (Denial of Service)
# simulate_attack.py sends high-rate small SYN/UDP packets to camera
# Key signal: packets_per_window spikes massively, avg_packet_size tiny
# ─────────────────────────────────────────────────────────────
dos = pd.DataFrame({
    'packets_per_window': rng.integers(8000, 30000, N_PER_ATTACK).astype(float),
    'avg_packet_size':    rng.uniform(40, 90, N_PER_ATTACK),    # bare SYN/UDP
    'dest_count':         rng.integers(1, 2, N_PER_ATTACK).astype(float),  # 1 target
    'activity_hour':      rng.integers(0, 24, N_PER_ATTACK).astype(float),
    'label': 1
})

# ─────────────────────────────────────────────────────────────
# ATTACK TYPE 2 — Data Exfiltration
# Large payload packets sent FROM camera to attacker
# Key signal: avg_packet_size very high, moderate packet count
# ─────────────────────────────────────────────────────────────
exfil = pd.DataFrame({
    'packets_per_window': rng.integers(2000, 5000, N_PER_ATTACK).astype(float),
    'avg_packet_size':    rng.uniform(1400, 1500, N_PER_ATTACK),  # near MTU, max payload
    'dest_count':         rng.integers(1, 3, N_PER_ATTACK).astype(float),
    'activity_hour':      rng.integers(0, 6, N_PER_ATTACK).astype(float),   # odd hours
    'label': 1
})

# ─────────────────────────────────────────────────────────────
# ATTACK TYPE 3 — Port Scan
# Attacker probes many different IPs/ports rapidly
# Key signal: dest_count very high, moderate packets, small size
# ─────────────────────────────────────────────────────────────
portscan = pd.DataFrame({
    'packets_per_window': rng.integers(3000, 8000, N_PER_ATTACK).astype(float),
    'avg_packet_size':    rng.uniform(50, 120, N_PER_ATTACK),    # probe packets
    'dest_count':         rng.integers(15, 50, N_PER_ATTACK).astype(float),  # many targets
    'activity_hour':      rng.integers(0, 24, N_PER_ATTACK).astype(float),
    'label': 1
})

# ─────────────────────────────────────────────────────────────
# ATTACK TYPE 4 — Botnet C2C (Command & Control)
# Periodic bursts at fixed hours, consistent small beacons
# Key signal: high_hour_flag fires (midnight-6AM), low dest_count, periodic
# ─────────────────────────────────────────────────────────────
botnet = pd.DataFrame({
    'packets_per_window': rng.integers(4000, 9000, N_PER_ATTACK).astype(float),
    'avg_packet_size':    rng.uniform(60, 200, N_PER_ATTACK),   # beacon packets
    'dest_count':         rng.integers(1, 3, N_PER_ATTACK).astype(float),
    'activity_hour':      rng.integers(0, 5, N_PER_ATTACK).astype(float),  # 0-5 AM
    'label': 1
})

# ─────────────────────────────────────────────────────────────
# COMBINE AND SAVE
# ─────────────────────────────────────────────────────────────
attack_all = pd.concat([dos, exfil, portscan, botnet], ignore_index=True)

# Sample attack to ~25% of total (matches process_data.py logic)
n_attack_target = int(len(normal) * 0.25)
attack_sampled  = attack_all.sample(n=min(n_attack_target, len(attack_all)), random_state=42)

final = pd.concat([normal, attack_sampled], ignore_index=True)
final = final.sample(frac=1, random_state=42).reset_index(drop=True)
final.to_csv('camera_dataset.csv', index=False)

print(f"Saved camera_dataset.csv")
print(f"  Total  : {len(final)}")
print(f"  Normal : {(final.label==0).sum()}")
print(f"  Attack : {(final.label==1).sum()}")
print(f"  Normal avg_packet_size: {final[final.label==0].avg_packet_size.mean():.0f} bytes")
print(f"  Attack avg_packet_size: {final[final.label==1].avg_packet_size.mean():.0f} bytes")
print(f"  Normal avg_pkt_window:  {final[final.label==0].packets_per_window.mean():.0f}")
print(f"  Attack avg_pkt_window:  {final[final.label==1].packets_per_window.mean():.0f}")