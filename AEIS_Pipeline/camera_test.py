import cv2
import requests
import threading
import time
import numpy as np

print("========== CCTV DASHBOARD ==========")

SERVER_URL = "http://192.168.29.89:5000/alert"

_lock = threading.Lock()
_status = "NORMAL"


def check_status():
    global _status
    while True:
        try:
            res = requests.get(SERVER_URL, timeout=2)
            data = res.json()

            with _lock:
                _status = data.get("status", "NORMAL")

        except:
            pass

        time.sleep(2)


def open_camera(url):
    cap = cv2.VideoCapture(url)
    time.sleep(1)

    if cap.isOpened():
        print("✅ Camera connected")
        return cap
    return None


threading.Thread(target=check_status, daemon=True).start()

cap = open_camera("http://192.168.29.36:4747/video")

WINDOW_NAME = "CCTV Monitor"
cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)

last_frame = None

while True:
    with _lock:
        status = _status

    paused = status in ["HIGH", "QUARANTINED"]

    if cap is not None and not paused:
        ret, frame = cap.read()
        if ret:
            last_frame = frame

    if paused:
        frame = np.zeros((360, 620, 3), dtype=np.uint8)
        cv2.putText(frame, "CAMERA ISOLATED",
                    (120, 180), cv2.FONT_HERSHEY_SIMPLEX,
                    0.7, (0, 0, 255), 2)
    elif last_frame is not None:
        frame = cv2.resize(last_frame, (620, 360))
    else:
        frame = np.zeros((360, 620, 3), dtype=np.uint8)

    cv2.imshow(WINDOW_NAME, frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

if cap:
    cap.release()

cv2.destroyAllWindows()