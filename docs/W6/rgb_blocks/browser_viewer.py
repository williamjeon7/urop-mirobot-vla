"""Stream the real LIBERO simulation to a localhost browser without saving files."""

import argparse
import errno
import http.client
import json
import math
import secrets
import socket
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

PORT = 8766
CAMERA_SIZE = 512
SEED = 0
FPS = 20.0
VIEWER_ID = "libero-rgb-blocks-v1"

PAGE = """<!doctype html>
<html lang="ko">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LIBERO · RGB blocks</title>
<style>
body { margin: 0; background: #111827; color: #e5e7eb; font: 16px system-ui, sans-serif; }
main { max-width: 780px; margin: 32px auto; padding: 0 20px; }
h1 { font-size: 24px; } a { color: #93c5fd; }
#screen { background: #030712; border-radius: 12px; overflow: hidden; }
img { display: block; width: 100%; height: auto; min-height: 300px; object-fit: contain; }
#status { min-height: 48px; line-height: 1.6; }
</style>
<main>
<h1>LIBERO Tabletop · Red / Green / Blue</h1>
<p id="status">시뮬레이터 준비 중…</p>
<div id="screen"><img id="video" src="/stream.mjpg" alt="LIBERO 실시간 화면"></div>
</main>
<script>
const status = document.getElementById('status');
const video = document.getElementById('video');
video.onerror = () => setTimeout(() => { video.src = '/stream.mjpg?t=' + Date.now(); }, 2000);
async function update() {
  try {
    const response = await fetch('/status', {cache: 'no-store'});
    if (!response.ok) throw new Error('HTTP ' + response.status);
    const info = await response.json();
    video.style.display = '';
    if (info.error) status.textContent = '오류: ' + info.error;
    else if (info.state === 'running') {
      status.textContent = 'LIVE · 한 변 ' + info.block_size_mm + ' mm · step ' + info.step
        + ' · goal=' + info.goal + ' · ' + info.fps.toFixed(1) + ' FPS'
        + (info.frame_age_seconds > 3 ? ' · 화면 갱신 지연' : '');
    } else status.textContent = info.state === 'stopped' ? '종료' : '시뮬레이터 준비 중…';
  } catch (_) {
    status.textContent = '연결 끊김';
    video.style.display = 'none';
  }
}
update(); setInterval(update, 1000);
</script>
</html>
""".encode("utf-8")


class LiveSimulation:
    """Own MuJoCo and its GL context in one thread; share only JPEG bytes."""

    def __init__(self, resolution=CAMERA_SIZE, seed=SEED, fps=FPS):
        self.resolution = resolution
        self.seed = seed
        self.fps = fps
        self.stop_event = threading.Event()
        self.condition = threading.Condition()
        self.thread = None
        self.jpeg = None
        self.frame_time = None
        self.status = {"viewer_id": VIEWER_ID, "state": "starting", "step": 0, "goal": None,
                       "block_size_mm": None, "fps": 0.0, "error": None,
                       "zero_actions_only": True, "saved_files": False}

    def start(self):
        self.thread = threading.Thread(target=self._run, name="rgb-simulation", daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        with self.condition:
            self.condition.notify_all()
        if self.thread is not None:
            self.thread.join(timeout=10)

    def get_status(self):
        with self.condition:
            result = dict(self.status)
            result["frame_age_seconds"] = (
                None if self.frame_time is None else time.monotonic() - self.frame_time
            )
            return result

    def wait_for_frame(self, previous_step, timeout=1.0):
        with self.condition:
            self.condition.wait_for(
                lambda: self.stop_event.is_set() or self.status["error"] is not None
                or (self.jpeg is not None and self.status["step"] != previous_step),
                timeout=timeout,
            )
            if self.jpeg is None or self.status["step"] == previous_step:
                return None
            return self.jpeg, self.status["step"]

    def _publish(self, obs, step, goal, block_size_mm, frame_from, cv2, actual_fps):
        ok, encoded = cv2.imencode(".jpg", frame_from(obs, step, goal),
                                  [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not ok:
            raise RuntimeError("OpenCV could not encode the simulation frame.")
        with self.condition:
            self.jpeg = encoded.tobytes()
            self.frame_time = time.monotonic()
            self.status.update(state="running", step=step, goal=goal,
                               block_size_mm=block_size_mm, fps=actual_fps)
            self.condition.notify_all()

    def _run(self):
        env = None
        try:
            import cv2
            import numpy as np
            if __package__:
                from .test_rgb_blocks import BLOCK_SIZE_MM, frame_from, init_checks, make_env
            else:
                from test_rgb_blocks import BLOCK_SIZE_MM, frame_from, init_checks, make_env
            env = make_env(seed=self.seed, size=self.resolution)
            obs = env.reset()
            checks = init_checks(env)
            scene = env.env
            expected = {color + "_block_1" for color in ("red", "green", "blue")}
            if set(scene.objects_dict) != expected or scene.fixtures_dict:
                raise RuntimeError("Expected only the three RGB cubes on the tabletop.")
            if not all(checks.values()):
                raise RuntimeError("The BDDL initial placement conditions failed.")
            for obj in scene.objects_dict.values():
                collision = env.sim.model.geom_name2id(obj.contact_geoms[0])
                if not np.allclose(env.sim.model.geom_size[collision], BLOCK_SIZE_MM / 2000):
                    raise RuntimeError("Cube dimensions do not match BLOCK_SIZE_MM.")
            self._publish(obs, 0, bool(env.check_success()), BLOCK_SIZE_MM, frame_from, cv2, 0.0)
            print("RGB simulation ready: {} mm cubes; initial checks {}".format(
                BLOCK_SIZE_MM, checks), flush=True)
            action = np.zeros(7, dtype=np.float32)
            step = 0
            previous_frame = time.monotonic()
            while not self.stop_event.is_set():
                started = time.monotonic()
                obs, _, _, _ = env.step(action)
                step += 1
                now = time.monotonic()
                actual_fps = 1.0 / max(now - previous_frame, 0.000001)
                previous_frame = now
                self._publish(obs, step, bool(env.check_success()), BLOCK_SIZE_MM,
                              frame_from, cv2, actual_fps)
                self.stop_event.wait(max(0, 1.0 / self.fps - (time.monotonic() - started)))
        except Exception as error:
            with self.condition:
                self.status.update(state="error", error="{}: {}".format(type(error).__name__, error))
                self.condition.notify_all()
            traceback.print_exc()
        finally:
            try:
                if env is not None:
                    env.close()
            finally:
                with self.condition:
                    if self.status["error"] is None:
                        self.status["state"] = "stopped"
                    self.condition.notify_all()


def make_server(simulation, port=PORT):
    """Serve frames and allow a terminal client to stop this specific instance."""
    shutdown_token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, code, content_type, body):
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urlsplit(self.path).path
            try:
                if path == "/":
                    self.reply(200, "text/html; charset=utf-8", PAGE)
                elif path == "/status":
                    status = simulation.get_status()
                    status["shutdown_token"] = shutdown_token
                    self.reply(200, "application/json; charset=utf-8",
                               json.dumps(status).encode("utf-8"))
                elif path == "/stream.mjpg":
                    self.stream()
                else:
                    self.reply(404, "text/plain; charset=utf-8", b"Not found")
            except (BrokenPipeError, ConnectionResetError, TimeoutError):
                pass

        def do_POST(self):
            if urlsplit(self.path).path != "/shutdown":
                self.reply(404, "text/plain; charset=utf-8", b"Not found")
                return
            token = self.headers.get("X-RGB-Viewer-Token", "")
            if (self.headers.get("Origin") is not None or not token.isascii()
                    or not secrets.compare_digest(token, shutdown_token)):
                self.reply(403, "text/plain; charset=utf-8", b"Forbidden")
                return
            try:
                self.reply(202, "application/json", b'{"stopping":true}')
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            simulation.stop_event.set()
            with simulation.condition:
                simulation.condition.notify_all()
            self.server.shutdown()

        def stream(self):
            self.connection.settimeout(5)
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            previous_step = -1
            while not simulation.stop_event.is_set():
                frame = simulation.wait_for_frame(previous_step)
                if frame is None:
                    if simulation.get_status()["error"] is not None:
                        break
                    continue
                jpeg, previous_step = frame
                self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                                 + str(len(jpeg)).encode("ascii") + b"\r\n\r\n" + jpeg + b"\r\n")
                self.wfile.flush()

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    server.block_on_close = False
    return server


def probe_existing_viewer(port, timeout=2.0):
    """Recognize our viewer only; never stop or reuse an unrelated service."""
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        connection.request("GET", "/status")
        response = connection.getresponse()
        if response.status != 200:
            return None
        body = response.read(65537)
        if len(body) > 65536:
            return None
        status = json.loads(body.decode("utf-8"))
        required = {"state", "step", "goal", "block_size_mm", "fps", "error",
                    "zero_actions_only", "saved_files", "frame_age_seconds"}
        if not isinstance(status, dict) or not required.issubset(status):
            return None
        if (status["state"] not in ("starting", "running", "error", "stopped")
                or type(status["step"]) is not int or status["step"] < 0
                or status["zero_actions_only"] is not True or status["saved_files"] is not False):
            return None
        if status.get("viewer_id") == VIEWER_ID:
            return status
        if status.get("viewer_id") is not None:
            return None
        # A viewer started before this fix has no ID; require the exact page too.
        connection.request("GET", "/")
        response = connection.getresponse()
        if response.status == 200 and response.read(len(PAGE) + 1) == PAGE:
            return status
    except (OSError, http.client.HTTPException, UnicodeError, ValueError, RecursionError):
        return None
    finally:
        connection.close()
    return None


def print_viewer_address(port):
    print("http://localhost:{}".format(port), flush=True)


def request_shutdown(port, token, timeout=2.0):
    if not isinstance(token, str) or not token:
        return False
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        connection.request("POST", "/shutdown", body=b"",
                           headers={"X-RGB-Viewer-Token": token})
        response = connection.getresponse()
        response.read(1024)
        return response.status == 202
    except (OSError, http.client.HTTPException, ValueError, UnicodeError):
        return False
    finally:
        connection.close()


def wait_for_server_exit(port, timeout=15.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                pass
        except ConnectionRefusedError:
            return True
        except OSError:
            pass
        time.sleep(0.1)
    return False


def stop_existing_viewer(port, status=None):
    if status is None:
        status = probe_existing_viewer(port)
    if status is None:
        if wait_for_server_exit(port, timeout=0.5):
            print("서버가 종료되어 있습니다.", flush=True)
            return 0
        print("RGB 서버로 확인되지 않아 종료하지 않았습니다.", file=sys.stderr)
        return 1
    if not request_shutdown(port, status.get("shutdown_token")):
        print("서버 종료 요청에 실패했습니다.", file=sys.stderr)
        return 1
    if not wait_for_server_exit(port):
        print("서버 종료를 확인하지 못했습니다.", file=sys.stderr)
        return 1
    print("서버 종료", flush=True)
    return 0


def follow_existing_viewer(port, token):
    try:
        while True:
            time.sleep(0.5)
            current = probe_existing_viewer(port)
            if current is None:
                if wait_for_server_exit(port, timeout=0.5):
                    return 0
                continue
            if current.get("shutdown_token") != token:
                return 0
    except KeyboardInterrupt:
        return stop_existing_viewer(port, status={"shutdown_token": token})


def reuse_existing_viewer(status, port):
    """Report existing settings honestly; failed or stale workers are not LIVE."""
    if status["error"] is not None or status["state"] not in ("starting", "running"):
        print("기존 RGB 서버가 있지만 정상 실행 상태가 아닙니다: {}. "
              "서버를 시작한 터미널에서 종료한 뒤 다시 실행하세요.".format(
                  status["error"] or status["state"]), file=sys.stderr)
        return 1
    age = status["frame_age_seconds"]
    if status["state"] == "running" and (
            type(age) not in (int, float) or not 0 <= age <= 5 or not math.isfinite(age)):
        print("기존 RGB 서버의 화면 갱신이 멈췄습니다. "
              "서버를 시작한 터미널에서 종료한 뒤 다시 실행하세요.", file=sys.stderr)
        return 1
    token = status.get("shutdown_token")
    if not isinstance(token, str) or not token:
        print("이전 버전 서버입니다. 기존 실행 터미널에서 종료한 뒤 다시 실행하세요.", file=sys.stderr)
        return 1
    print_viewer_address(port)
    print("기존 서버 연결 · Ctrl+C로 종료", flush=True)
    return follow_existing_viewer(port, token)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--size", type=int, default=CAMERA_SIZE, help="Camera resolution, not cube size.")
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--fps", type=float, default=FPS)
    parser.add_argument("--stop", action="store_true", help="Stop the RGB server on this port.")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535 or not 128 <= args.size <= 2048:
        parser.error("port must be 1..65535 and size must be 128..2048")
    if not math.isfinite(args.fps) or not 0 < args.fps <= 60:
        parser.error("fps must be finite and in (0, 60]")
    if args.stop:
        return stop_existing_viewer(args.port)
    simulation = LiveSimulation(resolution=args.size, seed=args.seed, fps=args.fps)
    try:
        server = make_server(simulation, port=args.port)
    except OSError as error:
        if error.errno == errno.EADDRINUSE:
            existing = probe_existing_viewer(args.port)
            if existing is not None:
                return reuse_existing_viewer(existing, args.port)
        print("Cannot start localhost viewer: {}. Try --port with an unused port.".format(error),
              file=sys.stderr)
        return 1
    print_viewer_address(args.port)
    print("Ctrl+C로 종료", flush=True)
    try:
        simulation.start()
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        simulation.stop()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
