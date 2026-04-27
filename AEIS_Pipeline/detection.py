"""
AEIS — Rule-Based Anomaly Detection
detection.py

╔══════════════════════════════════════════════════════════════════════╗
║   THE 4 RULES — HOW DETECTION WORKS                                 ║
╠══════════════════════════════════════════════════════════════════════╣
║                                                                      ║
║  RULE 1 — PACKET FLOOD (DDoS Detection)                             ║
║    We count how many packets arrive in a 5-second window.           ║
║    Normal camera traffic: 10–120 packets/window                     ║
║    A DDoS attack floods with hundreds or thousands of packets.      ║
║    → 300–699  packets = LOW   (eyebrow-raising)                     ║
║    → 700–1499 packets = MEDIUM (suspicious burst)                   ║
║    → 1500+    packets = HIGH  (almost certainly a flood)            ║
║                                                                      ║
║  RULE 2 — PACKET SIZE (Data Exfiltration Detection)                 ║
║    We measure the average size of each network frame in bytes.      ║
║    Normal camera streaming: 200–700 bytes/packet                    ║
║    Data exfiltration sends large bulk frames (near the 1500B max).  ║
║    → 1000–1199B avg = LOW   (slightly elevated)                     ║
║    → 1200–1399B avg = MEDIUM (bulk transfer likely)                 ║
║    → 1400B+    avg  = HIGH  (near MTU — exfiltration signature)     ║
║                                                                      ║
║  RULE 3 — DESTINATION SPREAD (Port/IP Scan Detection)              ║
║    We count how many unique destination IPs appear per window.      ║
║    A camera normally talks to 1–4 servers (stream, NTP, etc.)       ║
║    A scanner rapidly probes many different IPs.                     ║
║    → 5–11  unique IPs = LOW   (minor spread)                        ║
║    → 12–24 unique IPs = MEDIUM (likely scanning)                    ║
║    → 25+   unique IPs = HIGH  (aggressive scan)                     ║
║                                                                      ║
║  RULE 4 — ACTIVITY HOUR (Timing Anomaly Detection)                  ║
║    We check what hour the traffic occurs.                           ║
║    Cameras accessed at 10 PM – 6 AM are inherently suspicious.     ║
║    Could be an insider threat, malware beacon, or unauthorized      ║
║    access attempt.                                                  ║
║    → Off-hours (22:00–05:59) = MEDIUM (always)                     ║
║                                                                      ║
║  COMBINATION SCORING:                                               ║
║    The final threat level = worst single rule triggered.            ║
║    Confidence = 0.25 per rule triggered (max 0.95).                 ║
║    Multiple rules firing = higher confidence in the assessment.     ║
║                                                                      ║
╚══════════════════════════════════════════════════════════════════════╝

Outputs:
    {
        "threat_level" : "NORMAL" | "LOW" | "MEDIUM" | "HIGH",
        "reason"       : str,
        "confidence"   : float  (0.0 – 1.0),
        "flags"        : list[str],
        "rule_hits"    : dict   (detail per rule)
    }
"""

from __future__ import annotations
from typing import Any


# ══════════════════════════════════════════════════════════════
# THRESHOLDS  (tune these per your network environment)
# ══════════════════════════════════════════════════════════════

class Thresholds:
    # Rule 1 — Packet flood (DDoS)
    PACKETS_LOW    = 300     # start worrying
    PACKETS_MEDIUM = 700     # suspicious burst
    PACKETS_HIGH   = 1500    # almost certainly an attack

    # Rule 2 — Packet size (Data exfiltration)
    SIZE_LOW    = 1000.0    # slightly elevated
    SIZE_MEDIUM = 1200.0    # bulk transfer
    SIZE_HIGH   = 1400.0    # near MTU — exfil signature

    # Rule 3 — Destination spread (IP/Port scanning)
    DEST_LOW    = 5         # minor spread
    DEST_MEDIUM = 12        # likely scanning
    DEST_HIGH   = 25        # aggressive scan

    # Rule 4 — Off-hours window (22:00 – 05:59)
    OFFHOURS_START = 22     # 10 PM
    OFFHOURS_END   = 6      # 6 AM (exclusive)

    # Confidence scoring
    WEIGHT_PER_FLAG = 0.25  # each rule adds 25% confidence


T = Thresholds()


# ══════════════════════════════════════════════════════════════
# INDIVIDUAL RULE FUNCTIONS
# ══════════════════════════════════════════════════════════════

def _rule_packet_flood(packets: int) -> tuple[str | None, str, dict]:
    """
    Rule 1: DDoS / Flood Detection
    A camera generates 10–120 packets in a 5-second window under normal load.
    Anything above 300 suggests abnormal traffic injection.
    """
    detail = {"rule": "packet_flood", "value": packets, "unit": "packets/window"}

    if packets >= T.PACKETS_HIGH:
        detail.update({"triggered": True, "threshold": T.PACKETS_HIGH, "level": "HIGH"})
        return "HIGH", (
            f"Packet FLOOD: {packets} pkt/window "
            f"(threshold {T.PACKETS_HIGH}) → DDoS likely"
        ), detail

    if packets >= T.PACKETS_MEDIUM:
        detail.update({"triggered": True, "threshold": T.PACKETS_MEDIUM, "level": "MEDIUM"})
        return "MEDIUM", (
            f"High packet rate: {packets} pkt/window → burst or scan"
        ), detail

    if packets >= T.PACKETS_LOW:
        detail.update({"triggered": True, "threshold": T.PACKETS_LOW, "level": "LOW"})
        return "LOW", (
            f"Elevated packet rate: {packets} pkt/window (baseline 10–120)"
        ), detail

    detail.update({"triggered": False})
    return None, "", detail


def _rule_packet_size(size: float) -> tuple[str | None, str, dict]:
    """
    Rule 2: Data Exfiltration Detection
    Normal RTSP/camera streaming uses 200–700 byte frames.
    Near-MTU (1400+B) frames in bulk = someone sending data out.
    """
    detail = {"rule": "packet_size", "value": round(size, 1), "unit": "bytes/packet avg"}

    if size >= T.SIZE_HIGH:
        detail.update({"triggered": True, "threshold": T.SIZE_HIGH, "level": "HIGH"})
        return "HIGH", (
            f"Near-MTU frames: avg {size:.0f}B "
            f"(threshold {T.SIZE_HIGH}B) → data exfiltration"
        ), detail

    if size >= T.SIZE_MEDIUM:
        detail.update({"triggered": True, "threshold": T.SIZE_MEDIUM, "level": "MEDIUM"})
        return "MEDIUM", (
            f"Large frames: avg {size:.0f}B → bulk transfer"
        ), detail

    if size >= T.SIZE_LOW:
        detail.update({"triggered": True, "threshold": T.SIZE_LOW, "level": "LOW"})
        return "LOW", (
            f"Slightly elevated frame size: avg {size:.0f}B"
        ), detail

    detail.update({"triggered": False})
    return None, "", detail


def _rule_dest_spread(dest_count: int) -> tuple[str | None, str, dict]:
    """
    Rule 3: IP/Port Scan Detection
    A camera talks to 1–4 IPs (stream server, NTP, DNS, etc.).
    Sudden contact with 25+ unique destinations = network scanning.
    """
    detail = {"rule": "dest_spread", "value": dest_count, "unit": "unique destination IPs"}

    if dest_count >= T.DEST_HIGH:
        detail.update({"triggered": True, "threshold": T.DEST_HIGH, "level": "HIGH"})
        return "HIGH", (
            f"Destination spread: {dest_count} unique IPs → aggressive scan"
        ), detail

    if dest_count >= T.DEST_MEDIUM:
        detail.update({"triggered": True, "threshold": T.DEST_MEDIUM, "level": "MEDIUM"})
        return "MEDIUM", (
            f"Destination spread: {dest_count} unique IPs → port scan"
        ), detail

    if dest_count >= T.DEST_LOW:
        detail.update({"triggered": True, "threshold": T.DEST_LOW, "level": "LOW"})
        return "LOW", (
            f"Destination spread: {dest_count} unique IPs → minor anomaly"
        ), detail

    detail.update({"triggered": False})
    return None, "", detail


def _rule_activity_hour(hour: int) -> tuple[str | None, str, dict]:
    """
    Rule 4: Off-Hours Activity Detection
    Cameras being accessed between 10 PM and 6 AM is abnormal.
    Could be an insider threat, scheduled malware, or unauthorized access.
    """
    detail = {"rule": "activity_hour", "value": hour, "unit": "hour (0-23)"}
    is_offhours = (hour >= T.OFFHOURS_START or hour < T.OFFHOURS_END)

    if is_offhours:
        detail.update({"triggered": True, "level": "MEDIUM"})
        return "MEDIUM", (
            f"Off-hours traffic: {hour:02d}:00 "
            f"(suspicious window: {T.OFFHOURS_START}:00–{T.OFFHOURS_END:02d}:00)"
        ), detail

    detail.update({"triggered": False})
    return None, "", detail


# ══════════════════════════════════════════════════════════════
# SEVERITY RANKING
# ══════════════════════════════════════════════════════════════

_RANK = {"NORMAL": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}

def _max_severity(*levels: str | None) -> str:
    valid = [lvl for lvl in levels if lvl is not None]
    if not valid:
        return "NORMAL"
    return max(valid, key=lambda lvl: _RANK.get(lvl, 0))


# ══════════════════════════════════════════════════════════════
# PUBLIC API
# ══════════════════════════════════════════════════════════════

def detect(
    packets_per_window: int,
    avg_packet_size: float,
    dest_count: int,
    activity_hour: int,
) -> dict[str, Any]:
    """
    Run all 4 rules and return a combined threat assessment.

    Returns
    -------
    {
        threat_level : "NORMAL" | "LOW" | "MEDIUM" | "HIGH"
        reason       : human-readable explanation
        confidence   : 0.0–1.0 (more rules = higher confidence)
        flags        : list of severity strings per rule that fired
        rule_hits    : detailed dict per rule for debugging/UI
    }
    """
    flags: list[str] = []
    reasons: list[str] = []
    severities: list[str | None] = []
    rule_hits: dict[str, Any] = {}

    # Run all 4 rules
    rules = [
        _rule_packet_flood(packets_per_window),
        _rule_packet_size(avg_packet_size),
        _rule_dest_spread(dest_count),
        _rule_activity_hour(activity_hour),
    ]

    for sev, reason, detail in rules:
        rule_name = detail["rule"]
        rule_hits[rule_name] = detail
        severities.append(sev)
        if sev is not None:
            flags.append(sev)
            reasons.append(reason)

    threat_level = _max_severity(*severities)

    # Confidence: 0.25 per rule that fired, minimum 0.05 for NORMAL
    if threat_level == "NORMAL":
        confidence = 0.05
    else:
        confidence = min(len(flags) * T.WEIGHT_PER_FLAG, 0.95)
        if threat_level == "HIGH":
            confidence = max(confidence, 0.75)

    primary_reason = (
        "; ".join(reasons) if reasons else "All metrics within normal range"
    )

    return {
        "threat_level": threat_level,
        "reason"      : primary_reason,
        "confidence"  : round(confidence, 4),
        "flags"       : flags,
        "rule_hits"   : rule_hits,
        # pass-through raw values for the /alert endpoint
        "packets"     : packets_per_window,
        "avg_size"    : avg_packet_size,
        "dest_count"  : dest_count,
        "hour"        : activity_hour,
    }


# ══════════════════════════════════════════════════════════════
# SELF-TEST
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    cases = [
        ("Normal baseline",        50,  400.0,  2, 14),
        ("Mild late-night",        80,  450.0,  3,  2),
        ("Size anomaly (LOW)",     60, 1050.0,  2, 10),
        ("Dest spread (MEDIUM)",  200,  350.0, 14, 11),
        ("Rate spike (MEDIUM)",   750,  400.0,  3, 15),
        ("Exfil + off-hours",     100, 1350.0,  4, 23),
        ("DDoS (HIGH)",          1800,  400.0,  2, 14),
        ("Scan + flood (HIGH)",  1600,  300.0, 30,  3),
    ]

    print(f"\n{'='*70}")
    print("  AEIS Rule-Based Detection — Self Test")
    print(f"{'='*70}\n")

    for label, pkts, size, dests, hour in cases:
        r = detect(pkts, size, dests, hour)
        print(f"  [{label}]")
        print(f"    Level: {r['threat_level']}  Confidence: {r['confidence']}")
        print(f"    Reason: {r['reason']}\n")