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

if __package__:
    from .tasks import TASK_NAMES, task_spec
else:
    from tasks import TASK_NAMES, task_spec

PORT = 8766
CAMERA_SIZE = 512
SEED = 0
FPS = 20.0
# --pickup: seconds to keep showing the result before the next seed.
RESULT_HOLD_SECONDS = 3.0
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
#status { min-height: 48px; line-height: 1.6; white-space: pre-line; }
</style>
<main>
<h1>LIBERO Tabletop · Red / Green / Blue</h1>
<p id="instruction">RGB 블록 초기 배치</p>
<p id="status">시뮬레이터 준비 중…</p>
<div id="screen"><img id="video" src="/stream.mjpg" alt="LIBERO 실시간 화면"></div>
</main>
<script>
const status = document.getElementById('status');
const instruction = document.getElementById('instruction');
const video = document.getElementById('video');
video.onerror = () => setTimeout(() => { video.src = '/stream.mjpg?t=' + Date.now(); }, 2000);
async function update() {
  try {
    const response = await fetch('/status', {cache: 'no-store'});
    if (!response.ok) throw new Error('HTTP ' + response.status);
    const info = await response.json();
    instruction.textContent = info.pickup ? 'Pick up 실행 · ' + info.instruction
      : info.target_object ? '초기 환경 · ' + info.instruction : 'RGB 블록 초기 배치';
    video.style.display = '';
    if (info.error) status.textContent = '오류: ' + info.error;
    else if (info.state === 'running' && info.pickup) {
      const last = info.last_result;
      status.textContent = 'LIVE · episode ' + info.episode + ' (seed ' + info.seed + ') · '
        + info.phase + ' · step ' + info.step + ' · goal ' + info.goal
        + ' · ' + info.fps.toFixed(1) + ' FPS'
        + (info.frame_age_seconds > 3 ? ' · 화면 갱신 지연' : '')
        + '\n성공 ' + info.successes + ' / ' + info.completed
        + (last ? ' · 직전 seed ' + last.seed + ': ' + (last.success
            ? '성공 (' + last.steps + ' step, ' + last.lift_height_m + ' m 상승)'
            : '실패 · ' + last.reason) : '');
    } else if (info.state === 'running') {
      status.textContent = 'LIVE · 한 변 ' + info.block_size_mm + ' mm · step ' + info.step
        + (info.placement_ok ? ' · 배치 정상' : ' · 배치 확인 필요')
        + ' · ' + info.fps.toFixed(1) + ' FPS'
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

    def __init__(self, resolution=CAMERA_SIZE, seed=SEED, fps=FPS, task="scene", pickup=False):
        self.resolution = resolution
        self.seed = seed
        self.fps = fps
        self.task = task_spec(task)
        if pickup and not self.task["pickup_implemented"]:
            raise ValueError("--pickup needs --task red, green or blue.")
        self.pickup = pickup
        self.stop_event = threading.Event()
        self.condition = threading.Condition()
        self.thread = None
        self.jpeg = None
        self.frame_time = None
        self.status = {"viewer_id": VIEWER_ID, "state": "starting", "step": 0, "goal": None,
                       "block_size_mm": None, "fps": 0.0, "error": None,
                       "zero_actions_only": not pickup, "saved_files": False,
                       "task": self.task["name"], "instruction": self.task["language"],
                       "target_object": self.task["target_object"],
                       "pickup_implemented": self.task["pickup_implemented"],
                       "goal_kind": self.task["goal_kind"],
                       "placement_ok": None, "pickup": pickup, "seed": seed}
        if pickup:
            self.status.update(phase=None, episode=0, completed=0, successes=0,
                               last_result=None)

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

    def _publish(self, obs, step, goal, block_size_mm, frame_from, cv2, actual_fps,
                 scene_info):
        ok, encoded = cv2.imencode(".jpg", frame_from(obs, step, goal),
                                  [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not ok:
            raise RuntimeError("OpenCV could not encode the simulation frame.")
        with self.condition:
            self.jpeg = encoded.tobytes()
            self.frame_time = time.monotonic()
            self.status.update(state="running", step=step, goal=goal,
                               block_size_mm=block_size_mm, fps=actual_fps)
            self.status.update(scene_info)
            self.condition.notify_all()

    def _run_pickup(self, env, cv2, np, block_size_mm, frame_from, scene_state):
        """Repeat pickup.py on seed, seed+1, ... and stream every Panda step."""
        if __package__:
            from .pickup import pickup_success, run_pickup
        else:
            from pickup import pickup_success, run_pickup

        class Stopped(Exception):
            pass

        target = self.task["target_object"]
        clock = {"last": time.monotonic()}

        def show(obs, step, goal, phase, extra):
            # Pace to the requested FPS so the motion is watchable in real time.
            self.stop_event.wait(max(0, 1.0 / self.fps - (time.monotonic() - clock["last"])))
            if self.stop_event.is_set():
                raise Stopped
            now = time.monotonic()
            actual_fps = 1.0 / max(now - clock["last"], 0.000001)
            clock["last"] = now
            caption = "{} | seed {} | {} | step {} | goal={}".format(
                self.task["name"], extra["seed"], phase, step, goal)
            self._publish(obs, step, goal, block_size_mm,
                          lambda o, s, g: frame_from(o, s, g, caption=caption),
                          cv2, actual_fps, dict(extra, phase=phase))

        seed = self.seed
        episode = 0
        try:
            while not self.stop_event.is_set():
                episode += 1
                env.seed(seed)
                obs = env.reset()
                extra = dict(scene_state(env), seed=seed, episode=episode)
                show(obs, 0, bool(env.check_success()), "reset", extra)
                try:
                    obs, result = run_pickup(
                        env, obs, target,
                        on_step=lambda o, s, p, g: show(o, s, g, p, extra))
                    success = pickup_success(result)
                    outcome = {"seed": seed, "success": success, "steps": result["steps"],
                               "lift_height_m": result["lift_height_m"],
                               "reason": None if success else "판정 조건 불충족"}
                    held = result["still_grasped"]
                except RuntimeError as error:
                    outcome = {"seed": seed, "success": False, "steps": None,
                               "lift_height_m": None, "reason": str(error)}
                    held = False
                print("seed {}: {}".format(seed, json.dumps(outcome, ensure_ascii=False)), flush=True)
                with self.condition:
                    self.status["completed"] += 1
                    self.status["successes"] += int(outcome["success"])
                    self.status["last_result"] = outcome
                # Keep the final pose on screen: zero OSC delta, gripper as it ended.
                hold = np.zeros(7, dtype=np.float32)
                hold[6] = 1.0 if held else -1.0
                for step in range(1, int(RESULT_HOLD_SECONDS * self.fps) + 1):
                    obs, _, _, _ = env.step(hold)
                    show(obs, step, bool(env.check_success()),
                         "result " + ("success" if outcome["success"] else "fail"), extra)
                seed += 1
        except Stopped:
            pass

    def _run(self):
        env = None
        try:
            import cv2
            import numpy as np
            if __package__:
                from .test_rgb_blocks import BLOCK_SIZE_MM, frame_from, make_env, scene_state
            else:
                from test_rgb_blocks import BLOCK_SIZE_MM, frame_from, make_env, scene_state
            env = make_env(seed=self.seed, size=self.resolution, task=self.task["name"])
            if self.pickup:
                self._run_pickup(env, cv2, np, BLOCK_SIZE_MM, frame_from, scene_state)
                return
            obs = env.reset()
            scene_info = scene_state(env)
            self._publish(obs, 0, bool(env.check_success()), BLOCK_SIZE_MM, frame_from,
                          cv2, 0.0, scene_info)
            print("RGB simulation ready: {} mm cubes; initial checks {}".format(
                BLOCK_SIZE_MM, scene_info["initial_checks"]), flush=True)
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
                scene_info = scene_state(env, require_contact=step >= 20)
                self._publish(obs, step, bool(env.check_success()), BLOCK_SIZE_MM,
                              frame_from, cv2, actual_fps, scene_info)
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
                or type(status["zero_actions_only"]) is not bool
                or status["saved_files"] is not False):
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


def reuse_existing_viewer(status, port, requested_task="scene", requested_pickup=False):
    """Report existing settings honestly; failed or stale workers are not LIVE."""
    if bool(status.get("pickup", False)) != requested_pickup:
        print("기존 RGB 서버는 {} 모드입니다. --stop으로 종료한 뒤 다시 실행하세요.".format(
            "--pickup" if status.get("pickup") else "배치 확인"), file=sys.stderr)
        return 1
    if status.get("task", "scene") != requested_task:
        print("기존 RGB 서버의 Task는 {}입니다. --stop으로 종료한 뒤 "
              "--task {}로 다시 실행하세요.".format(status.get("task", "scene"), requested_task),
              file=sys.stderr)
        return 1
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
    parser.add_argument("--task", choices=TASK_NAMES, default="scene",
                        help="Select the prepared task target.")
    parser.add_argument("--pickup", action="store_true",
                        help="Run pickup.py on seed, seed+1, ... and stream the Panda (colour tasks).")
    parser.add_argument("--fps", type=float, default=FPS)
    parser.add_argument("--stop", action="store_true", help="Stop the RGB server on this port.")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535 or not 128 <= args.size <= 2048:
        parser.error("port must be 1..65535 and size must be 128..2048")
    if not math.isfinite(args.fps) or not 0 < args.fps <= 60:
        parser.error("fps must be finite and in (0, 60]")
    if args.pickup and args.task == "scene":
        parser.error("--pickup needs --task red, green or blue")
    if args.stop:
        return stop_existing_viewer(args.port)
    simulation = LiveSimulation(resolution=args.size, seed=args.seed, fps=args.fps,
                                task=args.task, pickup=args.pickup)
    try:
        server = make_server(simulation, port=args.port)
    except OSError as error:
        if error.errno == errno.EADDRINUSE:
            existing = probe_existing_viewer(args.port)
            if existing is not None:
                return reuse_existing_viewer(existing, args.port, requested_task=args.task,
                                             requested_pickup=args.pickup)
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
