"""Stream the real LIBERO simulation to a localhost browser without saving files."""

import argparse
import json
import math
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
.note { color: #9ca3af; line-height: 1.7; }
</style>
<main>
<h1>LIBERO Tabletop · Red / Green / Blue</h1>
<p id="status">시뮬레이터를 준비 중입니다. 첫 실행은 잠시 기다려 주세요.</p>
<div id="screen"><img id="video" src="/stream.mjpg" alt="LIBERO 실시간 화면"></div>
<p class="note">OASYS에서 실제 물리 시뮬레이션을 실행해 이 화면으로 전송합니다.<br>
블록 크기: <code>objects.py</code>의 <code>BLOCK_SIZE_MM</code> 수정 후 서버 재시작.<br>
현재는 zero action으로 배치를 확인합니다. 자동 집기 동작은 없습니다.<br>
이미지·동영상은 저장하지 않습니다. 종료: 서버 터미널에서 <code>Ctrl+C</code>.</p>
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
    if (info.error) status.textContent = '오류: ' + info.error + ' · 서버 터미널을 확인하세요.';
    else if (info.state === 'running') {
      status.textContent = 'LIVE · 한 변 ' + info.block_size_mm + ' mm · step ' + info.step
        + ' · goal=' + info.goal + ' · ' + info.fps.toFixed(1) + ' FPS'
        + (info.frame_age_seconds > 3 ? ' · 화면 갱신 지연' : '');
    } else status.textContent = '시뮬레이터 준비 중… (' + info.state + ')';
  } catch (_) {
    status.textContent = '서버 연결이 끊겼습니다. 실행 터미널과 VS Code 포트 전달을 확인하세요.';
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
        self.status = {"state": "starting", "step": 0, "goal": None,
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
    """Expose only a fixed page, read-only status, and an in-memory MJPEG stream."""
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
                    self.reply(200, "application/json; charset=utf-8",
                               json.dumps(simulation.get_status()).encode("utf-8"))
                elif path == "/stream.mjpg":
                    self.stream()
                else:
                    self.reply(404, "text/plain; charset=utf-8", b"Not found")
            except (BrokenPipeError, ConnectionResetError, TimeoutError):
                pass

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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--size", type=int, default=CAMERA_SIZE, help="Camera resolution, not cube size.")
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--fps", type=float, default=FPS)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535 or not 128 <= args.size <= 2048:
        parser.error("port must be 1..65535 and size must be 128..2048")
    if not math.isfinite(args.fps) or not 0 < args.fps <= 60:
        parser.error("fps must be finite and in (0, 60]")
    simulation = LiveSimulation(resolution=args.size, seed=args.seed, fps=args.fps)
    try:
        server = make_server(simulation, port=args.port)
    except OSError as error:
        print("Cannot start localhost viewer: {}. Try --port with an unused port.".format(error),
              file=sys.stderr)
        return 1
    print("Browser viewer: http://127.0.0.1:{}".format(args.port), flush=True)
    print("Remote-SSH: forward port {} in VS Code PORTS, then open http://localhost:{}".format(
        args.port, args.port), flush=True)
    print("No images or videos are saved. Stop with Ctrl+C.", flush=True)
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
