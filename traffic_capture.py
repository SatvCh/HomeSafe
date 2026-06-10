"""
traffic_capture.py
==================
Real-traffic capture module for AEIS.

Captures packets on the local network interface using Scapy,
extracts ML features in fixed time windows, and POSTs them
to the Flask server — same /data endpoint used by the live
pipeline.

Usage (standalone):
    python traffic_capture.py

Usage (from server via API):
    POST /start_capture  {"device_ip": "192.168.137.168", "window_sec": 5}
    POST /stop_capture

Architecture:
    Packets → kernel BPF filter → Python handler → feature window
    → POST /data (cam1) → _run_ml → dashboard update

Safety:
    Only captures host-local network traffic.
    No packets are injected or forwarded externally.
"""

from __future__ import annotations

import threading
import time
import requests
import logging

log = logging.getLogger("traffic_capture")

# ── Optional scapy import (graceful degradation) ──────────────────────────────
try:
    from scapy.all import sniff, IP
    SCAPY_AVAILABLE = True
except ImportError:
    SCAPY_AVAILABLE = False
    log.warning("Scapy not available — real capture mode disabled. Install with: pip install scapy")


# ── Config ────────────────────────────────────────────────────────────────────
DEFAULT_SERVER_URL = "http://127.0.0.1:5000/data"
DEFAULT_WINDOW_SEC = 5
DEFAULT_INTERFACE  = "Wi-Fi"          # Change to your interface name


# ═══════════════════════════════════════════════════════════════════════════════
# CaptureSession — one session per start_capture call
# ═══════════════════════════════════════════════════════════════════════════════
class CaptureSession:
    """
    Manages a single packet capture session.

    Thread safety: all public methods are thread-safe.
    The capture runs on a daemon thread — it stops automatically
    when stop() is called or the process exits.
    """

    def __init__(
        self,
        device_ip:   str | None = None,
        window_sec:  int        = DEFAULT_WINDOW_SEC,
        interface:   str        = DEFAULT_INTERFACE,
        server_url:  str        = DEFAULT_SERVER_URL,
        send_retries: int       = 3,
    ):
        self.device_ip   = device_ip        # None = capture all hosts
        self.window_sec  = window_sec
        self.interface   = interface
        self.server_url  = server_url
        self.send_retries = send_retries

        self._lock        = threading.Lock()
        self._stop_event  = threading.Event()
        self._thread: threading.Thread | None = None
        self._packet_buf: list[dict]  = []   # [{src, dst, len}, ...]
        self.running      = False
        self.windows_sent = 0
        self.last_features: dict | None = None

    # ── Public API ─────────────────────────────────────────────────────────────
    def start(self) -> bool:
        """Start capture in a background thread. Returns False if already running."""
        if not SCAPY_AVAILABLE:
            log.error("Cannot start capture: Scapy is not installed.")
            return False
        with self._lock:
            if self.running:
                return False
            self._stop_event.clear()
            self.running = True

        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="aeis-capture")
        self._thread.start()
        log.info(f"Capture started — device={self.device_ip or 'ALL'}  "
                 f"interface={self.interface}  window={self.window_sec}s")
        return True

    def stop(self) -> None:
        """Signal the capture loop to stop and wait for it."""
        self._stop_event.set()
        with self._lock:
            self.running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=self.window_sec + 2)
        log.info("Capture stopped.")

    def status(self) -> dict:
        with self._lock:
            return {
                "running":       self.running,
                "device_ip":     self.device_ip,
                "interface":     self.interface,
                "window_sec":    self.window_sec,
                "windows_sent":  self.windows_sent,
                "last_features": self.last_features,
                "scapy_ok":      SCAPY_AVAILABLE,
            }

    # ── Internal loop ──────────────────────────────────────────────────────────
    def _run_loop(self) -> None:
        """Main capture loop — runs on the daemon thread."""
        bpf = f"host {self.device_ip}" if self.device_ip else ""

        while not self._stop_event.is_set():
            # Clear window buffer
            with self._lock:
                self._packet_buf.clear()

            # Sniff for one window
            try:
                sniff(
                    iface=self.interface,
                    filter=bpf or None,
                    timeout=self.window_sec,
                    prn=self._handle_packet,
                    store=False,
                    stop_filter=lambda _: self._stop_event.is_set(),
                )
            except Exception as e:
                log.error(f"Sniff error: {e}")
                time.sleep(1)
                continue

            if self._stop_event.is_set():
                break

            # Extract features and send
            with self._lock:
                buf = list(self._packet_buf)

            features = self._extract_features(buf)
            if features:
                self.last_features = features
                self._send(features)
                self.windows_sent += 1
            else:
                log.debug("No packets captured in this window.")

    def _handle_packet(self, packet) -> None:
        """Scapy callback — runs in the sniff thread (may be C-level thread)."""
        if IP in packet:
            with self._lock:
                self._packet_buf.append({
                    "src": packet[IP].src,
                    "dst": packet[IP].dst,
                    "len": len(packet),
                })

    def _extract_features(self, buf: list[dict]) -> dict | None:
        """Convert raw packet list into ML feature dict."""
        if not buf:
            return None

        count    = len(buf)
        avg_size = sum(p["len"] for p in buf) / count
        dests    = len(set(p["dst"] for p in buf))
        hour     = time.localtime().tm_hour

        features = {
            "packets_per_window": count,
            "avg_packet_size":    round(avg_size, 2),
            "dest_count":         dests,
            "activity_hour":      hour,
        }

        log.debug(
            f"  [window] pkts={count}  avg_size={avg_size:.1f}B  "
            f"dest={dests}  hour={hour}"
        )
        return features

    def _send(self, features: dict) -> bool:
        """POST features to the Flask server with retry."""
        for attempt in range(1, self.send_retries + 1):
            try:
                r = requests.post(self.server_url, json=features, timeout=3)
                if r.status_code == 200:
                    resp = r.json()
                    log.info(f"  ✅ [{self.windows_sent+1}] Sent → status={resp.get('status','?')}")
                    return True
                log.warning(f"  ⚠ Server HTTP {r.status_code}")
            except requests.exceptions.ConnectionError:
                log.warning(f"  ❌ Connection error (attempt {attempt}/{self.send_retries})")
            except requests.exceptions.Timeout:
                log.warning(f"  ❌ Timeout (attempt {attempt}/{self.send_retries})")
            time.sleep(0.4)
        log.error("  ✖ All retries failed")
        return False


# ── Module-level singleton used by server endpoints ───────────────────────────
_active_session: CaptureSession | None = None
_session_lock   = threading.Lock()


def start_capture(device_ip: str | None = None,
                  window_sec: int = DEFAULT_WINDOW_SEC,
                  interface: str  = DEFAULT_INTERFACE) -> dict:
    """Start (or replace) the global capture session."""
    global _active_session
    with _session_lock:
        if _active_session and _active_session.running:
            _active_session.stop()

        _active_session = CaptureSession(
            device_ip  = device_ip or None,
            window_sec = window_sec,
            interface  = interface,
        )
        ok = _active_session.start()
        return {"started": ok, "scapy_ok": SCAPY_AVAILABLE, "device_ip": device_ip, "window_sec": window_sec}


def stop_capture() -> dict:
    """Stop the global capture session."""
    global _active_session
    with _session_lock:
        if _active_session and _active_session.running:
            _active_session.stop()
            return {"stopped": True}
        return {"stopped": False, "reason": "No active capture"}


def capture_status() -> dict:
    """Return status of the global capture session."""
    with _session_lock:
        if _active_session:
            return _active_session.status()
        return {"running": False, "scapy_ok": SCAPY_AVAILABLE}


# ── Standalone entry point ────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s  %(message)s")

    ip  = sys.argv[1] if len(sys.argv) > 1 else None
    win = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_WINDOW_SEC

    print("=" * 55)
    print("  AEIS Traffic Capture — Standalone Mode")
    print(f"  Device IP  : {ip or 'ALL'}")
    print(f"  Window     : {win}s")
    print(f"  Server     : {DEFAULT_SERVER_URL}")
    print(f"  Scapy OK   : {SCAPY_AVAILABLE}")
    print("=" * 55)

    if not SCAPY_AVAILABLE:
        print("ERROR: Install scapy first:  pip install scapy")
        sys.exit(1)

    session = CaptureSession(device_ip=ip, window_sec=win)
    session.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping…")
        session.stop()
