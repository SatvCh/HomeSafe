"""
AEIS — Fixed server.py
Fixes:
  1. Thread lock on shared state (no race condition)
  2. Correct BASE_FEATURES column order
  3. Accepts both 'packets_per_min' and 'packets_per_window' from pipeline
  4. Smoothing: status only changes after N consecutive same readings
  5. Unblock resets status cleanly
  6. RF gets 7-feature input (TIME_FEATURES dropped), matching training
     ISO gets all 11 features, matching its training
"""

from flask import Flask, request, jsonify
from flask_cors import CORS

import joblib
import numpy as np
import pandas as pd
import subprocess
import threading
import logging

from aeis_utils import BASE_FEATURES, engineer_features

# These 4 columns were DROPPED during RF training (aeis_train_random_forest.py step 2).
# RF model expects exactly 7 features (11 engineered minus 4 time features).
# Isolation Forest was trained on ALL 11 features — do NOT drop for ISO.
RF_DROP_COLS = ["activity_hour", "hour_sin", "hour_cos", "high_hour_flag"]

log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

app = Flask(__name__)
CORS(app)

# ── Config ────────────────────────────────────────────────────
PHONE_IP = "192.168.29.83"

# How many consecutive readings before escalating status.
# Prevents single-packet spike from flipping to QUARANTINED.
STABILITY_COUNT = 2   # set to 1 to disable smoothing

# ── Load models ───────────────────────────────────────────────
iso = joblib.load("outputs_if/model_isolation_forest.pkl")
threshold_if = float(np.load("outputs_if/iso_threshold.npy"))

rf = joblib.load("outputs_rf/model_random_forest.pkl")
threshold_rf = float(np.load("outputs_rf/rf_threshold.npy"))

# ── Shared state (protected by lock) ─────────────────────────
_lock = threading.Lock()

traffic_data = {"packets": 0}
alert_data = {
    "device": "Android Camera",
    "status": "NORMAL",
    "threat": "LOW",
    "rf_prob": 0.0,
    "iso_score": 0.0,
    "packets": 0,
    "timestamp": 0,
}

device_blocked = False

# Stability buffer: track last N statuses before committing a change
_status_buffer = []


# ── Device blocking ───────────────────────────────────────────
def block_device():
    global device_blocked
    if device_blocked:
        return
    print("🚫 Blocking device:", PHONE_IP)
    try:
        subprocess.run([
            "netsh", "advfirewall", "firewall", "add", "rule",
            "name=AEIS_Block", "dir=in", "action=block",
            f"remoteip={PHONE_IP}"
        ], check=True, capture_output=True)
        device_blocked = True
        print("✅ Firewall rule applied")
    except Exception as e:
        print("⚠ Firewall block failed:", e)


def unblock_device():
    global device_blocked
    if not device_blocked:
        return
    print("🔓 Unblocking device:", PHONE_IP)
    try:
        subprocess.run([
            "netsh", "advfirewall", "firewall", "delete", "rule",
            "name=AEIS_Block"
        ], check=True, capture_output=True)
        device_blocked = False
        print("✅ Firewall rule removed")
    except Exception as e:
        print("⚠ Firewall unblock failed:", e)


# ── Stable status: only change after STABILITY_COUNT confirmations ──
def stable_status(new_status: str) -> str:
    """
    Prevents transient spikes from flipping the dashboard.
    Returns the committed status only after STABILITY_COUNT
    consecutive identical readings.
    """
    global _status_buffer
    _status_buffer.append(new_status)
    if len(_status_buffer) > STABILITY_COUNT:
        _status_buffer = _status_buffer[-STABILITY_COUNT:]

    # Commit only if all recent readings agree
    if len(_status_buffer) == STABILITY_COUNT and len(set(_status_buffer)) == 1:
        return _status_buffer[0]

    # Otherwise keep existing committed status
    return alert_data["status"]


# ── Main data endpoint ────────────────────────────────────────
@app.route("/data", methods=["POST"])
def receive_data():
    global traffic_data, alert_data

    data = request.json

    # Accept both field names from pipeline
    packets_key = "packets_per_min" if "packets_per_min" in data else "packets_per_window"
    if packets_key not in data:
        return jsonify({"ignored": True, "reason": "missing packets field"})

    packets = data[packets_key]

    # ── Build feature DataFrame in EXACT BASE_FEATURES order ──
    # BASE_FEATURES = ["packets_per_window", "avg_packet_size", "dest_count", "activity_hour"]
    try:
        raw = pd.DataFrame([[
            packets,
            data["avg_packet_size"],
            data["dest_count"],
            data["activity_hour"],
        ]], columns=BASE_FEATURES)
    except KeyError as e:
        return jsonify({"ignored": True, "reason": f"missing field {e}"})

    # ── Feature engineering ───────────────────────────────────
    feat_all = engineer_features(raw)          # 11 cols — for Isolation Forest

    # RF was trained WITHOUT time features (see RF_DROP_COLS).
    # Drop them here so RF receives the same 7 cols it was trained on.
    feat_rf = feat_all.drop(columns=RF_DROP_COLS)   # 7 cols — for Random Forest

    # ── Model inference ────────────────────────────────────────
    iso_score = float(-iso.score_samples(feat_all.values)[0])
    rf_prob   = float(rf.predict_proba(feat_rf.values)[0, 1])

    iso_flag = iso_score >= threshold_if
    rf_flag  = rf_prob  >= threshold_rf

    # ── Raw decision ───────────────────────────────────────────
    if iso_flag and rf_flag:
        raw_status = "SUSPICIOUS"
        threat     = "MEDIUM"
    else:
        raw_status = "NORMAL"
        threat     = "LOW"

    # ── Traffic-based escalation ───────────────────────────────
    if iso_flag and rf_flag and packets > 5000:
        raw_status = "QUARANTINED"
        threat     = "HIGH"

    # ── Stability filter (prevents jitter) ────────────────────
    committed_status = stable_status(raw_status)

    # ── Side effects based on committed status ─────────────────
    if committed_status == "QUARANTINED":
        block_device()
    elif committed_status == "NORMAL" and packets < 1500:
        unblock_device()

    # ── Console output ─────────────────────────────────────────
    print(f"\n{'='*40}")
    print(f"  Packets    : {packets}")
    print(f"  RF Prob    : {rf_prob:.4f}  (flag={rf_flag})")
    print(f"  ISO Score  : {iso_score:.4f}  (flag={iso_flag})")
    print(f"  Raw Status : {raw_status}")
    print(f"  Committed  : {committed_status}")
    print(f"{'='*40}\n")

    # ── Update shared state (thread-safe) ─────────────────────
    import time
    with _lock:
        traffic_data = {"packets": packets}
        alert_data = {
            "device"    : "Android Camera",
            "status"    : committed_status,
            "threat"    : threat if committed_status == raw_status else alert_data["threat"],
            "rf_prob"   : round(rf_prob, 4),
            "iso_score" : round(iso_score, 4),
            "packets"   : packets,
            "timestamp" : int(time.time()),
        }

    return jsonify({"ok": True, "status": committed_status})


# ── Read endpoints ────────────────────────────────────────────
@app.route("/traffic")
def traffic():
    with _lock:
        return jsonify(dict(traffic_data))


@app.route("/alert")
def alert():
    with _lock:
        return jsonify(dict(alert_data))


# ── Manual override endpoints (useful during demo) ────────────
@app.route("/force/<status>")
def force_status(status):
    """
    GET /force/NORMAL   → manually reset to NORMAL
    GET /force/QUARANTINED → manually trigger quarantine
    Useful if demo gets stuck.
    """
    global _status_buffer
    allowed = {"NORMAL", "SUSPICIOUS", "QUARANTINED"}
    if status.upper() not in allowed:
        return jsonify({"error": "Invalid status"}), 400

    with _lock:
        _status_buffer = [status.upper()] * STABILITY_COUNT
        alert_data["status"] = status.upper()

    if status.upper() == "QUARANTINED":
        block_device()
    elif status.upper() == "NORMAL":
        unblock_device()

    print(f"🎮 MANUAL OVERRIDE → {status.upper()}")
    return jsonify({"ok": True, "forced": status.upper()})


if __name__ == "__main__":
    # threaded=True ensures pipeline POST and dashboard GET don't block each other
    app.run(host="0.0.0.0", port=5000, threaded=True)