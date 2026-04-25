"""
AEIS — pipeline_live.py
Fixes:
  1. Binds sniff() to the correct WiFi interface — stops missing packets
  2. Sends 'packets_per_window' to match BASE_FEATURES
  3. Filters traffic to camera IP only
  4. Debug output so you can see exactly what is captured each window
  5. Retry logic on connection error
  6. Window size configurable
"""

from scapy.all import sniff, IP
import requests
import time

# ── Config ────────────────────────────────────────────────────
LAPTOP1_URL    = "http://127.0.0.1:5000/data"  # Laptop 1 Flask server
CAMERA_IP      = "100.120.11.125"                    # Phone / DroidCam IP
WINDOW_SEC     = 5                                  # capture window in seconds
SEND_RETRIES   = 3                                  # retry POST on failure

# !! IMPORTANT — paste the interface name you noted here !!
# Example: "Wi-Fi", "Wireless Network Connection", "Intel(R) Wi-Fi 6 ..."
WIFI_INTERFACE = "Wi-Fi"                            # <── CHANGE THIS

# ── State ─────────────────────────────────────────────────────
packet_data = []


# ── Packet handler ────────────────────────────────────────────
def packet_handler(packet):
    if IP in packet:
        src = packet[IP].src
        dst = packet[IP].dst
        # Only track packets involving the camera
        if CAMERA_IP in (src, dst):
            packet_data.append({
                "src": src,
                "dst": dst,
                "len": len(packet)
            })


# ── Feature extraction ────────────────────────────────────────
def extract_features(data):
    if not data:
        return None

    packet_count = len(data)
    avg_size     = sum(p["len"] for p in data) / packet_count
    unique_dest  = len(set(p["dst"] for p in data))

    # Debug — shows exactly what will be sent to the server
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
                resp = r.json()
                print(f"  ✅ Server accepted → status={resp.get('status', '?')}")
                return True
            else:
                print(f"  ⚠  Server returned HTTP {r.status_code}")
        except requests.exceptions.ConnectionError:
            print(f"  ❌ Connection error (attempt {attempt}/{SEND_RETRIES}) "
                  f"— is Laptop 1 running?")
        except requests.exceptions.Timeout:
            print(f"  ❌ Timeout (attempt {attempt}/{SEND_RETRIES})")
        time.sleep(0.5)
    print("  ✖  All retries failed — skipping this window")
    return False


# ── Startup banner ────────────────────────────────────────────
print("=" * 55)
print("  AEIS Live Pipeline — Started")
print(f"  Server    : {LAPTOP1_URL}")
print(f"  Camera IP : {CAMERA_IP}")
print(f"  Interface : {WIFI_INTERFACE}")
print(f"  Window    : {WINDOW_SEC}s")
print("=" * 55)
print("  Tip: if you see 'No camera packets' every window,")
print("  the interface name is wrong. Run get_working_ifaces()")
print("  from scapy to list available interfaces.")
print("=" * 55)

# ── Main loop ─────────────────────────────────────────────────
while True:
    packet_data.clear()

    # iface= forces Scapy to use your WiFi adapter, not Ethernet/VPN
    sniff(
        iface=WIFI_INTERFACE,
        timeout=WINDOW_SEC,
        prn=packet_handler,
        store=False
    )

    timestamp = time.strftime('%H:%M:%S')
    print(f"\n[{timestamp}] Window closed — {len(packet_data)} camera packets captured")

    features = extract_features(packet_data)

    if features:
        print(f"  📡 Sending → {features}")
        send_with_retry(features)
    else:
        print("  ⚠  No camera packets in this window — nothing sent")
        print("  Possible reasons:")
        print("    • DroidCam is not streaming right now")
        print("    • CAMERA_IP is wrong")
        print(f"    • Wrong interface — expected traffic on '{WIFI_INTERFACE}'")