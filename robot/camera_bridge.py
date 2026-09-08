#!/usr/bin/env python3
"""Stream a Windows USB camera over HTTP for the SSH server.

Copy this file to the Windows PC that has the camera connected.

Install dependency:
    python -m pip install opencv-python

Run on the Windows PC:
    python -m robot.camera_bridge --camera-index 0 --listen-host <LAPTOP_IP> --port 8890

Test from the SSH server:
    curl http://<LAPTOP_IP>:8890/health
    ffmpeg -y -i http://<LAPTOP_IP>:8890/video -t 5 camera_test.mp4
"""

from __future__ import annotations

import argparse
import json
import signal
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional

from common.protocol import DEFAULT_CAMERA_PORT

try:
    import cv2
except ImportError as exc:  # pragma: no cover - user-facing startup error
    raise SystemExit("opencv-python is required. Run: python -m pip install opencv-python") from exc


class CameraState:
    def __init__(self, camera_index: int, width: int, height: int, fps: int, jpeg_quality: int) -> None:
        self.camera_index = camera_index
        self.width = width
        self.height = height
        self.fps = fps
        self.jpeg_quality = jpeg_quality
        self.lock = threading.Lock()
        self.latest_jpeg: Optional[bytes] = None
        self.latest_shape: Optional[tuple[int, int, int]] = None
        self.latest_time = 0.0
        self.frames = 0
        self.error = ""
        self.stop_event = threading.Event()

    def start(self) -> threading.Thread:
        thread = threading.Thread(target=self._capture_loop, name="camera-capture", daemon=True)
        thread.start()
        return thread

    def _capture_loop(self) -> None:
        cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap = cv2.VideoCapture(self.camera_index)
        if not cap.isOpened():
            self.error = f"Could not open camera index {self.camera_index}"
            return

        if self.width > 0:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        if self.height > 0:
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        if self.fps > 0:
            cap.set(cv2.CAP_PROP_FPS, self.fps)

        encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), int(self.jpeg_quality)]
        frame_interval = 1.0 / self.fps if self.fps > 0 else 0.0

        try:
            while not self.stop_event.is_set():
                ok, frame = cap.read()
                if not ok:
                    self.error = "Camera read failed"
                    time.sleep(0.05)
                    continue

                ok, encoded = cv2.imencode(".jpg", frame, encode_params)
                if not ok:
                    self.error = "JPEG encode failed"
                    continue

                with self.lock:
                    self.latest_jpeg = encoded.tobytes()
                    self.latest_shape = tuple(frame.shape)
                    self.latest_time = time.time()
                    self.frames += 1
                    self.error = ""

                if frame_interval > 0:
                    time.sleep(frame_interval * 0.25)
        finally:
            cap.release()


def make_handler(camera: CameraState):
    class CameraHandler(BaseHTTPRequestHandler):
        server_version = "MirobotCameraBridge/1.0"

        def log_message(self, fmt: str, *args) -> None:
            print(f"{self.address_string()} - {fmt % args}")

        def do_GET(self) -> None:  # noqa: N802 - stdlib API name
            if self.path in ("/", "/index.html"):
                self._send_html()
            elif self.path == "/health":
                self._send_health()
            elif self.path == "/snapshot.jpg":
                self._send_snapshot()
            elif self.path == "/video":
                self._send_video()
            else:
                self.send_error(HTTPStatus.NOT_FOUND, "Not found")

        def _send_html(self) -> None:
            body = (
                "<!doctype html><html><head><title>Mirobot Camera</title>"
                "<style>body{margin:0;background:#111;color:#eee;font-family:sans-serif}"
                "img{display:block;max-width:100vw;max-height:100vh;margin:auto}</style>"
                "</head><body><img src='/video'></body></html>"
            ).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_health(self) -> None:
            with camera.lock:
                payload = {
                    "ok": camera.latest_jpeg is not None and not camera.error,
                    "camera_index": camera.camera_index,
                    "frames": camera.frames,
                    "latest_age_sec": round(time.time() - camera.latest_time, 3) if camera.latest_time else None,
                    "shape": camera.latest_shape,
                    "error": camera.error,
                }
            body = (json.dumps(payload, indent=2) + "\n").encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_snapshot(self) -> None:
            jpeg = self._get_latest_or_wait()
            if jpeg is None:
                self.send_error(HTTPStatus.SERVICE_UNAVAILABLE, camera.error or "No camera frame yet")
                return
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(jpeg)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(jpeg)

        def _send_video(self) -> None:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            last_frame_id = -1
            while not camera.stop_event.is_set():
                with camera.lock:
                    jpeg = camera.latest_jpeg
                    frame_id = camera.frames
                if jpeg is None or frame_id == last_frame_id:
                    time.sleep(0.01)
                    continue
                last_frame_id = frame_id
                try:
                    self.wfile.write(b"--frame\r\n")
                    self.wfile.write(b"Content-Type: image/jpeg\r\n")
                    self.wfile.write(f"Content-Length: {len(jpeg)}\r\n\r\n".encode("ascii"))
                    self.wfile.write(jpeg)
                    self.wfile.write(b"\r\n")
                except (BrokenPipeError, ConnectionResetError):
                    return

        def _get_latest_or_wait(self, timeout: float = 3.0) -> Optional[bytes]:
            deadline = time.time() + timeout
            while time.time() < deadline:
                with camera.lock:
                    if camera.latest_jpeg is not None:
                        return camera.latest_jpeg
                time.sleep(0.02)
            return None

    return CameraHandler


def main() -> None:
    parser = argparse.ArgumentParser(description="HTTP/MJPEG bridge for a local USB camera.")
    parser.add_argument("--camera-index", type=int, default=0)
    parser.add_argument("--listen-host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=DEFAULT_CAMERA_PORT)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--jpeg-quality", type=int, default=80)
    args = parser.parse_args()

    camera = CameraState(args.camera_index, args.width, args.height, args.fps, args.jpeg_quality)
    camera.start()

    server = ThreadingHTTPServer((args.listen_host, args.port), make_handler(camera))

    def stop(*_args) -> None:
        print("\nstopping camera bridge...")
        camera.stop_event.set()
        server.shutdown()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    print(f"camera index: {args.camera_index}")
    print(f"bridge listening on {args.listen_host}:{args.port}")
    print(f"open: http://{args.listen_host}:{args.port}/")
    print("press Ctrl+C to stop")
    try:
        server.serve_forever()
    finally:
        camera.stop_event.set()
        server.server_close()


if __name__ == "__main__":
    main()
