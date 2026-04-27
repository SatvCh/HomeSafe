"""
AEIS — Live Pipeline (Scapy Capture or Simulation)
pipeline_live.py

Run on the device that can see camera traffic (same network).
Captures packets → extracts features → sends to server.py via HTTP.

Usage:
    python pipeline_live.py                     # simulation mode (default)
    python pipeline_live.py --live              # real Scapy capture
    python pipeline_live.py --attack ddos       # simulate specific attack
    python pipeline_live.py --attack port_scan --intensity 0.7
"""

import argparse
import time
import requests
import sys

# ── Config ─────────────────────────────────────────────────────────────────────
SERVER_URL   = "http://localhost:5000/data"   # change to your server IP
CAMERA_IP    = "192.168.29.36"
WINDOW_SEC   = 5
WIFI_IFACE   = "Wi-Fi"                        # Windows; use "wlan0" for Linux
SEND_RETRIES = 3

# ── Argument parsing ───────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description="AEIS Live Pipeline")
parser.add_argument("--live",      action="store_true", help="Use real Scapy capture")
parser.add_argument("--attack",    default="ddos",
    choices=["normal","ddos","port_scan","data_exfiltration","suspicious_timing"],
    help="Attack type to simulate (simulation mode)")
parser.add_argument("--intensity", type=float, default=1.0, help="Attack intensity 0.0–1.0")
args = parser.parse_args()

USE_SIMULATION = not args.live

print(f"\n{'='*55}")
print("  AEIS Live Pipeline")
print(f"  Mode      : {'SIMULATION' if USE_SIMULATION else 'LIVE CAPTURE'}")
if USE_SIMULATION:
    print(f"  Attack    : {args.attack} @ intensity {args.intensity}")
print(f"  Server    : {SERVER_URL}")
print(f"  Window    : {WINDOW_SEC}s")
print(f"{'='*55}\n")

if USE_SIMULATION:
    from AEIS_Pipeline.simulation import generate
else:
    try:
        from scapy.all import sniff, IP
    except ImportError:
        print("ERROR: Scapy not installed. Run: pip install scapy")
        sys.exit(1)

# ── Packet capture buffer ──────────────────────────────────────────────────────
packet_data = []

def packet_handler(pkt):
    from scapy.all import IP
    if IP in pkt:
        src = pkt[IP].src
        dst = pkt[IP].dst
        if CAMERA_IP in (src, dst):
            packet_data.append({"src": src, "dst": dst, "len": len(pkt)})


def extract_features(data: list) -> dict | None:
    if not data:
        return None
    count    = len(data)
    avg_size = sum(p["len"] for p in data) / count
    unique_d = len(set(p["dst"] for p in data))
    print(f"  [capture] packets={count}  avg_size={avg_size:.1f}B  unique_dests={unique_d}")
    return {
        "packets_per_window": count,
        "avg_packet_size"   : round(avg_size, 2),
        "dest_count"        : unique_d,
        "activity_hour"     : time.localtime().tm_hour,
    }


def send(features: dict) -> None:
    for attempt in range(SEND_RETRIES):
        try:
            r = requests.post(SERVER_URL, json=features, timeout=3)
            data = r.json()
            print(f"  → Server responded: {data}")
            return
        except Exception as e:
            print(f"  Send attempt {attempt+1} failed: {e}")
            time.sleep(0.5)
    print("  ✗ All send attempts failed")


# ── Main loop ──────────────────────────────────────────────────────────────────
print("🚀 Pipeline running (Ctrl+C to stop)…\n")

try:
    while True:
        if USE_SIMULATION:
            features = generate(args.attack, args.intensity)
            print(f"  [sim] {args.attack}@{args.intensity} → "
                  f"pkts={features['packets_per_window']}  "
                  f"size={features['avg_packet_size']}B  "
                  f"dests={features['dest_count']}  "
                  f"hour={features['activity_hour']:02d}:00")
            send(features)
            time.sleep(WINDOW_SEC)
        else:
            packet_data.clear()
            sniff(iface=WIFI_IFACE, timeout=WINDOW_SEC,
                  prn=packet_handler, store=False)
            features = extract_features(packet_data)
            if features:
                send(features)
            else:
                print("  No camera packets captured in window")

except KeyboardInterrupt:
    print("\n\nPipeline stopped.")