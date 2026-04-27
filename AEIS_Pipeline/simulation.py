"""
AEIS — Attack Simulation Module
simulation.py

Generates synthetic traffic snapshots for testing the pipeline.
Each function returns a dict compatible with detection.detect().

Attack Types:
    ddos               → Packet flood (high packet count)
    port_scan          → Destination IP spread (many unique IPs)
    data_exfiltration  → Large outbound frames (near MTU)
    suspicious_timing  → Off-hours low-volume access
    normal             → Baseline healthy traffic
"""

from __future__ import annotations

import random
import time
from typing import Any


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))

def _ri(lo: int, hi: int) -> int:
    return random.randint(lo, hi)

def _rf(lo: float, hi: float) -> float:
    return round(random.uniform(lo, hi), 2)

def _meta() -> dict:
    return {"simulated": True, "timestamp": int(time.time())}


# ══════════════════════════════════════════════════════════════
# ATTACK SIMULATORS
# ══════════════════════════════════════════════════════════════

def ddos(intensity: float = 1.0) -> dict[str, Any]:
    """
    DDoS / Packet Flood
    Triggers Rule 1 (packet count).
    
    Intensity 0.3 → ~600 packets (LOW/MEDIUM)
    Intensity 1.0 → ~2800 packets (HIGH)
    """
    i = _clamp(intensity, 0.0, 1.0)
    return {
        "attack_type"       : "ddos",
        "intensity"         : round(i, 2),
        "packets_per_window": int(_ri(800, 1000) + i * 2000),
        "avg_packet_size"   : _rf(200.0, 600.0 + i * 400.0),
        "dest_count"        : _ri(1, max(1, int(4 - i * 2))),
        "activity_hour"     : _ri(0, 23),
        **_meta(),
    }


def port_scan(intensity: float = 1.0) -> dict[str, Any]:
    """
    Port / Network Scan
    Triggers Rule 3 (destination spread).
    
    Intensity 0.3 → ~15 unique IPs (MEDIUM)
    Intensity 1.0 → ~50 unique IPs (HIGH)
    Also triggers Rule 4 (off-hours) at high intensity.
    """
    i = _clamp(intensity, 0.0, 1.0)
    hour = random.choice(list(range(0, 6)) + list(range(22, 24))) if i > 0.5 else _ri(0, 23)
    return {
        "attack_type"       : "port_scan",
        "intensity"         : round(i, 2),
        "packets_per_window": _ri(100, int(200 + i * 500)),
        "avg_packet_size"   : _rf(40.0, 80.0 + i * 60.0),
        "dest_count"        : int(_ri(8, 10) + i * 40),
        "activity_hour"     : hour,
        **_meta(),
    }


def data_exfiltration(intensity: float = 1.0) -> dict[str, Any]:
    """
    Data Exfiltration (bulk outbound transfer)
    Triggers Rule 2 (large packet size).
    
    Intensity 0.3 → ~1050B avg (LOW)
    Intensity 1.0 → ~1420B avg (HIGH)
    Also triggers Rule 4 (off-hours) at moderate+ intensity.
    """
    i = _clamp(intensity, 0.0, 1.0)
    hour = random.choice(range(0, 6)) if i > 0.4 else _ri(0, 23)
    return {
        "attack_type"       : "data_exfiltration",
        "intensity"         : round(i, 2),
        "packets_per_window": _ri(80, int(150 + i * 200)),
        "avg_packet_size"   : _rf(900.0 + i * 200.0, 1450.0),
        "dest_count"        : _ri(1, max(1, int(3 - i))),
        "activity_hour"     : hour,
        **_meta(),
    }


def suspicious_timing(intensity: float = 1.0) -> dict[str, Any]:
    """
    Suspicious Off-Hours Activity
    Triggers Rule 4 (timing anomaly). Always off-hours.
    
    Low volume, designed to stay under other thresholds.
    This is the hardest to detect — only the timing rule fires.
    """
    i = _clamp(intensity, 0.0, 1.0)
    return {
        "attack_type"       : "suspicious_timing",
        "intensity"         : round(i, 2),
        "packets_per_window": _ri(30, int(100 + i * 200)),
        "avg_packet_size"   : _rf(300.0, 700.0),
        "dest_count"        : _ri(1, 4),
        "activity_hour"     : random.choice(range(0, 6)),
        **_meta(),
    }


def normal_traffic() -> dict[str, Any]:
    """
    Baseline healthy traffic.
    Business hours, low packet count, normal frame size.
    """
    return {
        "attack_type"       : "normal",
        "intensity"         : 0.0,
        "packets_per_window": _ri(10, 120),
        "avg_packet_size"   : _rf(200.0, 700.0),
        "dest_count"        : _ri(1, 4),
        "activity_hour"     : _ri(7, 21),
        **_meta(),
    }


# ══════════════════════════════════════════════════════════════
# REGISTRY + CONVENIENCE
# ══════════════════════════════════════════════════════════════

ATTACK_REGISTRY: dict[str, Any] = {
    "ddos"              : ddos,
    "port_scan"         : port_scan,
    "data_exfiltration" : data_exfiltration,
    "suspicious_timing" : suspicious_timing,
    "normal"            : normal_traffic,
}

ATTACK_LABELS = {
    "normal"            : "Normal Traffic",
    "ddos"              : "DDoS / Packet Flood",
    "port_scan"         : "Port / IP Scan",
    "data_exfiltration" : "Data Exfiltration",
    "suspicious_timing" : "Suspicious Off-Hours",
}


def generate(attack_type: str, intensity: float = 1.0) -> dict[str, Any]:
    """
    Generate a traffic snapshot by attack type name.

    Usage:
        snap = generate("ddos", intensity=0.6)
        snap = generate("normal")
    """
    fn = ATTACK_REGISTRY.get(attack_type)
    if fn is None:
        raise ValueError(
            f"Unknown attack type '{attack_type}'. "
            f"Valid: {list(ATTACK_REGISTRY.keys())}"
        )
    return fn() if attack_type == "normal" else fn(intensity=intensity)