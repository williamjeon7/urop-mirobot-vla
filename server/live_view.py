"""Live browser view of a running policy, from the observations the run already fetches.

No extra request reaches the Windows bridge or the robot: run_policy publishes each observation
it receives (before/after every move and while waiting for the arm to stop). Open the printed
http://127.0.0.1:<port> from VS Code (port forwarding) in a browser on the laptop.
"""
from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading

PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>Mirobot live</title>
<style>body{margin:0;background:#111;color:#eee;font:15px sans-serif;text-align:center}
img{max-width:100vw;max-height:88vh;margin-top:8px}#s{padding:6px}</style></head>
<body><img src="/stream"><div id="s">waiting for the first observation...</div>
<script>setInterval(async()=>{try{const r=await fetch('/status');const j=await r.json();
document.getElementById('s').textContent=j.text}catch(e){}},500)</script></body></html>"""


class LiveView:
    def __init__(self, port=8893, host="127.0.0.1"):
        self.condition = threading.Condition()
        self.jpeg = None
        self.serial = 0
        self.text = "waiting for the first observation..."
        view = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def _send(self, body, kind):
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):  # noqa: N802
                if self.path == "/":
                    self._send(PAGE.encode("utf-8"), "text/html; charset=utf-8")
                elif self.path == "/status":
                    self._send(json.dumps({"text": view.text}, ensure_ascii=False).encode("utf-8"),
                               "application/json")
                elif self.path == "/stream":
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                    self.end_headers()
                    seen = -1
                    try:
                        while True:
                            with view.condition:
                                view.condition.wait_for(lambda: view.serial != seen, timeout=5)
                                jpeg, seen = view.jpeg, view.serial
                            if jpeg is None:
                                continue
                            self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n"
                                             + f"Content-Length: {len(jpeg)}\r\n\r\n".encode() + jpeg + b"\r\n")
                    except (BrokenPipeError, ConnectionResetError):
                        return
                else:
                    self.send_response(HTTPStatus.NOT_FOUND)
                    self.end_headers()

        self.server = ThreadingHTTPServer((host, port), Handler)
        self.server.daemon_threads = True
        self.url = f"http://{host}:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": .2}, daemon=True).start()

    def publish(self, rgb, text):
        import cv2
        image = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        cv2.putText(image, text, (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(image, text, (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
        ok, jpeg = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if not ok:
            return
        with self.condition:
            self.jpeg, self.text = jpeg.tobytes(), text
            self.serial += 1
            self.condition.notify_all()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def attach(client, port, describe, log=print):
    """Start a LiveView and make client.observation() publish every frame. Never fails the run."""
    try:
        view = LiveView(port)
    except OSError as error:
        log(f"실시간 화면을 열지 못했습니다 (port {port}: {error}). 실행은 계속합니다.")
        return None
    original = client.observation

    def observed(*args, **kwargs):
        observation = original(*args, **kwargs)
        try:
            if observation.get("rgb") is not None:
                view.publish(observation["rgb"], describe(observation))
        except Exception:  # the viewer must never stop the robot run
            pass
        return observation

    client.observation = observed
    log(f"실시간 화면: {view.url}  (VS Code 의 'Open in Browser' 알림 또는 Ports 탭에서 열기)")
    return view
