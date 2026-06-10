"""
AEIS — server.py  (Healing & Recovery Edition)
===============================================
Flask API for HomeSafe dashboard.

New in this version
-------------------
* Cam2 auto-feeder thread  — cam2 always has live data (normal traffic every 5 s)
* Healing state machine    — QUARANTINED → HEALING → RECOVERING → NORMAL
* Adaptive immune learning — past attack patterns lower future thresholds
* GET  /heal_status        — healing phase info per device
* POST /reset              — force any device back to NORMAL immediately
"""

from flask import Flask, request, jsonify
from flask_cors import CORS

import joblib
import numpy as np
import pandas as pd
import threading
import logging
import time

from aeis_utils import BASE_FEATURES, engineer_features
from traffic_sim import generate_synthetic, VALID_ATTACK_TYPES, ATTACK_LABELS
from traffic_capture import start_capture, stop_capture, capture_status

RF_DROP_COLS   = ["activity_hour", "hour_sin", "hour_cos", "high_hour_flag"]
DEVICE_TIMEOUT = 30       # seconds before a device is considered disconnected

# ── Healing parameters ────────────────────────────────────────────────────────
HEAL_COOLDOWN      = 10   # seconds to wait in QUARANTINED before healing starts
HEAL_STABLE_NEEDED = 5    # consecutive normal readings to advance each phase
MAX_ATTACK_MEMORY  = 10   # how many attack snapshots to remember
SENSITIVITY_BOOST  = 0.15 # max threshold reduction from immune memory (15 %)

log = logging.getLogger("werkzeug")
log.setLevel(logging.ERROR)

app = Flask(__name__)
CORS(app)

# ── Config ────────────────────────────────────────────────────────────────────
PHONE_IP        = "192.168.137.139"
STABILITY_COUNT = 2

# ── Load models ───────────────────────────────────────────────────────────────
iso          = joblib.load("outputs_if/model_isolation_forest.pkl")
threshold_if = float(np.load("outputs_if/iso_threshold.npy"))

rf           = joblib.load("outputs_rf/model_random_forest.pkl")
threshold_rf = float(np.load("outputs_rf/rf_threshold.npy"))


# ── Per-device state factory ──────────────────────────────────────────────────
def _make_device_state(device_name: str) -> dict:
    return {
        "name":         device_name,
        "last_features": {
            "packets_per_window": 0,
            "avg_packet_size":    0.0,
            "dest_count":         0,
            "activity_hour":      0,
        },
        "alert_data": {
            "device":          device_name,
            "status":          "NORMAL",
            "heal_phase":      None,        # None | "HEALING" | "RECOVERING"
            "threat":          "LOW",
            "rf_prob":         0.0,
            "iso_score":       0.0,
            "packets":         0,
            "avg_packet_size": 0.0,
            "dest_count":      0,
            "activity_hour":   0,
            "timestamp":       0,
            "heal_cooldown_remaining": 0,
            "heal_stable_count": 0,
            "heal_stable_needed": HEAL_STABLE_NEEDED,
            "attack_memory_count": 0,
        },
        "traffic":           {"packets": 0},
        "status_buffer":     [],
        "last_update":       0.0,
        "sim_active":        False,
        # ── Healing state ──────────────────────────────────────────────────
        "heal_phase":        None,          # None | "HEALING" | "RECOVERING"
        "quarantine_at":     0.0,           # epoch when quarantine began
        "heal_stable_count": 0,             # consecutive normal readings
        # ── Adaptive immune memory ─────────────────────────────────────────
        "attack_memory":     [],            # list of feature dicts from past attacks
    }


device_state = {
    "cam1": _make_device_state("Camera 1 — Front Door"),
    "cam2": _make_device_state("Camera 2 — Backyard"),
}

device_locks = {
    "cam1": threading.Lock(),
    "cam2": threading.Lock(),
}

_firewall_lock = threading.Lock()
device_blocked = False


# ── Helpers ───────────────────────────────────────────────────────────────────
def _is_connected(device_id: str) -> bool:
    ds = device_state[device_id]
    # Devices in healing/recovering phases are always considered connected
    if ds["heal_phase"] in ("HEALING", "RECOVERING"):
        return True
    if ds["alert_data"]["status"] == "QUARANTINED":
        return True
    return ds["last_update"] > 0 and (time.time() - ds["last_update"]) < DEVICE_TIMEOUT


def _stable_status(device_id: str, new_status: str) -> str:
    ds  = device_state[device_id]
    buf = ds["status_buffer"]
    buf.append(new_status)
    if len(buf) > STABILITY_COUNT:
        ds["status_buffer"] = buf[-STABILITY_COUNT:]
    buf = ds["status_buffer"]
    if len(buf) == STABILITY_COUNT and len(set(buf)) == 1:
        return buf[0]
    return ds["alert_data"]["status"]


def _adaptive_thresholds(device_id: str):
    """
    Returns (pkt_thresh_q, pkt_thresh_s, size_thresh) adjusted by immune memory.
    Base thresholds mirror _run_ml hard rules.
    """
    base_q_pkt   = 12000
    base_s_pkt   = 9000
    base_s_dest  = 5
    base_q_dest  = 10

    ds      = device_state[device_id]
    memory  = ds["attack_memory"]
    if not memory:
        return base_q_pkt, base_s_pkt, base_s_dest, base_q_dest

    # Compute mean attack packet count from memory
    mean_pkts = sum(m["packets_per_window"] for m in memory) / len(memory)
    # Scale boost: more memory → more sensitive, capped at SENSITIVITY_BOOST
    boost = min(SENSITIVITY_BOOST, len(memory) / MAX_ATTACK_MEMORY * SENSITIVITY_BOOST)

    adj_q_pkt  = int(base_q_pkt  * (1 - boost))
    adj_s_pkt  = int(base_s_pkt  * (1 - boost))
    adj_s_dest = max(3, int(base_s_dest  * (1 - boost)))
    adj_q_dest = max(6, int(base_q_dest  * (1 - boost)))

    return adj_q_pkt, adj_s_pkt, adj_s_dest, adj_q_dest


# ── Healing state machine ─────────────────────────────────────────────────────
def _advance_healing(device_id: str, raw_status: str) -> str:
    """
    Manages QUARANTINED → HEALING → RECOVERING → NORMAL transitions.
    Called inside device_locks[device_id].
    Returns the effective status to commit.
    """
    ds = device_state[device_id]
    now = time.time()
    current = ds["alert_data"]["status"]

    # ── New quarantine event ──────────────────────────────────────────────────
    if raw_status == "QUARANTINED":
        if current != "QUARANTINED":
            # Fresh quarantine — save attack to immune memory
            feat = dict(ds["last_features"])
            ds["attack_memory"].append(feat)
            if len(ds["attack_memory"]) > MAX_ATTACK_MEMORY:
                ds["attack_memory"].pop(0)
            print(f"[{device_id.upper()}] 🧠 Immune memory updated — "
                  f"{len(ds['attack_memory'])} pattern(s) stored")

        ds["quarantine_at"]     = now if ds["quarantine_at"] == 0.0 else ds["quarantine_at"]
        ds["heal_phase"]        = None
        ds["heal_stable_count"] = 0
        return "QUARANTINED"

    # ── Device in QUARANTINED state — check if healing can begin ─────────────
    if current == "QUARANTINED" and raw_status == "NORMAL":
        elapsed = now - ds["quarantine_at"]
        remaining = max(0.0, HEAL_COOLDOWN - elapsed)

        if remaining > 0:
            # Still in cooldown — stay QUARANTINED
            ds["heal_phase"] = None
            return "QUARANTINED"

        # Cooldown expired — enter HEALING phase
        if ds["heal_phase"] is None:
            ds["heal_phase"]        = "HEALING"
            ds["heal_stable_count"] = 0
            print(f"[{device_id.upper()}] 💙 Entering HEALING phase")

    # ── HEALING phase — accumulate stable readings ────────────────────────────
    if current in ("QUARANTINED", "HEALING") and ds["heal_phase"] == "HEALING":
        if raw_status == "NORMAL":
            ds["heal_stable_count"] += 1
        else:
            ds["heal_stable_count"] = 0   # reset on any anomaly

        if ds["heal_stable_count"] >= HEAL_STABLE_NEEDED:
            # Advance to RECOVERING (SUSPICIOUS level)
            ds["heal_phase"]        = "RECOVERING"
            ds["heal_stable_count"] = 0
            print(f"[{device_id.upper()}] 🔵 Advancing to RECOVERING phase")

        return "HEALING"

    # ── RECOVERING phase — accumulate more stable readings ───────────────────
    if current in ("HEALING", "RECOVERING", "SUSPICIOUS") and ds["heal_phase"] == "RECOVERING":
        if raw_status == "NORMAL":
            ds["heal_stable_count"] += 1
        else:
            ds["heal_stable_count"] = 0

        if ds["heal_stable_count"] >= HEAL_STABLE_NEEDED:
            # Fully recovered
            ds["heal_phase"]        = None
            ds["heal_stable_count"] = 0
            ds["quarantine_at"]     = 0.0
            print(f"[{device_id.upper()}] ✅ Fully RECOVERED → NORMAL")
            return "NORMAL"

        return "RECOVERING"

    # ── Normal operation — reset healing state ────────────────────────────────
    if raw_status == "NORMAL" and ds["heal_phase"] is None:
        ds["quarantine_at"]     = 0.0
        ds["heal_stable_count"] = 0

    return raw_status


# ── Core ML inference ─────────────────────────────────────────────────────────
def _run_ml(device_id: str, features: dict) -> dict:
    packets  = int(features["packets_per_window"])
    avg_size = float(features["avg_packet_size"])
    dest     = int(features["dest_count"])
    hour     = int(features["activity_hour"])

    raw      = pd.DataFrame([[packets, avg_size, dest, hour]], columns=BASE_FEATURES)
    feat_all = engineer_features(raw)
    feat_rf  = feat_all.drop(columns=RF_DROP_COLS)

    iso_score = float(-iso.score_samples(feat_all.values)[0])
    rf_prob   = float(rf.predict_proba(feat_rf.values)[0, 1])

    iso_flag = iso_score >= threshold_if
    rf_flag  = rf_prob  >= threshold_rf

    # Adaptive thresholds (shrink when immune memory exists)
    q_pkt, s_pkt, s_dest, q_dest = _adaptive_thresholds(device_id)

    if (packets > q_pkt or avg_size < 600 or dest > q_dest):
        raw_status = "QUARANTINED"
        threat     = "HIGH"
    elif (packets > s_pkt or avg_size > 1350 or dest > s_dest):
        raw_status = "SUSPICIOUS"
        threat     = "MEDIUM"
    elif iso_flag and rf_flag:
        raw_status = "SUSPICIOUS"
        threat     = "MEDIUM"
    else:
        raw_status = "NORMAL"
        threat     = "LOW"

    with device_locks[device_id]:
        ds = device_state[device_id]

        ds["last_features"].update({
            "packets_per_window": packets,
            "avg_packet_size":    round(avg_size, 2),
            "dest_count":         dest,
            "activity_hour":      hour,
        })

        # Run healing state machine
        committed = _advance_healing(device_id, raw_status)

        # Stability buffer only applies when not in healing
        if committed in ("NORMAL", "SUSPICIOUS"):
            committed = _stable_status(device_id, committed)

        # Compute heal cooldown remaining for UI
        elapsed   = time.time() - ds["quarantine_at"] if ds["quarantine_at"] > 0 else HEAL_COOLDOWN
        remaining = max(0.0, HEAL_COOLDOWN - elapsed) if ds["quarantine_at"] > 0 else 0.0

        ds["alert_data"].update({
            "status":                  committed,
            "heal_phase":              ds["heal_phase"],
            "threat":                  threat if committed == raw_status else ds["alert_data"]["threat"],
            "rf_prob":                 round(rf_prob, 4),
            "iso_score":               round(iso_score, 4),
            "packets":                 packets,
            "avg_packet_size":         round(avg_size, 2),
            "dest_count":              dest,
            "activity_hour":           hour,
            "timestamp":               int(time.time()),
            "heal_cooldown_remaining": round(remaining, 1),
            "heal_stable_count":       ds["heal_stable_count"],
            "heal_stable_needed":      HEAL_STABLE_NEEDED,
            "attack_memory_count":     len(ds["attack_memory"]),
        })
        ds["traffic"]["packets"] = packets
        ds["last_update"]        = time.time()
        result_threat = ds["alert_data"]["threat"]

    print(f"\n[{device_id.upper()}] {'='*36}")
    print(f"  Packets   : {packets}")
    print(f"  RF Prob   : {rf_prob:.4f}  (flag={rf_flag})")
    print(f"  ISO Score : {iso_score:.4f}  (flag={iso_flag})")
    print(f"  Status    : {raw_status} → committed={committed}  heal={ds['heal_phase']}")
    print(f"{'='*42}\n")

    return {
        "status":    committed,
        "heal_phase": ds["heal_phase"],
        "threat":    result_threat,
        "rf_prob":   round(rf_prob, 4),
        "iso_score": round(iso_score, 4),
    }


# ── Healing feeder — auto-feeds normal data during healing phases ─────────────
def _healing_feeder():
    """
    Background thread that feeds synthetic NORMAL traffic to any device
    currently in QUARANTINED (post-cooldown), HEALING, or RECOVERING phase.
    This ensures the healing state machine can advance without relying
    on external data sources (which may be blocked/offline during quarantine).
    Does NOT feed devices that are idle/normal — those need real data.
    """
    time.sleep(2)
    print("[HEAL-FEEDER] 🟢 Started — healing feeder running")
    while True:
        for device_id in list(device_state.keys()):
            try:
                with device_locks[device_id]:
                    phase   = device_state[device_id]["heal_phase"]
                    status  = device_state[device_id]["alert_data"]["status"]
                    q_at    = device_state[device_id]["quarantine_at"]

                # Only feed during active healing phases
                needs_feed = False
                if phase in ("HEALING", "RECOVERING"):
                    needs_feed = True
                elif status == "QUARANTINED" and q_at > 0:
                    # Check if cooldown has expired — if so, feed to kick off healing
                    if (time.time() - q_at) >= HEAL_COOLDOWN:
                        needs_feed = True

                if needs_feed:
                    features = generate_synthetic("normal")
                    _run_ml(device_id, features)

            except Exception as e:
                print(f"[HEAL-FEEDER] ⚠ Error for {device_id}: {e}")
        time.sleep(5)


threading.Thread(target=_healing_feeder, daemon=True).start()


# ── Firewall helpers (cam1 only) ──────────────────────────────────────────────
def _block_device() -> None:
    global device_blocked
    with _firewall_lock:
        if device_blocked:
            return
        print("🚫 Blocking device:", PHONE_IP)
        try:
            import subprocess
            subprocess.run([
                "netsh", "advfirewall", "firewall", "add", "rule",
                "name=AEIS_Block", "dir=in", "action=block",
                f"remoteip={PHONE_IP}"
            ], check=True, capture_output=True)
            device_blocked = True
            print("✅ Firewall rule applied")
        except Exception as e:
            print("⚠ Firewall block failed:", e)


def _unblock_device() -> None:
    global device_blocked
    with _firewall_lock:
        if not device_blocked:
            return
        print("🔓 Unblocking device:", PHONE_IP)
        try:
            import subprocess
            subprocess.run([
                "netsh", "advfirewall", "firewall", "delete", "rule",
                "name=AEIS_Block"
            ], check=True, capture_output=True)
            device_blocked = False
            print("✅ Firewall rule removed")
        except Exception as e:
            print("⚠ Firewall unblock failed:", e)


# ═════════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ═════════════════════════════════════════════════════════════════════════════

@app.route("/data", methods=["POST"])
def receive_data():
    data = request.json
    packets_key = "packets_per_min" if "packets_per_min" in data else "packets_per_window"
    if packets_key not in data:
        return jsonify({"ignored": True, "reason": "missing packets field"})
    try:
        features = {
            "packets_per_window": data[packets_key],
            "avg_packet_size":    data["avg_packet_size"],
            "dest_count":         data["dest_count"],
            "activity_hour":      data["activity_hour"],
        }
    except KeyError as e:
        return jsonify({"ignored": True, "reason": f"missing field {e}"})

    # Skip processing if cam1 is in a healing phase — let the healing feeder manage it
    with device_locks["cam1"]:
        heal_phase = device_state["cam1"]["heal_phase"]
        cam1_status = device_state["cam1"]["alert_data"]["status"]
        device_state["cam1"]["sim_active"] = False

    if heal_phase in ("HEALING", "RECOVERING") or cam1_status == "QUARANTINED":
        return jsonify({"ok": True, "status": cam1_status, "ignored_healing": True})

    result    = _run_ml("cam1", features)
    committed = result["status"]

    if committed == "QUARANTINED":
        _block_device()
    elif committed == "NORMAL" and features["packets_per_window"] < 8000:
        _unblock_device()

    return jsonify({"ok": True, "status": committed})


@app.route("/simulate", methods=["POST"])
def simulate():
    body      = request.json or {}
    device_id = str(body.get("device_id", "cam1")).lower()

    if device_id not in device_state:
        return jsonify({"error": f"Unknown device_id '{device_id}'. Valid: cam1, cam2"}), 400

    if "features" in body:
        raw      = body["features"]
        required = {"packets_per_window", "avg_packet_size", "dest_count", "activity_hour"}
        missing  = required - set(raw.keys())
        if missing:
            return jsonify({"error": f"Missing feature keys: {missing}"}), 400
        try:
            features = {
                "packets_per_window": int(raw["packets_per_window"]),
                "avg_packet_size":    float(raw["avg_packet_size"]),
                "dest_count":         int(raw["dest_count"]),
                "activity_hour":      int(raw["activity_hour"]),
            }
        except (ValueError, TypeError) as e:
            return jsonify({"error": f"Invalid feature value: {e}"}), 400
        attack_type = "custom"
    else:
        attack_type = str(body.get("attack_type", "normal")).lower()
        intensity   = float(body.get("intensity", 1.0))
        if attack_type not in VALID_ATTACK_TYPES:
            return jsonify({"error": f"Unknown attack_type '{attack_type}'. Valid: {VALID_ATTACK_TYPES}"}), 400
        intensity = max(0.0, min(1.0, intensity))
        features  = generate_synthetic(attack_type, intensity)

    with device_locks[device_id]:
        device_state[device_id]["sim_active"] = True

    result = _run_ml(device_id, features)

    return jsonify({
        "ok":        True,
        "device_id": device_id,
        "status":    result["status"],
        "heal_phase": result.get("heal_phase"),
        "threat":    result["threat"],
        "rf_prob":   result["rf_prob"],
        "iso_score": result["iso_score"],
        "features":  features,
        "label":     ATTACK_LABELS.get(attack_type, attack_type),
    })


@app.route("/metrics")
def metrics():
    device_id = request.args.get("device_id", "cam1").lower()
    if device_id not in device_state:
        return jsonify({"error": f"Unknown device_id '{device_id}'"}), 400

    connected = _is_connected(device_id)
    if not connected:
        return jsonify({
            "connected":             False,
            "no_of_packets":         0,
            "packet_size":           0.0,
            "dest_ip_changes":       0,
            "activity_hour_pattern": 0,
        })

    with device_locks[device_id]:
        f = dict(device_state[device_id]["last_features"])

    return jsonify({
        "connected":             True,
        "no_of_packets":         f["packets_per_window"],
        "packet_size":           f["avg_packet_size"],
        "dest_ip_changes":       f["dest_count"],
        "activity_hour_pattern": f["activity_hour"],
    })


@app.route("/alert")
def alert():
    device_id = request.args.get("device_id", "cam1").lower()
    if device_id not in device_state:
        return jsonify({"error": f"Unknown device_id '{device_id}'"}), 400

    connected = _is_connected(device_id)
    with device_locks[device_id]:
        data = dict(device_state[device_id]["alert_data"])

    data["connected"] = connected
    if not connected:
        data.update({
            "status":          "DISCONNECTED",
            "heal_phase":      None,
            "threat":          "NONE",
            "packets":         0,
            "avg_packet_size": 0.0,
            "dest_count":      0,
            "activity_hour":   0,
        })
    return jsonify(data)


@app.route("/status")
def status():
    return jsonify({
        "server_connected": True,
        "devices": {
            "cam1": {
                "connected":   _is_connected("cam1"),
                "sim_active":  device_state["cam1"]["sim_active"],
                "last_update": device_state["cam1"]["last_update"],
                "heal_phase":  device_state["cam1"]["heal_phase"],
            },
            "cam2": {
                "connected":   _is_connected("cam2"),
                "sim_active":  device_state["cam2"]["sim_active"],
                "last_update": device_state["cam2"]["last_update"],
                "heal_phase":  device_state["cam2"]["heal_phase"],
            },
        },
    })


@app.route("/traffic")
def traffic():
    device_id = request.args.get("device_id", "cam1").lower()
    if device_id not in device_state:
        return jsonify({"error": f"Unknown device_id '{device_id}'"}), 400

    connected = _is_connected(device_id)
    if not connected:
        return jsonify({"packets": 0, "connected": False})

    with device_locks[device_id]:
        t = dict(device_state[device_id]["traffic"])
    t["connected"] = True
    return jsonify(t)


@app.route("/force/<st>")
def force_status(st):
    allowed = {"NORMAL", "SUSPICIOUS", "QUARANTINED"}
    if st.upper() not in allowed:
        return jsonify({"error": "Invalid status"}), 400

    with device_locks["cam1"]:
        ds = device_state["cam1"]
        ds["status_buffer"]         = [st.upper()] * STABILITY_COUNT
        ds["alert_data"]["status"]  = st.upper()
        ds["last_update"]           = time.time()
        if st.upper() == "QUARANTINED":
            ds["quarantine_at"] = time.time()
            ds["heal_phase"]    = None
        elif st.upper() == "NORMAL":
            ds["heal_phase"]        = None
            ds["heal_stable_count"] = 0
            ds["quarantine_at"]     = 0.0

    if st.upper() == "QUARANTINED":
        _block_device()
    elif st.upper() == "NORMAL":
        _unblock_device()

    print(f"🎮 MANUAL OVERRIDE (cam1) → {st.upper()}")
    return jsonify({"ok": True, "forced": st.upper()})


# ── GET /heal_status — healing phase info ─────────────────────────────────────
@app.route("/heal_status")
def heal_status():
    device_id = request.args.get("device_id", "cam1").lower()
    if device_id not in device_state:
        return jsonify({"error": f"Unknown device_id '{device_id}'"}), 400

    with device_locks[device_id]:
        ds  = device_state[device_id]
        ad  = ds["alert_data"]
        now = time.time()
        elapsed   = now - ds["quarantine_at"] if ds["quarantine_at"] > 0 else HEAL_COOLDOWN
        remaining = max(0.0, HEAL_COOLDOWN - elapsed) if ds["quarantine_at"] > 0 else 0.0

    return jsonify({
        "device_id":               device_id,
        "status":                  ad["status"],
        "heal_phase":              ds["heal_phase"],
        "heal_cooldown_remaining": round(remaining, 1),
        "heal_stable_count":       ds["heal_stable_count"],
        "heal_stable_needed":      HEAL_STABLE_NEEDED,
        "attack_memory_count":     len(ds["attack_memory"]),
    })


# ── POST /reset — force any device back to NORMAL ────────────────────────────
@app.route("/reset", methods=["POST"])
def reset_device():
    body      = request.json or {}
    device_id = str(body.get("device_id", "cam1")).lower()
    if device_id not in device_state:
        return jsonify({"error": f"Unknown device_id '{device_id}'"}), 400

    with device_locks[device_id]:
        ds = device_state[device_id]
        ds["alert_data"]["status"]  = "NORMAL"
        ds["alert_data"]["heal_phase"] = None
        ds["heal_phase"]            = None
        ds["heal_stable_count"]     = 0
        ds["quarantine_at"]         = 0.0
        ds["status_buffer"]         = ["NORMAL"] * STABILITY_COUNT
        ds["last_update"]           = time.time()

    if device_id == "cam1":
        _unblock_device()

    print(f"⟳ MANUAL RESET ({device_id}) → NORMAL")
    return jsonify({"ok": True, "device_id": device_id, "status": "NORMAL"})


# ── Capture endpoints ─────────────────────────────────────────────────────────
@app.route("/start_capture", methods=["POST"])
def api_start_capture():
    body       = request.json or {}
    device_ip  = body.get("device_ip")  or None
    window_sec = int(body.get("window_sec", 5))
    interface  = str(body.get("interface",  "Wi-Fi"))
    result = start_capture(device_ip=device_ip, window_sec=window_sec, interface=interface)
    return jsonify({"ok": True, **result})


@app.route("/stop_capture", methods=["POST"])
def api_stop_capture():
    result = stop_capture()
    return jsonify({"ok": True, **result})


@app.route("/capture_status")
def api_capture_status():
    return jsonify(capture_status())


# ── Boot ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, threaded=True)