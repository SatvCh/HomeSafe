import cv2
import requests
import threading
import time
import numpy as np


print("========== CCTV DASHBOARD ==========")


SERVER_URL = "http://192.168.56.1:4747/alert"


CAMERA1_URLS = [
    "http://192.168.1.65:4747/video",
    "http://192.168.1.65:4747/video?640x480",
    "http://192.168.1.65:4747/video?1280x720",
    "http://192.168.1.65:8080/video",
    "http://192.168.1.65:8080/videofeed",
    "http://192.168.1.65:8080/video?type=.mjpeg",
]

CAMERA2_URLS = [
    "http://192.168.1.69:4747/video",
    "http://192.168.1.69:4747/video?640x480",
    "http://192.168.1.69:4747/video?1280x720",
    "http://192.168.1.69:8080/video",
    "http://192.168.1.69:8080/videofeed",
    "http://192.168.1.69:8080/video?type=.mjpeg",
]


_lock = threading.Lock()
_status = "NORMAL"
_last_ok = time.time()



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



def open_camera(camera_urls, cam_name):
    for url in camera_urls:
        cap = cv2.VideoCapture(url)
        time.sleep(1)

        if cap.isOpened():
            ret, frame = cap.read()
            if ret and frame is not None:
                print(f"✅ Connected to {cam_name} using: {url}")
                return cap, url

        cap.release()

    return None, None



def try_reconnect(camera_urls, cam_name):
    cap, used_url = open_camera(camera_urls, cam_name)
    if cap is not None:
        print(f"🔄 Reconnected {cam_name}")
    return cap, used_url



def blue_tint(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    tinted = np.zeros_like(frame)
    tinted[:, :, 0] = np.clip(gray * 1.05, 0, 255).astype(np.uint8)
    tinted[:, :, 1] = np.clip(gray * 0.82, 0, 255).astype(np.uint8)
    tinted[:, :, 2] = np.clip(gray * 0.55, 0, 255).astype(np.uint8)
    return tinted



def add_scan_lines(img, step=4, alpha=0.12):
    out = img.copy()
    h, w = out.shape[:2]
    layer = np.zeros_like(out)
    for y in range(0, h, step):
        cv2.line(layer, (0, y), (w, y), (0, 0, 0), 1)
    cv2.addWeighted(layer, alpha, out, 1 - alpha, 0, out)
    return out



def draw_corner_marks(img, color=(180, 220, 255)):
    h, w = img.shape[:2]
    s = 18
    t = 2

    cv2.line(img, (8, 8), (8 + s, 8), color, t)
    cv2.line(img, (8, 8), (8, 8 + s), color, t)

    cv2.line(img, (w - 8 - s, 8), (w - 8, 8), color, t)
    cv2.line(img, (w - 8, 8), (w - 8, 8 + s), color, t)

    cv2.line(img, (8, h - 8), (8 + s, h - 8), color, t)
    cv2.line(img, (8, h - 8 - s), (8, h - 8), color, t)

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



def make_empty_screen(height, width, cam_label, channel_no):
    panel = np.zeros((height, width, 3), dtype=np.uint8)
    panel[:] = (8, 15, 22)

    for x in range(0, width, 36):
        cv2.line(panel, (x, 0), (x, height), (12, 28, 40), 1)
    for y in range(0, height, 36):
        cv2.line(panel, (0, y), (width, y), (12, 28, 40), 1)

    draw_top_bar(panel, cam_label, "OFFLINE")
    cv2.rectangle(panel, (8, 8), (width - 8, height - 8), (50, 110, 160), 1)

    bx1, by1 = width // 2 - 120, height // 2 - 35
    bx2, by2 = width // 2 + 120, height // 2 + 35
    cv2.rectangle(panel, (bx1, by1), (bx2, by2), (12, 18, 24), -1)
    cv2.rectangle(panel, (bx1, by1), (bx2, by2), (60, 180, 255), 2)

    cv2.putText(panel, "NO SIGNAL", (width // 2 - 88, height // 2 + 8),
                cv2.FONT_HERSHEY_DUPLEX, 0.95, (210, 240, 255), 2)

    cv2.putText(panel, f"CHANNEL      : {channel_no:02d}", (18, 64),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (160, 210, 240), 1)
    cv2.putText(panel, "INPUT STATUS : DISCONNECTED", (18, 88),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 170, 220), 1)

    draw_corner_marks(panel, (90, 170, 220))
    panel = add_scan_lines(panel, step=4, alpha=0.14)
    return panel



def build_live_screen(frame, current_status, paused, cam_label, channel_no):
    STATUS_COLORS = {
        "NORMAL": (80, 240, 120),
        "SUSPICIOUS": (0, 200, 255),
        "QUARANTINED": (0, 0, 255),
    }

    color = STATUS_COLORS.get(current_status, (220, 220, 220))

    frame = blue_tint(frame)
    display = frame.copy()
    h, w = display.shape[:2]

    draw_top_bar(display, cam_label, "LIVE")
    cv2.rectangle(display, (8, 8), (w - 8, h - 8), (50, 110, 160), 1)

    cv2.putText(display, f"CHANNEL      : {channel_no:02d}", (18, 64),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (160, 210, 240), 1)
    cv2.putText(display, "RECORDING", (18, 88),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
    cv2.circle(display, (108, 82), 5, (0, 0, 255), -1)

    ts = time.strftime("%d/%m/%Y  %H:%M:%S")
    cv2.putText(display, ts, (w - 205, 62),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (210, 235, 255), 1)

    bottom_text = "STATUS : SECURE"
    if current_status == "SUSPICIOUS":
        bottom_text = "STATUS : MOTION"
    elif current_status == "QUARANTINED":
        bottom_text = "STATUS : LOCKED"

    cv2.putText(display, bottom_text, (18, h - 18),
                cv2.FONT_HERSHEY_DUPLEX, 0.6, color, 2)

    draw_corner_marks(display, (90, 170, 220))

    if current_status == "SUSPICIOUS":
        alert = display.copy()
        cv2.rectangle(alert, (0, 0), (w, h), (0, 140, 255), -1)
        cv2.addWeighted(alert, 0.10, display, 0.90, 0, display)

        cv2.rectangle(display, (w - 210, h - 42), (w - 18, h - 12), (0, 170, 255), -1)
        cv2.putText(display, "MOTION DETECTED", (w - 192, h - 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.50, (255, 255, 255), 2)

    if paused:
        overlay = display.copy()
        cv2.rectangle(overlay, (0, 0), (w, h), (0, 0, 180), -1)
        cv2.addWeighted(overlay, 0.33, display, 0.67, 0, display)

        cv2.rectangle(display, (w // 2 - 140, h // 2 - 38),
                      (w // 2 + 140, h // 2 + 38), (15, 20, 28), -1)
        cv2.rectangle(display, (w // 2 - 140, h // 2 - 38),
                      (w // 2 + 140, h // 2 + 38), (0, 0, 255), 2)
        cv2.putText(display, "FEED LOCKED", (w // 2 - 82, h // 2 + 8),
                    cv2.FONT_HERSHEY_DUPLEX, 0.95, (0, 0, 255), 2)

    display = add_scan_lines(display, step=4, alpha=0.12)
    return display



def draw_bottom_dashboard(canvas, current_status, width, y_start, cam1_online, cam2_online):
    panel_h = 150
    cv2.rectangle(canvas, (0, y_start), (width, y_start + panel_h), (6, 12, 18), -1)
    cv2.line(canvas, (0, y_start), (width, y_start), (0, 110, 170), 2)

    cv2.rectangle(canvas, (18, y_start + 14), (360, y_start + 130), (10, 20, 28), -1)
    cv2.rectangle(canvas, (18, y_start + 14), (360, y_start + 130), (0, 110, 170), 1)

    cv2.putText(canvas, "LIVE VIEW", (32, y_start + 36),
                cv2.FONT_HERSHEY_SIMPLEX, 0.62, (210, 240, 255), 2)

    controls = [
        "REC MODE    : CONTINUOUS",
        "PLAYBACK    : AVAILABLE",
        "ALARM INPUT : READY",
        "EXPORT      : USB / NETWORK",
    ]

    yy = y_start + 62
    for line in controls:
        cv2.putText(canvas, line, (32, yy),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.48, (120, 190, 235), 1)
        yy += 22

    cv2.rectangle(canvas, (385, y_start + 14), (800, y_start + 130), (10, 20, 28), -1)
    cv2.rectangle(canvas, (385, y_start + 14), (800, y_start + 130), (0, 110, 170), 1)

    cv2.putText(canvas, "EVENT LIST", (400, y_start + 36),
                cv2.FONT_HERSHEY_SIMPLEX, 0.62, (210, 240, 255), 2)

    event_1 = "22:14:08  CH01  Live Stream" if cam1_online else "22:14:08  CH01  Video Loss"
    event_2 = "22:14:12  CH02  Live Stream" if cam2_online else "22:14:12  CH02  Video Loss"
    event_3 = "22:14:19  CH01  Motion Event" if current_status == "SUSPICIOUS" else "22:14:19  CH01  Live View Active"
    event_4 = "22:14:27  CH01  Stream Locked" if current_status == "QUARANTINED" else "22:14:27  CH01  Normal Stream"

    cv2.putText(canvas, event_1, (400, y_start + 60),
                cv2.FONT_HERSHEY_SIMPLEX, 0.46, (120, 190, 235) if cam1_online else (0, 170, 255), 1)
    cv2.putText(canvas, event_2, (400, y_start + 82),
                cv2.FONT_HERSHEY_SIMPLEX, 0.46, (120, 190, 235) if cam2_online else (0, 170, 255), 1)
    cv2.putText(canvas, event_3, (400, y_start + 104),
                cv2.FONT_HERSHEY_SIMPLEX, 0.46,
                (0, 200, 255) if current_status == "SUSPICIOUS" else (120, 190, 235), 1)
    cv2.putText(canvas, event_4, (400, y_start + 126),
                cv2.FONT_HERSHEY_SIMPLEX, 0.46,
                (0, 0, 255) if current_status == "QUARANTINED" else (120, 190, 235), 1)

    cv2.rectangle(canvas, (825, y_start + 14), (1260, y_start + 130), (10, 20, 28), -1)
    cv2.rectangle(canvas, (825, y_start + 14), (1260, y_start + 130), (0, 110, 170), 1)

    cv2.putText(canvas, "PLAYBACK TIMELINE", (840, y_start + 36),
                cv2.FONT_HERSHEY_SIMPLEX, 0.62, (210, 240, 255), 2)

    x1, x2 = 845, 1238
    yline = y_start + 74
    cv2.line(canvas, (x1, yline), (x2, yline), (80, 120, 150), 2)

    cv2.line(canvas, (855, yline), (955, yline), (60, 220, 100), 6)
    cv2.line(canvas, (980, yline), (1090, yline), (60, 220, 100), 6)
    cv2.line(canvas, (1120, yline), (1225, yline), (60, 220, 100), 6)
    cv2.line(canvas, (1015, yline), (1055, yline), (0, 200, 255), 6)

    cv2.line(canvas, (1145, yline - 16), (1145, yline + 16), (255, 255, 255), 2)
    cv2.circle(canvas, (1145, yline), 4, (255, 255, 255), -1)

    cv2.putText(canvas, "00:00", (845, y_start + 102),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, (120, 190, 235), 1)
    cv2.putText(canvas, "06:00", (935, y_start + 102),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, (120, 190, 235), 1)
    cv2.putText(canvas, "12:00", (1030, y_start + 102),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, (120, 190, 235), 1)
    cv2.putText(canvas, "18:00", (1125, y_start + 102),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, (120, 190, 235), 1)
    cv2.putText(canvas, "23:59", (1195, y_start + 102),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, (120, 190, 235), 1)

    ch01 = "ONLINE" if cam1_online else "NO SIGNAL"
    ch02 = "ONLINE" if cam2_online else "NO SIGNAL"
    cv2.putText(canvas, f"HDD : 1.8 TB FREE     CH01 : {ch01}     CH02 : {ch02}", (845, y_start + 124),
                cv2.FONT_HERSHEY_SIMPLEX, 0.44, (120, 190, 235), 1)



threading.Thread(target=check_status, daemon=True).start()

cap1, cam1_used_url = open_camera(CAMERA1_URLS, "CAM 01")
cap2, cam2_used_url = open_camera(CAMERA2_URLS, "CAM 02")

WINDOW_NAME = "CCTV Monitor"
cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
cv2.resizeWindow(WINDOW_NAME, 1400, 860)
cv2.moveWindow(WINDOW_NAME, 70, 30)

last_frame1 = None
last_frame2 = None

cam1_online = cap1 is not None
cam2_online = cap2 is not None

last_reconnect_try_1 = 0
last_reconnect_try_2 = 0
reconnect_interval = 3


while True:
    with _lock:
        current_status = _status

    paused = (current_status == "QUARANTINED")

    if cap1 is not None and not paused:
        ret1, frame1 = cap1.read()
        if ret1 and frame1 is not None:
            last_frame1 = frame1
            cam1_online = True
        else:
            cam1_online = False
            last_frame1 = None
            cap1.release()
            cap1 = None

    if cap2 is not None and not paused:
        ret2, frame2 = cap2.read()
        if ret2 and frame2 is not None:
            last_frame2 = frame2
            cam2_online = True
        else:
            cam2_online = False
            last_frame2 = None
            cap2.release()
            cap2 = None

    now = time.time()

    if cap1 is None and now - last_reconnect_try_1 >= reconnect_interval:
        last_reconnect_try_1 = now
        cap1, cam1_used_url = try_reconnect(CAMERA1_URLS, "CAM 01")
        cam1_online = cap1 is not None

    if cap2 is None and now - last_reconnect_try_2 >= reconnect_interval:
        last_reconnect_try_2 = now
        cap2, cam2_used_url = try_reconnect(CAMERA2_URLS, "CAM 02")
        cam2_online = cap2 is not None

    cam_w, cam_h = 620, 360

    if cam1_online and last_frame1 is not None:
        live_panel_1 = cv2.resize(last_frame1, (cam_w, cam_h))
        live_panel_1 = build_live_screen(live_panel_1, current_status, paused, "CAM 01", 1)
    else:
        live_panel_1 = make_empty_screen(cam_h, cam_w, "CAM 01", 1)

    if cam2_online and last_frame2 is not None:
        live_panel_2 = cv2.resize(last_frame2, (cam_w, cam_h))
        live_panel_2 = build_live_screen(live_panel_2, current_status, paused, "CAM 02", 2)
    else:
        live_panel_2 = make_empty_screen(cam_h, cam_w, "CAM 02", 2)

    top_row = cv2.hconcat([live_panel_1, live_panel_2])

    canvas_h = 760
    canvas_w = 1280
    canvas = np.zeros((canvas_h, canvas_w, 3), dtype=np.uint8)
    canvas[:] = (4, 10, 16)

    cv2.rectangle(canvas, (0, 0), (canvas_w, 42), (5, 14, 20), -1)
    cv2.line(canvas, (0, 41), (canvas_w, 41), (0, 120, 180), 1)

    cv2.putText(canvas, "SECURITY SURVEILLANCE DASHBOARD", (18, 27),
                cv2.FONT_HERSHEY_DUPLEX, 0.72, (220, 245, 255), 2)
    cv2.putText(canvas, "2 CHANNEL VIEW", (1085, 27),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (120, 190, 235), 2)

    x, y = 18, 58
    canvas[y:y + cam_h, x:x + (cam_w * 2)] = top_row
    cv2.rectangle(canvas, (x + cam_w - 1, y), (x + cam_w + 1, y + cam_h), (0, 140, 220), -1)
    cv2.rectangle(canvas, (16, 56), (16 + cam_w * 2 + 4, 56 + cam_h + 4), (0, 120, 180), 1)

    draw_bottom_dashboard(canvas, current_status, canvas_w, 440, cam1_online, cam2_online)

    cv2.imshow(WINDOW_NAME, canvas)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break


if cap1 is not None:
    cap1.release()
if cap2 is not None:
    cap2.release()

cv2.destroyAllWindows()