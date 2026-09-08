#!/usr/bin/env python3
"""Replay a Mirobot demo on the real robot and a live MuJoCo sim together.

This does not play saved camera frames. For every command sent to the real
robot, it applies the same Cartesian target to the MuJoCo Mirobot through IK and
serves the live render in a browser.

Run with the repo venv because MuJoCo is installed there:

    cosmos-policy_tj/.venv/bin/python mirobot_control/replay_demo_network_with_mujoco.py \
      --bridge-host <LAPTOP_IP> --demo 0 --execute

Open the viewer in a browser:

    http://<ssh-server-ip>:8888
"""

from __future__ import annotations

import argparse
import io
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

os.environ.setdefault("MUJOCO_GL", "egl")

ROOT = Path(__file__).resolve().parents[1]
COSMOS_ROOT = ROOT / "cosmos-policy_tj"
if str(COSMOS_ROOT) not in sys.path:
    sys.path.insert(0, str(COSMOS_ROOT))

import mujoco
import numpy as np
import h5py
from PIL import Image, ImageDraw

from cosmos_policy.experiments.robot.mirobot import MirobotCosmosEnv
from cosmos_policy.experiments.robot.mirobot.paths import WRIST_UNDER_V1_XML_PATH
from replay_all_demos_network import BridgeClient, run_home, send_gcode
from replay_all_demos_standalone import (
    DEFAULT_Z_OFFSET_MM,
    DEMOS,
    TASK_INSTRUCTION,
    gripper_gcode,
    parse_demo_selection,
    state_to_gcode,
)


OBJECT_JOINT = "task_object_freejoint"
OBJECT_SITE = "task_object_site"
TARGET_PAD = "task_target_pad"
TARGET_SITE = "task_target_site"
GRIP_SITE = "grip_site"
OBJECT_Z = 0.057
TARGET_Z = 0.052
DEFAULT_HDF5_PATH = (
    COSMOS_ROOT
    / "artifacts/mirobot/datasets/active/wrist_under_v1_pick_place/"
    / "pick_up_the_red_cube_and_place_it_on_the_green_target_SCENE1_demos.hdf5"
)


class ViewerState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.jpeg = self._placeholder("waiting for MuJoCo replay")
        self.step_text = "waiting"

    def _placeholder(self, text: str) -> bytes:
        image = Image.new("RGB", (1024, 512), (28, 28, 28))
        draw = ImageDraw.Draw(image)
        draw.text((24, 24), text, fill=(240, 240, 240))
        return self._encode(image)

    def _encode(self, image: Image.Image) -> bytes:
        out = io.BytesIO()
        image.save(out, format="JPEG", quality=88)
        return out.getvalue()

    def update(self, jpeg: bytes, step_text: str) -> None:
        with self.lock:
            self.jpeg = jpeg
            self.step_text = step_text

    def snapshot(self) -> tuple[bytes, str]:
        with self.lock:
            return self.jpeg, self.step_text


def _camera_snapshot_url(camera_url: str) -> str:
    if camera_url.endswith("/video"):
        return camera_url[: -len("/video")] + "/snapshot.jpg"
    return camera_url


def _probe_camera(camera_url: str, timeout: float) -> bool:
    try:
        parts = urlsplit(camera_url)
        if not parts.hostname:
            return False
        port = parts.port
        if port is None:
            port = 443 if parts.scheme == "https" else 80
        with socket.create_connection((parts.hostname, port), timeout=timeout):
            return True
    except OSError:
        return False


class LatestCameraFeed:
    def __init__(
        self,
        name: str,
        snapshot_url: str,
        timeout: float,
        poll_fps: float,
        retry_on_error: bool,
        placeholder_fn,
    ) -> None:
        self.name = name
        self.snapshot_url = snapshot_url
        self.timeout = timeout
        self.interval = 1.0 / max(poll_fps, 0.1)
        self.retry_on_error = retry_on_error
        self.placeholder_fn = placeholder_fn
        self.lock = threading.Lock()
        self.latest_jpeg = placeholder_fn(f"{name} waiting")
        self.latest_time = 0.0
        self.status = "starting"
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        self.thread = threading.Thread(target=self._loop, name=f"{self.name}-latest-camera", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=1.0)

    def snapshot(self) -> tuple[bytes, str, float]:
        with self.lock:
            return self.latest_jpeg, self.status, self.latest_time

    def _loop(self) -> None:
        while not self.stop_event.is_set():
            start = time.monotonic()
            try:
                with urllib.request.urlopen(self.snapshot_url, timeout=self.timeout) as response:
                    jpeg = response.read()
                with self.lock:
                    self.latest_jpeg = jpeg
                    self.latest_time = time.time()
                    self.status = "live"
            except (OSError, urllib.error.URLError, TimeoutError) as exc:
                with self.lock:
                    self.latest_time = time.time()
                    self.status = f"error: {exc}"
                if not self.retry_on_error:
                    break

            elapsed = time.monotonic() - start
            self.stop_event.wait(max(0.0, self.interval - elapsed))


def make_handler(
    state: ViewerState,
    camera_feeds: list[LatestCameraFeed],
    camera_display_fps: float,
    sim_display_fps: float,
):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args) -> None:
            return

        def do_GET(self) -> None:
            if self.path.startswith("/frame.jpg"):
                jpeg, step_text = state.snapshot()
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Step", step_text)
                self.send_header("Content-Length", str(len(jpeg)))
                self.end_headers()
                self.wfile.write(jpeg)
                return

            if self.path.startswith("/sim_stream"):
                self._sim_stream()
                return

            if self.path.startswith("/camera_stream/"):
                self._camera_stream()
                return

            camera_panels = []
            for index, feed in enumerate(camera_feeds):
                _, status, latest_time = feed.snapshot()
                if latest_time:
                    age = max(0.0, time.time() - latest_time)
                    label = f"{feed.name} | {status} | {age:.2f}s"
                else:
                    label = f"{feed.name} | {status}"
                camera_panels.append(
                    f'<div class="panel"><span class="label">{label}</span>'
                    f'<img src="/camera_stream/{index}"></div>'
                )
            html = """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Mirobot MuJoCo Live</title>
  <style>
    body { margin: 0; background: #111; color: #eee; font-family: system-ui, sans-serif; }
    main { height: 100vh; display: grid; grid-template-rows: auto minmax(280px, 50vh) minmax(220px, 1fr); }
    header { padding: 10px 14px; background: #1c1c1c; font-size: 14px; }
    img { width: 100%; height: 100%; object-fit: contain; background: #080808; }
    .sim { min-height: 0; max-height: 50vh; }
    .cameras { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1px; background: #333; min-height: 0; }
    .panel { position: relative; min-width: 0; min-height: 0; background: #090909; }
    .label {
      position: absolute; left: 10px; top: 8px; padding: 4px 7px;
      border-radius: 4px; background: rgba(0, 0, 0, 0.65); font-size: 13px;
    }
  </style>
</head>
<body>
<main>
  <header>Mirobot live MuJoCo simulation</header>
  <img class="sim" src="/sim_stream">
  <section class="cameras">
    __CAMERA_PANELS__
  </section>
</main>
</body>
</html>""".replace("__CAMERA_PANELS__", "".join(camera_panels)).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)

        def _sim_stream(self) -> None:
            try:
                self.send_response(200)
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                interval = 1.0 / max(sim_display_fps, 0.1)
                last_jpeg = None
                while True:
                    jpeg, step_text = state.snapshot()
                    if jpeg != last_jpeg:
                        last_jpeg = jpeg
                        self.wfile.write(b"--frame\r\n")
                        self.wfile.write(b"Content-Type: image/jpeg\r\n")
                        self.wfile.write(f"X-Step: {step_text}\r\n".encode("utf-8"))
                        self.wfile.write(f"Content-Length: {len(jpeg)}\r\n\r\n".encode("ascii"))
                        self.wfile.write(jpeg)
                        self.wfile.write(b"\r\n")
                    time.sleep(interval)
            except (BrokenPipeError, ConnectionResetError):
                return

        def _camera_stream(self) -> None:
            try:
                index_part = self.path.split("/camera_stream/", 1)[1].split(".", 1)[0].split("?", 1)[0]
                camera_index = int(index_part)
            except (IndexError, ValueError):
                self._send_placeholder("invalid camera index")
                return

            if camera_index < 0 or camera_index >= len(camera_feeds):
                self._send_placeholder(f"camera {camera_index} not configured")
                return

            try:
                self.send_response(200)
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                feed = camera_feeds[camera_index]
                interval = 1.0 / max(camera_display_fps, 0.1)
                while not feed.stop_event.is_set():
                    jpeg, _, _ = feed.snapshot()
                    self.wfile.write(b"--frame\r\n")
                    self.wfile.write(b"Content-Type: image/jpeg\r\n")
                    self.wfile.write(f"Content-Length: {len(jpeg)}\r\n\r\n".encode("ascii"))
                    self.wfile.write(jpeg)
                    self.wfile.write(b"\r\n")
                    time.sleep(interval)
            except (BrokenPipeError, ConnectionResetError):
                return

        def _send_placeholder(self, text: str) -> None:
            jpeg = state._placeholder(text)
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(jpeg)))
            self.end_headers()
            self.wfile.write(jpeg)

    return Handler


def start_viewer(
    host: str,
    port: int,
    state: ViewerState,
    camera_feeds: list[LatestCameraFeed],
    camera_display_fps: float,
    sim_display_fps: float,
) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), make_handler(state, camera_feeds, camera_display_fps, sim_display_fps))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def get_site_pos(env: MirobotCosmosEnv, name: str) -> np.ndarray:
    site_id = mujoco.mj_name2id(env.model, mujoco.mjtObj.mjOBJ_SITE, name)
    if site_id < 0:
        raise ValueError(f"Site not found: {name}")
    return env.data.site_xpos[site_id].copy()


def set_object_pose(env: MirobotCosmosEnv, pos: np.ndarray, quat: np.ndarray | None = None) -> None:
    joint_id = mujoco.mj_name2id(env.model, mujoco.mjtObj.mjOBJ_JOINT, OBJECT_JOINT)
    if joint_id < 0:
        return
    qpos_idx = env.model.jnt_qposadr[joint_id]
    dof_idx = env.model.jnt_dofadr[joint_id]
    env.data.qpos[qpos_idx : qpos_idx + 3] = pos
    env.data.qpos[qpos_idx + 3 : qpos_idx + 7] = quat if quat is not None else np.array([1.0, 0.0, 0.0, 0.0])
    env.data.qvel[dof_idx : dof_idx + 6] = 0.0
    mujoco.mj_forward(env.model, env.data)


def set_target_pose(env: MirobotCosmosEnv, pos: np.ndarray) -> None:
    site_id = mujoco.mj_name2id(env.model, mujoco.mjtObj.mjOBJ_SITE, TARGET_SITE)
    geom_id = mujoco.mj_name2id(env.model, mujoco.mjtObj.mjOBJ_GEOM, TARGET_PAD)
    if site_id >= 0:
        env.model.site_pos[site_id] = pos
    if geom_id >= 0:
        env.model.geom_pos[geom_id] = np.array([pos[0], pos[1], pos[2] - 0.0085], dtype=np.float64)
    mujoco.mj_forward(env.model, env.data)


def infer_task_layout(states: list[list[float]], actions: list[list[float]]) -> tuple[np.ndarray, np.ndarray]:
    gripper = np.array([float(action[6]) for action in actions], dtype=np.float64)
    state_arr = np.array(states, dtype=np.float64)

    close_candidates = np.where((gripper[:-1] < 0.0) & (gripper[1:] > 0.0))[0]
    release_candidates = np.where((gripper[:-1] > 0.0) & (gripper[1:] < 0.0))[0]

    if len(close_candidates) == 0:
        close_idx = int(np.argmin(state_arr[:, 4]))
    else:
        close_idx = int(close_candidates[0] + 1)

    if len(release_candidates) == 0:
        release_idx = len(states) - 1
    else:
        release_idx = int(release_candidates[-1] + 1)

    object_pos = np.array([state_arr[close_idx, 2], state_arr[close_idx, 3], OBJECT_Z], dtype=np.float64)
    target_pos = np.array([state_arr[release_idx, 2], state_arr[release_idx, 3], TARGET_Z], dtype=np.float64)
    return object_pos, target_pos


def parse_demo_selection_for_count(selection: str, count: int) -> list[int]:
    if selection == "all":
        return list(range(count))

    selected: list[int] = []
    for part in selection.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_s, end_s = part.split("-", 1)
            start = int(start_s)
            end = int(end_s)
            if end < start:
                raise ValueError(f"Invalid demo range: {part}")
            selected.extend(range(start, end + 1))
        else:
            selected.append(int(part))

    missing = [idx for idx in selected if idx < 0 or idx >= count]
    if missing:
        raise ValueError(f"Missing demos in HDF5: {missing}. Available range: 0-{count - 1}")
    return selected


def load_demo_from_hdf5(hdf5_file: h5py.File, demo_idx: int) -> tuple[list[list[float]], list[list[float]]]:
    group = hdf5_file["data"][f"demo_{demo_idx}"]
    actions = group["actions"][()].astype(float).tolist()
    states = group["robot_states"][()].astype(float).tolist()
    return actions, states


def set_demo_task_layout(env: MirobotCosmosEnv, demo_idx: int, states: list[list[float]], actions: list[list[float]]) -> None:
    object_pos, target_pos = infer_task_layout(states, actions)
    set_object_pose(env, object_pos)
    set_target_pose(env, target_pos)
    print(
        f"demo_{demo_idx} layout: "
        f"object=({object_pos[0]:.4f}, {object_pos[1]:.4f}, {object_pos[2]:.4f}), "
        f"target=({target_pos[0]:.4f}, {target_pos[1]:.4f}, {target_pos[2]:.4f})"
    )


def render_side_by_side(env: MirobotCosmosEnv, demo_idx: int, step_idx: int, target_pos: np.ndarray) -> bytes:
    primary = env.render(env.primary_camera)
    wrist = env.render(env.wrist_camera)
    left = Image.fromarray(primary).convert("RGB")
    right = Image.fromarray(wrist).convert("RGB")
    if left.size != right.size:
        right = right.resize(left.size)

    label_h = 34
    combined = Image.new("RGB", (left.width + right.width, left.height + label_h), (18, 18, 18))
    combined.paste(left, (0, label_h))
    combined.paste(right, (left.width, label_h))
    draw = ImageDraw.Draw(combined)
    draw.text(
        (10, 9),
        f"demo_{demo_idx} step {step_idx:04d} | MuJoCo target "
        f"({target_pos[0]:.3f}, {target_pos[1]:.3f}, {target_pos[2]:.3f})",
        fill=(245, 245, 245),
    )
    draw.text((left.width + 10, 9), "wrist_camera", fill=(245, 245, 245))

    out = io.BytesIO()
    combined.save(out, format="JPEG", quality=90)
    return out.getvalue()


def apply_command_to_mujoco(
    env: MirobotCosmosEnv,
    target_pos: np.ndarray,
    target_quat: np.ndarray,
    gripper_action: float,
    attached_offset: np.ndarray | None,
    use_assisted_object: bool,
) -> np.ndarray | None:
    env._solve_ik(target_pos, target_quat)  # noqa: SLF001 - this script is an integration tool.
    env._apply_gripper_action(gripper_action)  # noqa: SLF001
    mujoco.mj_forward(env.model, env.data)

    offset = attached_offset
    if use_assisted_object:
        if gripper_action > 0.0 and offset is None:
            object_pos = get_site_pos(env, OBJECT_SITE)
            grip_pos = get_site_pos(env, GRIP_SITE)
            if np.linalg.norm(object_pos - grip_pos) < 0.075:
                offset = object_pos - grip_pos
        if gripper_action < 0.0:
            offset = None
        if offset is not None:
            set_object_pose(env, get_site_pos(env, GRIP_SITE) + offset)

    mujoco.mj_forward(env.model, env.data)
    return offset


def replay_demo_with_mujoco(
    client: BridgeClient | None,
    env: MirobotCosmosEnv,
    demo_idx: int,
    args,
    viewer_state: ViewerState,
    dry_run: bool,
    hdf5_file: h5py.File | None,
    stop_event: threading.Event | None = None,
) -> None:
    if hdf5_file is None:
        demo = DEMOS[str(demo_idx)]
        actions = demo["actions"]
        states = demo["states"]
    else:
        actions, states = load_demo_from_hdf5(hdf5_file, demo_idx)

    indices = list(range(0, len(states), args.stride))
    if args.max_steps > 0:
        indices = indices[: args.max_steps]

    print(f"===== demo_{demo_idx} | states={len(states)} | replayed={len(indices)} =====")
    set_demo_task_layout(env, demo_idx, states, actions)
    attached_offset = None
    last_gripper = None

    for step_idx in indices:
        if stop_event is not None and stop_event.is_set():
            print(f"===== demo_{demo_idx} stopped before step {step_idx:04d} =====")
            break

        robot_state = states[step_idx]
        action = actions[step_idx]
        command = state_to_gcode(
            robot_state,
            args.x_offset_mm,
            args.y_offset_mm,
            args.z_offset_mm,
            args.a_deg,
            args.b_deg,
            args.c_deg,
        )
        target_pos = np.array(robot_state[2:5], dtype=np.float64)
        target_quat = np.array(robot_state[5:9], dtype=np.float64)
        target_quat /= max(np.linalg.norm(target_quat), 1e-8)

        print(f"[demo_{demo_idx} step {step_idx:04d}]")
        send_gcode(client, command, dry_run)

        grip_cmd = gripper_gcode(action, args.open_cmd, args.close_cmd)
        if grip_cmd != last_gripper:
            send_gcode(client, grip_cmd, dry_run)
            last_gripper = grip_cmd

        attached_offset = apply_command_to_mujoco(
            env,
            target_pos,
            target_quat,
            float(action[6]),
            attached_offset,
            args.assisted_object,
        )
        viewer_state.update(
            render_side_by_side(env, demo_idx, step_idx, target_pos),
            f"demo_{demo_idx} step {step_idx:04d} | command: {command}",
        )

        if args.period > 0:
            time.sleep(args.period)


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay real Mirobot commands and live MuJoCo simulation together.")
    parser.add_argument("--demo", default="0", help="Demo index, range like 0-9, or all. Default: 0")
    parser.add_argument(
        "--hdf5-path",
        type=Path,
        default=None,
        help="Optional dataset HDF5. If set, demos are loaded from this file instead of embedded demos.",
    )
    parser.add_argument("--xml-path", type=Path, default=WRIST_UNDER_V1_XML_PATH)
    parser.add_argument("--image-size", type=int, default=256)
    parser.add_argument("--viewer-host", default="0.0.0.0")
    parser.add_argument("--viewer-port", type=int, default=8888)
    parser.add_argument(
        "--camera-url",
        action="append",
        default=None,
        help=(
            "Camera snapshot URL to show under the MuJoCo viewer. "
            "Can be passed twice. Defaults to bridge-host ports 8890 and 8891."
        ),
    )
    parser.add_argument("--camera-timeout", type=float, default=3.0)
    parser.add_argument("--camera-cache-fps", type=float, default=10.0)
    parser.add_argument("--camera-display-fps", type=float, default=8.0)
    parser.add_argument("--sim-display-fps", type=float, default=10.0)
    parser.add_argument(
        "--camera-retry-on-error",
        action="store_true",
        help="Keep reconnecting to camera snapshot URLs after an error. Default is connect during this run only.",
    )
    parser.add_argument("--bridge-host", default="127.0.0.1")
    parser.add_argument("--bridge-port", type=int, default=8765)
    parser.add_argument("--bridge-timeout", type=float, default=20.0)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--skip-home", action="store_true")
    parser.add_argument("--home-each-demo", action="store_true", help="Home before every selected demo.")
    parser.add_argument("--between-demo-pause", type=float, default=1.0)
    parser.add_argument("--start-pause", type=float, default=5.0)
    parser.add_argument("--hold-viewer-after", type=float, default=10.0)
    parser.add_argument("--period", type=float, default=0.20)
    parser.add_argument("--repeat-count", type=int, default=1, help="How many times to replay the selected demo set.")
    parser.add_argument("--max-steps", type=int, default=0)
    parser.add_argument("--stride", type=int, default=1)
    parser.add_argument("--x-offset-mm", type=float, default=0.0)
    parser.add_argument("--y-offset-mm", type=float, default=0.0)
    parser.add_argument("--z-offset-mm", type=float, default=DEFAULT_Z_OFFSET_MM)
    parser.add_argument("--a-deg", type=float, default=0.0)
    parser.add_argument("--b-deg", type=float, default=0.0)
    parser.add_argument("--c-deg", type=float, default=0.0)
    parser.add_argument("--open-cmd", default="M4 S40")
    parser.add_argument("--close-cmd", default="M4 S60")
    parser.add_argument("--assisted-object", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args()

    hdf5_file = None
    if args.hdf5_path is not None:
        hdf5_file = h5py.File(args.hdf5_path, "r")
        demo_count = len(hdf5_file["data"].keys())
        try:
            selected = parse_demo_selection_for_count(args.demo, demo_count)
        except ValueError as exc:
            hdf5_file.close()
            parser.error(str(exc))
    else:
        try:
            selected = parse_demo_selection(args.demo)
        except ValueError as exc:
            parser.error(str(exc))
    if args.stride < 1:
        parser.error("--stride must be >= 1")
    if args.repeat_count < 1:
        parser.error("--repeat-count must be >= 1")
    if min(args.period, args.start_pause, args.hold_viewer_after, args.between_demo_pause) < 0:
        parser.error("--period, --start-pause, --hold-viewer-after, and --between-demo-pause must be >= 0")

    dry_run = not args.execute
    viewer_state = ViewerState()
    camera_urls = args.camera_url or [
        f"http://{args.bridge_host}:8890/snapshot.jpg",
        f"http://{args.bridge_host}:8891/snapshot.jpg",
    ]
    camera_feeds = []
    for index, camera_url in enumerate(camera_urls[:2]):
        snapshot_url = _camera_snapshot_url(camera_url)
        available = _probe_camera(snapshot_url, min(args.camera_timeout, 1.0))
        feed = LatestCameraFeed(
            name=f"camera {index}",
            snapshot_url=snapshot_url,
            timeout=args.camera_timeout,
            poll_fps=args.camera_cache_fps if available else 0.2,
            retry_on_error=args.camera_retry_on_error,
            placeholder_fn=viewer_state._placeholder,  # noqa: SLF001 - local viewer helper.
        )
        if not available:
            feed.status = "unavailable"
        feed.start()
        camera_feeds.append(feed)
    viewer = start_viewer(
        args.viewer_host,
        args.viewer_port,
        viewer_state,
        camera_feeds,
        args.camera_display_fps,
        args.sim_display_fps,
    )
    env = MirobotCosmosEnv(xml_path=args.xml_path, image_size=args.image_size, action_mode="ik_delta")

    print(f"instruction: {TASK_INSTRUCTION}")
    print(f"selected demos: {selected}")
    print(f"repeat count: {args.repeat_count}")
    if args.hdf5_path is not None:
        print(f"hdf5: {args.hdf5_path}")
    print(f"mode: {'EXECUTE' if args.execute else 'DRY-RUN'}")
    print(f"bridge: {args.bridge_host}:{args.bridge_port}")
    print(f"viewer: http://{args.viewer_host}:{args.viewer_port}")
    print(f"camera snapshot urls: {[feed.snapshot_url for feed in camera_feeds]}")
    print(f"camera cache fps: {args.camera_cache_fps}, display fps: {args.camera_display_fps}")
    print(f"camera retry on error: {args.camera_retry_on_error}")
    print(f"xml: {args.xml_path}")
    print("This viewer is live MuJoCo IK from the same G-code targets, not saved frames.")

    client = None
    if args.execute:
        client = BridgeClient(args.bridge_host, args.bridge_port, args.bridge_timeout)
        client.connect()

    try:
        if args.start_pause > 0:
            print(f"starting in {args.start_pause:.1f}s; open the viewer now")
            time.sleep(args.start_pause)
        if not args.skip_home and not args.home_each_demo:
            run_home(client, dry_run)
        total_runs = len(selected) * args.repeat_count
        run_index = 0
        for repeat_idx in range(args.repeat_count):
            if args.repeat_count > 1:
                print(f"===== repeat {repeat_idx + 1}/{args.repeat_count} =====")
            for i, demo_idx in enumerate(selected):
                run_index += 1
                print(f"===== run {run_index}/{total_runs} =====")
                if args.home_each_demo and not args.skip_home:
                    print(f"===== homing before demo_{demo_idx} =====")
                    run_home(client, dry_run)
                env.reset()
                replay_demo_with_mujoco(client, env, demo_idx, args, viewer_state, dry_run, hdf5_file)
                is_last_run = repeat_idx == args.repeat_count - 1 and i == len(selected) - 1
                if not is_last_run and args.between_demo_pause > 0:
                    time.sleep(args.between_demo_pause)
        if args.hold_viewer_after > 0:
            print(f"holding viewer for {args.hold_viewer_after:.1f}s")
            time.sleep(args.hold_viewer_after)
    finally:
        if client is not None:
            client.close()
            print("bridge connection closed")
        env.close()
        if hdf5_file is not None:
            hdf5_file.close()
        for feed in camera_feeds:
            feed.stop()
        viewer.shutdown()
        viewer.server_close()
        print("viewer closed")


if __name__ == "__main__":
    main()
