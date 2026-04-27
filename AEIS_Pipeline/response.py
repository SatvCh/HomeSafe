"""
AEIS — Threat Response System
response.py

╔══════════════════════════════════════════════════════════════════════╗
║   RESPONSE ACTIONS PER THREAT LEVEL                                  ║
╠══════════════════════════════════════════════════════════════════════╣
║                                                                      ║
║  NORMAL  → Heartbeat log only. No action needed.                    ║
║                                                                      ║
║  LOW     → Log warning + set dashboard yellow flag.                 ║
║            Camera stays UP. No blocking.                            ║
║            "Something looks off, keep watching."                    ║
║                                                                      ║
║  MEDIUM  → Alert user via dashboard + enter monitoring mode.        ║
║            Monitoring mode = doubled log frequency.                 ║
║            Camera stays UP. Source IP is flagged (not blocked).     ║
║            "Suspicious — watch closely, prepare to act."            ║
║                                                                      ║
║  HIGH    → Camera stream ISOLATED (shutdown).                       ║
║            Source IP BLOCKED (simulated firewall rule).             ║
║            Monitoring mode ON (aggressive logging).                 ║
║            Alert sent to dashboard with full detail.                ║
║            "Definite attack — cut off the threat immediately."      ║
║                                                                      ║
╚══════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

# ── Logging setup ──────────────────────────────────────────────────────────────

_LOG_DIR = Path(__file__).parent / "logs"
_LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s  [%(levelname)-8s]  %(message)s",
    handlers=[
        logging.FileHandler(_LOG_DIR / "aeis_events.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("AEIS.Response")


# ── Mutable system state ───────────────────────────────────────────────────────
# This is the single source of truth for the system.
# heal.py reads and resets this. server.py reads it for /alert.

system_state: dict[str, Any] = {
    "camera_active"  : True,
    "monitoring_mode": False,
    "blocked_ips"    : [],
    "threat_level"   : "NORMAL",
    "last_event_ts"  : 0,
    # Raw traffic data (updated each tick for /traffic endpoint)
    "last_snapshot"  : {},
}


# ── Simulation stubs ───────────────────────────────────────────────────────────
# In production: replace these with real subprocess/iptables/netsh calls.

def _camera_shutdown(reason: str) -> str:
    system_state["camera_active"] = False
    msg = f"CAMERA ISOLATED — {reason}"
    logger.warning("🎥  %s", msg)
    return msg


def _camera_restore() -> str:
    system_state["camera_active"] = True
    msg = "CAMERA RESTORED — stream re-enabled"
    logger.info("🎥  %s", msg)
    return msg


def _block_ip(ip: str) -> str:
    if ip not in system_state["blocked_ips"]:
        system_state["blocked_ips"].append(ip)
    msg = f"IP BLOCKED: {ip} (simulated firewall rule)"
    logger.warning("🚫  %s", msg)
    return msg


def _unblock_ip(ip: str) -> str:
    if ip in system_state["blocked_ips"]:
        system_state["blocked_ips"].remove(ip)
    msg = f"IP UNBLOCKED: {ip}"
    logger.info("🔓  %s", msg)
    return msg


def _enter_monitoring() -> str:
    system_state["monitoring_mode"] = True
    msg = "MONITORING MODE ON — log frequency doubled"
    logger.info("🔍  %s", msg)
    return msg


def _exit_monitoring() -> str:
    system_state["monitoring_mode"] = False
    msg = "MONITORING MODE OFF — returned to normal"
    logger.info("📉  %s", msg)
    return msg


def _send_alert(message: str) -> str:
    msg = f"ALERT → {message}"
    logger.warning("🔔  %s", msg)
    return msg


# ── Response handlers ──────────────────────────────────────────────────────────

def _respond_normal(detection: dict, source_ip: str) -> list[str]:
    logger.debug("✅  NORMAL traffic — heartbeat OK")
    return ["heartbeat_logged"]


def _respond_low(detection: dict, source_ip: str) -> list[str]:
    reason = detection.get("reason", "Low-level anomaly")
    logger.info("🟡  LOW threat from %s: %s", source_ip, reason)
    return [
        f"event_logged: {reason}",
        "dashboard_flag: YELLOW — minor anomaly detected",
    ]


def _respond_medium(detection: dict, source_ip: str) -> list[str]:
    reason = detection.get("reason", "Medium-level anomaly")
    actions = [
        _send_alert(f"Medium threat from {source_ip}: {reason}"),
        _enter_monitoring(),
        f"ip_flagged: {source_ip} (not blocked yet)",
        f"event_logged: {reason}",
    ]
    logger.warning("🟠  MEDIUM threat from %s: %s", source_ip, reason)
    return actions


def _respond_high(detection: dict, source_ip: str) -> list[str]:
    reason = detection.get("reason", "High-level threat")
    actions = [
        _send_alert(f"HIGH THREAT from {source_ip} — initiating lockdown"),
        _camera_shutdown(reason=reason),
        _block_ip(ip=source_ip),
        _enter_monitoring(),
        f"event_logged: {reason}",
    ]
    logger.error("🔴  HIGH threat from %s: %s", source_ip, reason)
    return actions


# ── Public API ─────────────────────────────────────────────────────────────────

def respond(
    detection: dict[str, Any],
    source_ip: str = "192.168.1.100",
) -> dict[str, Any]:
    """
    Execute the appropriate response for a given detection result.

    Parameters
    ----------
    detection  : Output dict from detection.detect()
    source_ip  : IP of the device under observation

    Returns
    -------
    Full response record with all state fields
    """
    threat_level = detection.get("threat_level", "NORMAL")
    system_state["threat_level"]  = threat_level
    system_state["last_event_ts"] = int(time.time())

    # Store snapshot for /traffic endpoint
    system_state["last_snapshot"] = {
        "packets_per_window": detection.get("packets", 0),
        "avg_packet_size"   : detection.get("avg_size", 0.0),
        "dest_count"        : detection.get("dest_count", 0),
        "activity_hour"     : detection.get("hour", 0),
    }

    dispatch = {
        "NORMAL": _respond_normal,
        "LOW"   : _respond_low,
        "MEDIUM": _respond_medium,
        "HIGH"  : _respond_high,
    }

    handler = dispatch.get(threat_level, _respond_normal)
    actions_taken = handler(detection, source_ip)

    alert_messages = {
        "NORMAL" : "System operating normally.",
        "LOW"    : "Minor anomaly detected. Monitoring recommended.",
        "MEDIUM" : f"Suspicious activity from {source_ip}. Monitoring active.",
        "HIGH"   : f"CRITICAL: Attack from {source_ip}. Camera isolated, IP blocked.",
    }

    return {
        "threat_level"   : threat_level,
        "actions_taken"  : actions_taken,
        "monitoring_mode": system_state["monitoring_mode"],
        "camera_active"  : system_state["camera_active"],
        "blocked_ips"    : list(system_state["blocked_ips"]),
        "alert_message"  : alert_messages.get(threat_level, ""),
        "source_ip"      : source_ip,
        "timestamp"      : system_state["last_event_ts"],
    }