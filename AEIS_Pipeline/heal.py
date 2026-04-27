from __future__ import annotations

import time
from typing import Any

from .response import system_state, logger

CLEAN_WINDOWS_TO_RELAX   = 3
CLEAN_WINDOWS_TO_RECOVER = 6

heal_state: dict[str, Any] = {
    "stage"              : "NORMAL",
    "clean_window_count" : 0,
    "previous_threat"    : "NORMAL",
    "heal_log"           : [],
    "last_heal_ts"       : 0,
}


def _log(event: str) -> None:
    entry = f"[{int(time.time())}] {event}"
    heal_state["heal_log"].append(entry)
    logger.info("💊  HEAL: %s", event)


def notify_threat_cleared(threat_level_was: str) -> None:
    if heal_state["stage"] != "NORMAL":
        return

    if threat_level_was in ("HIGH", "MEDIUM"):
        heal_state["stage"]              = "RECOVERING_STRICT"
        heal_state["clean_window_count"] = 0
        heal_state["previous_threat"]    = threat_level_was
        heal_state["last_heal_ts"]       = int(time.time())
        _log(f"HEAL STARTED after {threat_level_was}")


def heal(current_detection_level: str = "NORMAL") -> dict[str, Any]:

    # 🔴 LOCKDOWN MODE: once HIGH → never auto-recover
    if system_state["camera_active"] is False:
        return {
            "status": "LOCKED",
            "actions_taken": ["System in LOCKDOWN — manual reset required"],
            "clean_windows": 0,
            "system_state": _snapshot(),
        }

    if heal_state["stage"] == "NORMAL":
        return {
            "status": "NORMAL",
            "actions_taken": ["no_action_required"],
            "clean_windows": 0,
            "system_state": _snapshot(),
        }

    if current_detection_level == "NORMAL":
        heal_state["clean_window_count"] += 1
    else:
        heal_state["clean_window_count"] = 0

    return {
        "status": heal_state["stage"],
        "actions_taken": ["healing_paused"],
        "clean_windows": heal_state["clean_window_count"],
        "system_state": _snapshot(),
    }


def reset_heal_state() -> None:
    heal_state.update({
        "stage"              : "NORMAL",
        "clean_window_count" : 0,
        "previous_threat"    : "NORMAL",
        "heal_log"           : [],
        "last_heal_ts"       : 0,
    })

    system_state["camera_active"] = True
    system_state["blocked_ips"] = []
    system_state["monitoring_mode"] = False


def _snapshot() -> dict[str, Any]:
    return {
        "camera_active"  : system_state["camera_active"],
        "monitoring_mode": system_state["monitoring_mode"],
        "blocked_ips"    : list(system_state["blocked_ips"]),
        "threat_level"   : system_state["threat_level"],
    }

def get_heal_status():
    return {
        "stage": heal_state["stage"],
        "clean_windows": heal_state["clean_window_count"],
        "prev_threat": heal_state["previous_threat"],
    }

def get_heal_log():
    return list(heal_state["heal_log"])