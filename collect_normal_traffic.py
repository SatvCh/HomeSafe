"""
AEIS — collect_normal_traffic.py
---------------------------------
Run this on Laptop 2 while DroidCam is streaming normally.
Captures live traffic windows and saves them as label=0 (normal)
to a CSV that can be merged with camera_dataset.csv for retraining.

Usage:
  1. Start DroidCam and make sure it is streaming
  2. Run: python collect_normal_traffic.py
  3. Let it run for 10-15 minutes (captures ~120-180 windows)
  4. Copy the output CSV to Laptop 1 alongside camera_dataset.csv
  5. Run merge_and_retrain.py on Laptop 1
"""

from scapy.all import sniff, IP
import pandas as pd
import time
import os

# ── Config ────────────────────────────────────────────────────
CAMERA_IP      = "192.168.29.68"
WIFI_INTERFACE = "Wi-Fi"              # ← same interface name you used in pipeline_live.py
WINDOW_SEC     = 5                    # must match pipeline_live.py
TARGET_WINDOWS = 150                  # ~12 minutes of capture at 5s windows
OUTPUT_FILE    = "normal_live_traffic.csv"

# ── State ─────────────────────────────────────────────────────
packet_data = []
collected   = []


def packet_handler(packet):
    if IP in packet:
        src = packet[IP].src
        dst = packet[IP].dst
        if CAMERA_IP in (src, dst):
            packet_data.append({
                "src": src,
                "dst": dst,
                "len": len(packet)
            })


def extract_features(data, hour):
    packet_count = len(data)
    avg_size     = sum(p["len"] for p in data) / packet_count
    unique_dest  = len(set(p["dst"] for p in data))
    return {
        "packets_per_window": packet_count,
        "avg_packet_size"   : round(avg_size, 2),
        "dest_count"        : unique_dest,
        "activity_hour"     : hour,
        "label"             : 0,      # always 0 — this is normal traffic
    }


# ── Banner ────────────────────────────────────────────────────
print("=" * 55)
print("  AEIS — Normal Traffic Collector")
print(f"  Camera IP : {CAMERA_IP}")
print(f"  Interface : {WIFI_INTERFACE}")
print(f"  Window    : {WINDOW_SEC}s")
print(f"  Target    : {TARGET_WINDOWS} windows (~{TARGET_WINDOWS*WINDOW_SEC//60} min)")
print(f"  Output    : {OUTPUT_FILE}")
print("=" * 55)
print("\n  Make sure DroidCam is streaming before continuing.")
print("  Press ENTER to start collecting...")
input()

skipped = 0

for i in range(1, TARGET_WINDOWS + 1):
    packet_data.clear()
    hour = time.localtime().tm_hour

    sniff(
        iface=WIFI_INTERFACE,
        timeout=WINDOW_SEC,
        prn=packet_handler,
        store=False
    )

    if not packet_data:
        skipped += 1
        print(f"  [{i:>3}/{TARGET_WINDOWS}] ⚠  No camera packets — skipping "
              f"(is DroidCam streaming?)")
        continue

    features = extract_features(packet_data, hour)
    collected.append(features)

    print(f"  [{i:>3}/{TARGET_WINDOWS}] ✅  "
          f"pkts={features['packets_per_window']:>5}  "
          f"avg_size={features['avg_packet_size']:>7.1f}  "
          f"dests={features['dest_count']}  "
          f"hour={features['activity_hour']}")

    # Save incrementally every 20 windows so you don't lose data on crash
    if i % 20 == 0:
        pd.DataFrame(collected).to_csv(OUTPUT_FILE, index=False)
        print(f"\n  💾 Auto-saved {len(collected)} rows to {OUTPUT_FILE}\n")

# ── Final save ────────────────────────────────────────────────
df_new = pd.DataFrame(collected)
df_new.to_csv(OUTPUT_FILE, index=False)

print("\n" + "=" * 55)
print(f"  Collection complete!")
print(f"  Windows collected : {len(collected)}")
print(f"  Windows skipped   : {skipped}")
print(f"  Saved to          : {OUTPUT_FILE}")
print(f"\n  Stats of collected normal traffic:")
print(f"  packets_per_window : "
      f"{df_new['packets_per_window'].min()} – {df_new['packets_per_window'].max()} "
      f"(mean {df_new['packets_per_window'].mean():.0f})")
print(f"  avg_packet_size    : "
      f"{df_new['avg_packet_size'].min()} – {df_new['avg_packet_size'].max()} "
      f"(mean {df_new['avg_packet_size'].mean():.0f})")
print(f"\n  Next step: copy {OUTPUT_FILE} to Laptop 1")
print(f"  Then run : python merge_and_retrain.py")
print("=" * 55)