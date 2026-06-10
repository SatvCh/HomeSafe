"""
traffic_sim.py
==============
SYNTHETIC-ONLY attack simulation for AEIS.

Generates realistic feature snapshots using statistical models for each
attack type.  No real packets are ever sent.

Entry point
-----------
    from traffic_sim import generate_synthetic
    features = generate_synthetic("ddos", intensity=0.8)

Returns a dict matching BASE_FEATURES exactly:
    {
        "packets_per_window": int,
        "avg_packet_size":    float,
        "dest_count":         int,
        "activity_hour":      int,
    }
"""

from __future__ import annotations

import random
from typing import Any


# ── Helpers ───────────────────────────────────────────────────────────────────
def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))

def _ri(lo: int, hi: int) -> int:
    return random.randint(lo, hi)

def _rf(lo: float, hi: float) -> float:
    return round(random.uniform(lo, hi), 2)


# ══════════════════════════════════════════════════════════════════════════════
# SYNTHETIC GENERATORS
# Each function returns a BASE_FEATURES-compatible dict.
# ══════════════════════════════════════════════════════════════════════════════

def _synth_ddos(intensity: float) -> dict[str, Any]:
    """DDoS / Packet Flood — high packet rate, small frames, few destinations.

    intensity 0.0–0.49 → SUSPICIOUS range  (8 000–12 000 pkt)
    intensity 0.5–1.0  → QUARANTINE range  (12 001–20 000 pkt)
    """
    i = _clamp(intensity, 0.0, 1.0)
    if i >= 0.5:
        # Hard quarantine band
        pkts = int(_ri(12001, 14000) + i * 6000)
    else:
        # Suspicious band
        pkts = int(_ri(8001, 10000) + i * 2000)
    return {
        "packets_per_window": pkts,
        "avg_packet_size":    _rf(200.0, 600.0),
        "dest_count":         _ri(1, max(1, int(4 - i * 2))),
        "activity_hour":      _ri(0, 23),
    }


def _synth_port_scan(intensity: float) -> dict[str, Any]:
    """Port / Network Scan — many unique destination IPs, moderate rate.

    dest_count drives the classification here:
    intensity 0.0–0.49 → SUSPICIOUS (dest 5–10)
    intensity 0.5–1.0  → QUARANTINE (dest >10)
    """
    i = _clamp(intensity, 0.0, 1.0)
    hour = (
        random.choice(list(range(0, 6)) + list(range(22, 24)))
        if i > 0.5 else _ri(0, 23)
    )
    if i >= 0.5:
        dest = int(_ri(11, 20) + i * 20)   # >10 → QUARANTINED
    else:
        dest = int(_ri(5, 10))              # 5–10 → SUSPICIOUS
    return {
        "packets_per_window": _ri(500, int(1000 + i * 2000)),
        "avg_packet_size":    _rf(40.0, 120.0),
        "dest_count":         dest,
        "activity_hour":      hour,
    }


def _synth_data_exfiltration(intensity: float) -> dict[str, Any]:
    """Data Exfiltration — large outbound frames (near/above MTU), off-hours.

    avg_packet_size drives the classification:
    intensity 0.0–0.49 → SUSPICIOUS  (1350–1449 B)
    intensity 0.5–1.0  → QUARANTINE  (≥1450 B)
    """
    i    = _clamp(intensity, 0.0, 1.0)
    hour = random.choice(range(0, 6)) if i > 0.4 else _ri(0, 23)
    if i >= 0.5:
        size = _rf(1450.0, 1500.0)   # >1450 → QUARANTINED
    else:
        size = _rf(1350.0, 1449.0)   # 1350–1449 → SUSPICIOUS
    return {
        "packets_per_window": _ri(200, int(500 + i * 1000)),
        "avg_packet_size":    size,
        "dest_count":         _ri(1, max(1, int(3 - i))),
        "activity_hour":      hour,
    }


def _synth_suspicious_timing(intensity: float) -> dict[str, Any]:
    """Suspicious Off-Hours Activity — always midnight-6 AM.

    Classified SUSPICIOUS via activity_hour 0–6 anomaly heuristic.
    Packet count deliberately kept in normal-ish range to isolate
    the timing signal.
    """
    i = _clamp(intensity, 0.0, 1.0)
    return {
        "packets_per_window": _ri(3000, int(6000 + i * 2000)),
        "avg_packet_size":    _rf(300.0, 700.0),
        "dest_count":         _ri(1, 4),
        "activity_hour":      random.choice(range(0, 6)),
    }


def _synth_normal() -> dict[str, Any]:
    """Baseline healthy traffic — mirrors real observed camera traffic.

    Real logs: packets ~7000, avg_size ~1300 B, dest ~2, hour ~23.
    Kept safely below SUSPICIOUS thresholds (8000 pkt / 1350 B / 5 dest).
    """
    return {
        "packets_per_window": _ri(4000, 7999),
        "avg_packet_size":    _rf(800.0, 1349.0),
        "dest_count":         _ri(1, 4),
        "activity_hour":      _ri(0, 23),
    }


# ── Registry ──────────────────────────────────────────────────────────────────
_SYNTH_REGISTRY: dict[str, Any] = {
    "ddos":               _synth_ddos,
    "port_scan":          _synth_port_scan,
    "data_exfiltration":  _synth_data_exfiltration,
    "suspicious_timing":  _synth_suspicious_timing,
    "normal":             _synth_normal,
}

ATTACK_LABELS = {
    "normal":            "Normal Traffic",
    "ddos":              "DDoS / Packet Flood",
    "port_scan":         "Port / IP Scan",
    "data_exfiltration": "Data Exfiltration",
    "suspicious_timing": "Suspicious Off-Hours",
}

VALID_ATTACK_TYPES = list(_SYNTH_REGISTRY.keys())


# ── Public API ────────────────────────────────────────────────────────────────
def generate_synthetic(
    attack_type: str = "normal",
    intensity:   float = 1.0,
) -> dict[str, Any]:
    """
    Generate a SYNTHETIC traffic feature snapshot.  No real packets are sent.

    Parameters
    ----------
    attack_type : "ddos" | "port_scan" | "data_exfiltration" |
                  "suspicious_timing" | "normal"
    intensity   : 0.0 – 1.0  (ignored for normal traffic)

    Returns
    -------
    dict with keys: packets_per_window, avg_packet_size, dest_count, activity_hour
    """
    attack_type = attack_type.lower().strip()
    intensity   = _clamp(float(intensity), 0.0, 1.0)

    fn = _SYNTH_REGISTRY.get(attack_type)
    if fn is None:
        raise ValueError(
            f"Unknown attack_type '{attack_type}'. Valid: {VALID_ATTACK_TYPES}"
        )

    features = fn() if attack_type == "normal" else fn(intensity=intensity)

    print(
        f"  [traffic_sim] synthetic type={attack_type} "
        f"intensity={intensity:.2f} → {features}"
    )
    return features


# Back-compat alias used by older code
def run_simulation(
    mode: str        = "synthetic",
    attack_type: str = "normal",
    intensity: float = 1.0,
) -> dict[str, Any]:
    """
    Compatibility wrapper — mode must be 'synthetic'.
    Prefer calling generate_synthetic() directly.
    """
    if mode != "synthetic":
        raise ValueError(
            "Real-mode UDP flood has been removed. "
            "Only mode='synthetic' is supported."
        )
    return generate_synthetic(attack_type, intensity)


# ── Standalone demo ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n=== Synthetic demos ===")
    for at in VALID_ATTACK_TYPES:
        f = generate_synthetic(at, 1.0)
        print(f"  {at:22s} → {f}")
