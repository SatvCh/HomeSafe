"""
AEIS — pipeline_live.py

Fix for missing packets:
  Python-level IP filtering (if CAMERA_IP in src/dst) is too slow for
  DroidCam video traffic. Scapy's callback runs in Python for every single
  packet on the interface — it can't keep up with video frame rates, so
  most packets are dropped before your handler even sees them.

  Solution: use a BPF (Berkeley Packet Filter) string passed directly to
  Scapy's sniff(). BPF runs in the kernel/Npcap driver — it filters at
  wire speed before packets even reach Python. You capture everything.
"""

from scapy.all import sniff, IP
import requests
import time

# ── Config ────────────────────────────────────────────────────
LAPTOP1_URL    = "http://127.0.0.1:5000/data"
CAMERA_IP      = "192.168.137.168"
WINDOW_SEC     = 5
SEND_RETRIES   = 3
WIFI_INTERFACE = "Wi-Fi"   # change if needed

# ── State ─────────────────────────────────────────────────────
packet_data = []

# BPF filter — runs in kernel/Npcap driver at wire speed
# Much faster than Python-level if/else checking per packet
BPF_FILTER = f"host {CAMERA_IP}"


# ── Packet handler ────────────────────────────────────────────
def packet_handler(packet):
    if IP in packet:
        packet_data.append({
            "src": packet[IP].src,
            "dst": packet[IP].dst,
            "len": len(packet)
        })


# ── Feature extraction ────────────────────────────────────────
def extract_features(data):
    if not data:
        return None

    packet_count = len(data)
    avg_size     = sum(p["len"] for p in data) / packet_count
    unique_dest  = len(set(p["dst"] for p in data))

    print(f"  [debug] packets={packet_count}  avg_size={avg_size:.1f}  "
          f"dest_count={unique_dest}  hour={time.localtime().tm_hour}")

    return {
        "packets_per_window": packet_count,
        "avg_packet_size"   : round(avg_size, 2),
        "dest_count"        : unique_dest,
        "activity_hour"     : time.localtime().tm_hour,
    }


# ── Send with retry ───────────────────────────────────────────
def send_with_retry(features):
    for attempt in range(1, SEND_RETRIES + 1):
        try:
            r = requests.post(LAPTOP1_URL, json=features, timeout=3)
            if r.status_code == 200:
                print(f"  ✅ Server accepted → status={r.json().get('status','?')}")
                return True
            else:
                print(f"  ⚠  Server returned HTTP {r.status_code}")
        except requests.exceptions.ConnectionError:
            print(f"  ❌ Connection error (attempt {attempt}/{SEND_RETRIES})")
        except requests.exceptions.Timeout:
            print(f"  ❌ Timeout (attempt {attempt}/{SEND_RETRIES})")
        time.sleep(0.5)
    print("  ✖  All retries failed")
    return False


# ── Startup ───────────────────────────────────────────────────
print("=" * 55)
print("  AEIS Live Pipeline — Started")
print(f"  Server    : {LAPTOP1_URL}")
print(f"  Camera IP : {CAMERA_IP}")
print(f"  Interface : {WIFI_INTERFACE}")
print(f"  Filter    : {BPF_FILTER}  (kernel-level BPF)")
print(f"  Window    : {WINDOW_SEC}s")
print("=" * 55)

# ── Main loop ─────────────────────────────────────────────────
while True:
    packet_data.clear()

    sniff(
        iface=WIFI_INTERFACE,
        filter=BPF_FILTER,        # kernel-level filter, not Python
        timeout=WINDOW_SEC,
        prn=packet_handler,
        store=False
    )

    ts = time.strftime('%H:%M:%S')
    print(f"\n[{ts}] Window closed — {len(packet_data)} camera packets captured")

    features = extract_features(packet_data)

    if features:
        print(f"  📡 Sending → {features}")
        send_with_retry(features)
    else:
        print("  ⚠  No camera packets — is DroidCam streaming?")