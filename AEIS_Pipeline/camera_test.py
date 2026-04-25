"""
AEIS — Fixed camera_test.py
Fixes:
  1. Status check failure no longer freezes camera permanently
  2. Uses last-known-good status on error
  3. Cleaner freeze effect with status overlay on frame
"""

import cv2
import requests
import threading
import time

CAMERA_URL = "http://100.120.11.125:4747/video"
SERVER_URL = "http://192.168.56.1:4747/alert"

_lock       = threading.Lock()
_status     = "NORMAL"       # last confirmed status
_last_ok    = time.time()    # last successful server check

def check_status():
    global _status, _last_ok
    while True:
        try:
            res    = requests.get(SERVER_URL, timeout=2)
            data   = res.json()
            status = data.get("status", "NORMAL")

            with _lock:
                _status  = status
                _last_ok = time.time()

        except Exception as e:
            # Keep last known status — don't flip to NORMAL on error
            elapsed = time.time() - _last_ok
            if elapsed > 10:
                # Server unreachable for 10s → assume NORMAL (safe default)
                with _lock:
                    _status = "NORMAL"

        time.sleep(2)


# ── Start background thread ───────────────────────────────────
threading.Thread(target=check_status, daemon=True).start()

# ── Camera setup ──────────────────────────────────────────────
cap = cv2.VideoCapture(CAMERA_URL)

if not cap.isOpened():
    print("❌ Camera connection failed. Check DroidCam is running.")
    exit()

print("📷 AEIS Camera Feed running...")

last_frame   = None
STATUS_COLORS = {
    "NORMAL"     : (50, 200, 50),
    "SUSPICIOUS" : (0, 165, 255),
    "QUARANTINED": (0, 0, 220),
}

while True:
    with _lock:
        current_status = _status

    paused = (current_status == "QUARANTINED")

    if not paused:
        ret, frame = cap.read()
        if ret:
            last_frame = frame
        # If frame read fails, just use last_frame (don't crash)

    if last_frame is not None:
        display = last_frame.copy()

        # ── Status overlay ────────────────────────────────────
        color = STATUS_COLORS.get(current_status, (255, 255, 255))
        label = f"AEIS STATUS: {current_status}"

        # Dark banner at bottom
        h, w = display.shape[:2]
        cv2.rectangle(display, (0, h - 45), (w, h), (20, 20, 20), -1)
        cv2.putText(display, label, (15, h - 15),
                    cv2.FONT_HERSHEY_DUPLEX, 0.7, color, 2)

        if paused:
            # Big red QUARANTINED overlay
            overlay = display.copy()
            cv2.rectangle(overlay, (0, 0), (w, h), (0, 0, 180), -1)
            cv2.addWeighted(overlay, 0.35, display, 0.65, 0, display)
            cv2.putText(display, "QUARANTINED", (w // 2 - 150, h // 2),
                        cv2.FONT_HERSHEY_DUPLEX, 1.5, (0, 0, 255), 3)
            cv2.putText(display, "Device Isolated", (w // 2 - 100, h // 2 + 45),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

        cv2.imshow("AEIS Camera Feed", display)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()