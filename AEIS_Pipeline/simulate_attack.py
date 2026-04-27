import cv2
import requests
import threading
import time
import numpy as np


# =========================
# CONFIG
# =========================
SERVER_URL = "http://192.168.29.89:4747/alert"

CAMERA_URLS = [
    "http://192.168.29.36:4747/video",
    "http://192.168.29.36:4747/video?640x480",
    "http://192.168.29.36:4747/video?1280x720",
    "http://192.168.29.36:8080/video",
    "http://192.168.29.36:8080/videofeed",
    "http://192.168.29.36:8080/video?type=.mjpeg",
]


_lock    = threading.Lock()
_status  = "NORMAL"
_last_ok = time.time()


# =========================
# STATUS CHECK THREAD
# =========================
def check_status():
    global _status, _last_ok
    while True:
        try:
            res = requests.get(SERVER_URL, timeout=2)
            data = res.json()
            status = data.get("status", "NORMAL")

            with _lock:
                _status = status
                _last_ok = time.time()

        except Exception:
            elapsed = time.time() - _last_ok
            if elapsed > 10:
                with _lock:
                    _status = "NORMAL"

        time.sleep(2)


# =========================
# CAMERA CONNECT
# =========================
def open_camera():
    for url in CAMERA_URLS:
        print(f"Trying camera stream: {url}")
        cap = cv2.VideoCapture(url)
        time.sleep(1)

        if cap.isOpened():
            ret, frame = cap.read()
            if ret and frame is not None:
                print(f"✅ Connected to camera using: {url}")
                return cap

        cap.release()

    return None


# =========================
# UI HELPERS
# =========================
def blue_tint(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    tinted = np.zeros_like(frame)
    tinted[:, :, 0] = np.clip(gray * 1.05, 0, 255).astype(np.uint8)  # Blue
    tinted[:, :, 1] = np.clip(gray * 0.82, 0, 255).astype(np.uint8)  # Green
    tinted[:, :, 2] = np.clip(gray * 0.55, 0, 255).astype(np.uint8)  # Red
    return tinted


def add_scan_lines(img, step=4, alpha=0.12):
    out = img.copy()
    h, w = out.shape[:2]
    line = np.zeros_like(out)
    for y in range(0, h, step):
        cv2.line(line, (0, y), (w, y), (0, 0, 0), 1)
    cv2.addWeighted(line, alpha, out, 1 - alpha, 0, out)
    return out


def draw_corner_marks(img, color=(180, 220, 255)):
    h, w = img.shape[:2]
    s = 18
    t = 2

    # top-left
    cv2.line(img, (8, 8), (8 + s, 8), color, t)
    cv2.line(img, (8, 8), (8, 8 + s), color, t)

    # top-right
    cv2.line(img, (w - 8 - s, 8), (w - 8, 8), color, t)
    cv2.line(img, (w - 8, 8), (w - 8, 8 + s), color, t)

    # bottom-left
    cv2.line(img, (8, h - 8), (8 + s, h - 8), color, t)
    cv2.line(img, (8, h - 8 - s), (8, h - 8), color, t)

    # bottom-right
    cv2.line(img, (w - 8 - s, h - 8), (w - 8, h - 8), color, t)
    cv2.line(img, (w - 8, h - 8 - s), (w - 8, h - 8), color, t)


def draw_top_bar(img, title_left, title_right):
    h, w = img.shape[:2]
    overlay = img.copy()
    cv2.rectangle(overlay, (0, 0), (w, 38), (8, 18, 28), -1)
    cv2.addWeighted(overlay, 0.88, img, 0.12, 0, img)

    cv2.putText(img, title_left, (12, 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, (220, 245, 255), 2)
    cv2.putText(img, title_right, (w - 130, 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (140, 200, 255), 2)


def make_empty_screen(height, width):
    panel = np.zeros((height, width, 3), dtype=np.uint8)
    panel[:] = (8, 15, 22)

    for x in range(0, width, 36):
        cv2.line(panel, (x, 0), (x, height), (12, 28, 40), 1)
    for y in range(0, height, 36):
        cv2.line(panel, (0, y), (width, y), (12, 28, 40), 1)

    draw_top_bar(panel, "CAM 2", "OFFLINE")

    cv2.rectangle(panel, (8, 8), (width - 8, height - 8), (50, 110, 160), 1)

    # centered offline box
    bx1, by1 = width // 2 - 120, height // 2 - 35
    bx2, by2 = width // 2 + 120, height // 2 + 35
    cv2.rectangle(panel, (bx1, by1), (bx2, by2), (12, 18, 24), -1)
    cv2.rectangle(panel, (bx1, by1), (bx2, by2), (60, 180, 255), 2)

    cv2.putText(panel, "NO SIGNAL", (width // 2 - 88, height // 2 + 8),
                cv2.FONT_HERSHEY_DUPLEX, 0.95, (210, 240, 255), 2)

    cv2.putText(panel, "IP CAMERA 02", (18, 64),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (160, 210, 240), 1)
    cv2.putText(panel, "STATUS  : DISCONNECTED", (18, 88),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 170, 220), 1)

    draw_corner_marks(panel, (90, 170, 220))
    panel = add_scan_lines(panel, step=4, alpha=0.14)
    return panel


def build_live_screen(frame, current_status, paused):
    STATUS_COLORS = {
        "NORMAL": (80, 240, 120),
        "SUSPICIOUS": (0, 200, 255),
        "QUARANTINED": (0, 0, 255),
    }

    color = STATUS_COLORS.get(current_status, (220, 220, 220))

    frame = blue_tint(frame)
    display = frame.copy()
    h, w = display.shape[:2]

    draw_top_bar(display, "CAM 1", "LIVE")

    cv2.rectangle(display, (8, 8), (w - 8, h - 8), (50, 110, 160), 1)

    cv2.putText(display, "IP CAMERA 01", (18, 64),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (160, 210, 240), 1)
    cv2.putText(display, "REC", (18, 88),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
    cv2.circle(display, (66, 82), 5, (0, 0, 255), -1)

    ts = time.strftime("%d/%m/%Y  %H:%M:%S")
    cv2.putText(display, ts, (w - 205, 62),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (210, 235, 255), 1)

    cv2.putText(display, f"STATUS : {current_status}", (18, h - 18),
                cv2.FONT_HERSHEY_DUPLEX, 0.6, color, 2)

    draw_corner_marks(display, (90, 170, 220))

    if current_status == "SUSPICIOUS":
        alert = display.copy()
        cv2.rectangle(alert, (0, 0), (w, h), (0, 140, 255), -1)
        cv2.addWeighted(alert, 0.10, display, 0.90, 0, display)

        cv2.rectangle(display, (w - 210, h - 42), (w - 18, h - 12), (0, 170, 255), -1)
        cv2.putText(display, "ACTIVITY DETECTED", (w - 198, h - 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.50, (255, 255, 255), 2)

    if paused:
        overlay = display.copy()
        cv2.rectangle(overlay, (0, 0), (w, h), (0, 0, 180), -1)
        cv2.addWeighted(overlay, 0.33, display, 0.67, 0, display)

        cv2.rectangle(display, (w // 2 - 140, h // 2 - 38),
                      (w // 2 + 140, h // 2 + 38), (15, 20, 28), -1)
        cv2.rectangle(display, (w // 2 - 140, h // 2 - 38),
                      (w // 2 + 140, h // 2 + 38), (0, 0, 255), 2)
        cv2.putText(display, "QUARANTINED", (w // 2 - 105, h // 2 + 8),
                    cv2.FONT_HERSHEY_DUPLEX, 0.95, (0, 0, 255), 2)

    display = add_scan_lines(display, step=4, alpha=0.12)
    return display


def draw_bottom_dashboard(canvas, current_status, width, y_start):
    panel_h = 150
    cv2.rectangle(canvas, (0, y_start), (width, y_start + panel_h), (6, 12, 18), -1)
    cv2.line(canvas, (0, y_start), (width, y_start), (0, 110, 170), 2)

    # left config box
    cv2.rectangle(canvas, (18, y_start + 14), (300, y_start + 130), (10, 20, 28), -1)
    cv2.rectangle(canvas, (18, y_start + 14), (300, y_start + 130), (0, 110, 170), 1)
    cv2.putText(canvas, "SYSTEM INFO", (30, y_start + 36),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (210, 240, 255), 2)

    info = [
        "Input latency   : 100 ms",
        "Network         : Online",
        "Security mode   : Armed",
        "Device status   : Active",
    ]
    yy = y_start + 62
    for line in info:
        cv2.putText(canvas, line, (30, yy),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.48, (120, 190, 235), 1)
        yy += 22

    # center stats box
    cv2.rectangle(canvas, (325, y_start + 14), (760, y_start + 130), (10, 20, 28), -1)
    cv2.rectangle(canvas, (325, y_start + 14), (760, y_start + 130), (0, 110, 170), 1)
    cv2.putText(canvas, "AEIS MONITOR STATUS", (340, y_start + 36),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (210, 240, 255), 2)

    state_color = (80, 240, 120) if current_status == "NORMAL" else (0, 200, 255) if current_status == "SUSPICIOUS" else (0, 0, 255)
    cv2.putText(canvas, f"Current state : {current_status}", (340, y_start + 68),
                cv2.FONT_HERSHEY_DUPLEX, 0.62, state_color, 2)
    cv2.putText(canvas, "Camera 01     : Connected", (340, y_start + 92),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (120, 190, 235), 1)
    cv2.putText(canvas, "Camera 02     : Offline / Empty", (340, y_start + 114),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (120, 190, 235), 1)

    # right mini graph box
    cv2.rectangle(canvas, (785, y_start + 14), (1260, y_start + 130), (10, 20, 28), -1)
    cv2.rectangle(canvas, (785, y_start + 14), (1260, y_start + 130), (0, 110, 170), 1)
    cv2.putText(canvas, "MONITOR ACTIVITY", (800, y_start + 36),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (210, 240, 255), 2)

    points = np.array([
        [810, y_start + 105],
        [860, y_start + 98],
        [910, y_start + 86],
        [960, y_start + 92],
        [1010, y_start + 72],
        [1060, y_start + 64],
        [1110, y_start + 78],
        [1160, y_start + 60],
        [1210, y_start + 88],
        [1240, y_start + 82]
    ], np.int32)

    cv2.polylines(canvas, [points], False, (0, 190, 255), 2)
    for p in points:
        cv2.circle(canvas, tuple(p), 2, (0, 220, 255), -1)

    cv2.putText(canvas, "Refresh Rate : 100", (800, y_start + 115),
                cv2.FONT_HERSHEY_SIMPLEX, 0.46, (120, 190, 235), 1)


# =========================
# START THREAD
# =========================
threading.Thread(target=check_status, daemon=True).start()


# =========================
# CAMERA SETUP
# =========================
cap = open_camera()

if cap is None:
    print("❌ Camera connection failed.")
    print("Open these in browser and test:")
    for url in CAMERA_URLS:
        print("   ", url)
    exit()

print("📷 AEIS Camera Feed running...")


WINDOW_NAME = "AEIS CCTV Monitor"
cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
cv2.resizeWindow(WINDOW_NAME, 1400, 860)
cv2.moveWindow(WINDOW_NAME, 70, 30)

try:
    cv2.setWindowProperty(WINDOW_NAME, cv2.WND_PROP_TOPMOST, 1)
except:
    pass


last_frame = None


# =========================
# MAIN LOOP
# =========================
while True:
    with _lock:
        current_status = _status

    paused = (current_status == "QUARANTINED")

    if not paused:
        ret, frame = cap.read()
        if ret:
            last_frame = frame

    if last_frame is not None:
        # top two camera panels
        cam_w, cam_h = 620, 360

        live_panel = cv2.resize(last_frame, (cam_w, cam_h))
        live_panel = build_live_screen(live_panel, current_status, paused)

        empty_panel = make_empty_screen(cam_h, cam_w)

        top_row = cv2.hconcat([live_panel, empty_panel])

        # full dashboard canvas
        canvas_h = 760
        canvas_w = 1280
        canvas = np.zeros((canvas_h, canvas_w, 3), dtype=np.uint8)
        canvas[:] = (4, 10, 16)

        # top application bar
        cv2.rectangle(canvas, (0, 0), (canvas_w, 42), (5, 14, 20), -1)
        cv2.line(canvas, (0, 41), (canvas_w, 41), (0, 120, 180), 1)

        cv2.putText(canvas, "AEIS   CCTV SURVEILLANCE DASHBOARD", (18, 27),
                    cv2.FONT_HERSHEY_DUPLEX, 0.72, (220, 245, 255), 2)
        cv2.putText(canvas, "2 CHANNEL VIEW", (1085, 27),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (120, 190, 235), 2)

        # place the two cams
        x = 18
        y = 58
        canvas[y:y + cam_h, x:x + (cam_w * 2)] = top_row

        # vertical divider glow
        cv2.rectangle(canvas, (x + cam_w - 1, y), (x + cam_w + 1, y + cam_h), (0, 140, 220), -1)

        # outer block border
        cv2.rectangle(canvas, (16, 56), (16 + cam_w * 2 + 4, 56 + cam_h + 4), (0, 120, 180), 1)

        # bottom dashboard
        draw_bottom_dashboard(canvas, current_status, canvas_w, 440)

        cv2.imshow(WINDOW_NAME, canvas)

    key = cv2.waitKey(1) & 0xFF

    if key == ord('f'):
        cv2.setWindowProperty(WINDOW_NAME, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

    elif key == ord('n'):
        cv2.setWindowProperty(WINDOW_NAME, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(WINDOW_NAME, 1400, 860)
        cv2.moveWindow(WINDOW_NAME, 70, 30)

    elif key == ord('q'):
        break


cap.release()
cv2.destroyAllWindows()