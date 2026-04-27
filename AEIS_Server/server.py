from flask import Flask, request, jsonify
from flask_cors import CORS
import sys, os, time, threading

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from AEIS_Pipeline.pipeline import run_pipeline
from AEIS_Pipeline.simulation import generate
from AEIS_Pipeline.heal import reset_heal_state
from AEIS_Pipeline.response import system_state

app = Flask(__name__)
CORS(app)

_lock = threading.Lock()

# 🔥 NEW: force override flag
force_normal_mode = False

latest_status = {
    "status": "NORMAL",
    "threat": "NORMAL",
    "reason": "System starting...",
    "confidence": 0.0,
    "timestamp": int(time.time()),
    "packets": 0,
    "avg_size": 0,
    "dest_count": 0,
    "camera_active": True,
    "monitoring_mode": False,
    "blocked_ips": [],
    "heal_stage": "NORMAL",
    "clean_windows": 0,
}

def _map(threat):
    return {
        "NORMAL": "NORMAL",
        "LOW": "SUSPICIOUS",
        "MEDIUM": "SUSPICIOUS",
        "HIGH": "QUARANTINED",
    }.get(threat, "NORMAL")


# ================= DATA PIPELINE =================
@app.route("/data", methods=["POST"])
def receive_data():
    global force_normal_mode

    # 🔴 If heal is active → ignore all attack data
    if force_normal_mode:
        return jsonify({"status": "NORMAL"})

    snapshot = request.json
    result = run_pipeline(snapshot, "192.168.29.36")

    det = result["detection"]
    resp = result["response"]
    hlr = result["heal"]

    with _lock:
        latest_status.update({
            "status": _map(det["threat_level"]),
            "threat": det["threat_level"],
            "reason": det["reason"],
            "confidence": det["confidence"],
            "timestamp": int(time.time()),
            "packets": snapshot.get("packets_per_window", 0),
            "avg_size": snapshot.get("avg_packet_size", 0),
            "dest_count": snapshot.get("dest_count", 0),
            "camera_active": resp["camera_active"],
            "monitoring_mode": resp["monitoring_mode"],
            "blocked_ips": resp["blocked_ips"],
            "heal_stage": hlr["status"],
            "clean_windows": hlr["clean_windows"],
        })

    return jsonify({"status": det["threat_level"]})


# ================= ALERT =================
@app.route("/alert")
def alert():
    return jsonify(latest_status)


# ================= TRAFFIC =================
@app.route("/traffic")
def traffic():
    return jsonify({"packets": latest_status["packets"]})


# ================= SIMULATION =================
@app.route("/simulate/<attack>")
def simulate(attack):
    snapshot = generate(attack, 1.0)
    result = run_pipeline(snapshot, "192.168.29.36")

    det = result["detection"]
    resp = result["response"]
    hlr = result["heal"]

    with _lock:
        latest_status.update({
            "status": _map(det["threat_level"]),
            "threat": det["threat_level"],
            "reason": det["reason"],
            "confidence": det["confidence"],
            "timestamp": int(time.time()),
            "packets": snapshot["packets_per_window"],
            "avg_size": snapshot["avg_packet_size"],
            "dest_count": snapshot["dest_count"],
            "camera_active": resp["camera_active"],
            "monitoring_mode": resp["monitoring_mode"],
            "blocked_ips": resp["blocked_ips"],
            "heal_stage": hlr["status"],
            "clean_windows": hlr["clean_windows"],
        })

    return jsonify({"ok": True})


# ================= HEAL =================
@app.route("/heal", methods=["GET"])
def heal_manual():
    global force_normal_mode

    reset_heal_state()

    # 🔥 Force clean system state
    system_state["camera_active"] = True
    system_state["blocked_ips"] = []
    system_state["monitoring_mode"] = False
    system_state["threat_level"] = "NORMAL"

    # 🔥 Activate override (ignore attacks)
    force_normal_mode = True

    with _lock:
        latest_status.update({
            "status": "NORMAL",
            "threat": "NORMAL",
            "reason": "Manual heal triggered",
            "confidence": 1.0,
            "camera_active": True,
            "monitoring_mode": False,
            "blocked_ips": [],
            "heal_stage": "NORMAL",
            "clean_windows": 0,
            "timestamp": int(time.time())
        })

    print("🔓 HEAL TRIGGERED — SYSTEM FORCED TO NORMAL")

    return jsonify({"status": "NORMAL"})


# ================= RESUME (OPTIONAL) =================
@app.route("/resume", methods=["GET"])
def resume_detection():
    global force_normal_mode
    force_normal_mode = False
    print("▶ Detection resumed")
    return jsonify({"status": "RESUMED"})


# ================= MAIN =================
if __name__ == "__main__":
    print("🚀 AEIS Server running on http://localhost:5000")
    app.run(host="0.0.0.0", port=5000)