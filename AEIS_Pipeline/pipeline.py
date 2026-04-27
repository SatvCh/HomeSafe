"""
AEIS — Main Pipeline
pipeline.py

Integrates: detect → respond → heal

run_pipeline(snapshot) is the single entry point called by server.py.
"""

from __future__ import annotations

import time
from typing import Any

from . import detection
from . import response
from . import heal as heal_module
from .heal import notify_threat_cleared, reset_heal_state, get_heal_status


# ── Pipeline state ──────────────────────────────────────────────────────────────

_pipeline_state: dict[str, Any] = {
    "previous_threat_level": "NORMAL",
    "tick"                 : 0,
}


# ── Core function ───────────────────────────────────────────────────────────────

def run_pipeline(
    snapshot: dict[str, Any],
    source_ip: str = "192.168.29.36",
) -> dict[str, Any]:
    """
    Run one full pipeline tick.

    Parameters
    ----------
    snapshot  : Dict with packets_per_window, avg_packet_size,
                dest_count, activity_hour
    source_ip : Camera or device IP to target with response actions

    Returns
    -------
    {
        tick, detection, response, heal, pipeline_ok, timestamp
    }
    """
    _pipeline_state["tick"] += 1
    tick = _pipeline_state["tick"]

    # ── 1. DETECT ──────────────────────────────────────────────────────────────
    det = detection.detect(
        packets_per_window = int(snapshot.get("packets_per_window", 0)),
        avg_packet_size    = float(snapshot.get("avg_packet_size", 0.0)),
        dest_count         = int(snapshot.get("dest_count", 0)),
        activity_hour      = int(snapshot.get("activity_hour", 12)),
    )

    # ── 2. RESPOND ─────────────────────────────────────────────────────────────
    resp = response.respond(det, source_ip=source_ip)

    # ── 3. HEAL ────────────────────────────────────────────────────────────────
    prev = _pipeline_state["previous_threat_level"]

    # Notify heal system when transitioning from a real threat back to NORMAL
    if det["threat_level"] == "NORMAL" and prev in ("HIGH", "MEDIUM"):
        notify_threat_cleared(threat_level_was=prev)

    heal_result = heal_module.heal(current_detection_level=det["threat_level"])

    # Track previous state for next tick
    _pipeline_state["previous_threat_level"] = det["threat_level"]

    return {
        "tick"        : tick,
        "detection"   : det,
        "response"    : resp,
        "heal"        : heal_result,
        "pipeline_ok" : True,
        "timestamp"   : int(time.time()),
    }


def get_pipeline_state() -> dict[str, Any]:
    return dict(_pipeline_state)