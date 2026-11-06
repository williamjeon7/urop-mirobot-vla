"""Lossless D405 + Cartesian-state HTTP bridge for a trained Mirobot policy.

Run on the robot PC. Startup opens the devices and only queries status: it never
homes, changes mode, opens the gripper, or moves the arm. Commands require
``--execute``. Images are raw RGB encoded losslessly as PNG; all training colour
correction, rotation and cropping belong on the inference server.
"""
from __future__ import annotations

import argparse
import base64
from collections import OrderedDict, deque
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import io
import json
import math
import os
from pathlib import Path
import re
import threading
import time

from tools.probe_mirobot import fields, find_field, is_error, is_ok, is_status, state_of
from tools.run_gcode import ANGLE_WARN_DEG, REACH_WARN_MM, Z_FLOOR_MM
from common.workspace import MIROBOT_CARTESIAN_LIMITS_MM

PROTOCOL = "mirobot-policy/1"
DEFAULT_POLICY_PORT = 8891
DEFAULT_COLOR_PROFILE = Path(__file__).resolve().parents[1]/"Mirobot_data/W10/L01_red/color_profile.json"
NUMBER = r"-?(?:\d+(?:\.\d*)?|\.\d+)"
MOVE = re.compile(r"G0\s+" + r"\s+".join(axis + "(" + NUMBER + ")" for axis in "XYZABC"), re.I)
GRIPPER = re.compile(r"M4\s+S(" + NUMBER + ")", re.I)


def positive(value: float, name: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return value


def cartesian_status(line: str) -> dict:
    """Parse the six Cartesian values, never the seven joint-angle values."""
    cart = find_field(fields(line), "Cartesian")
    if cart is None or len(cart) < 6 or not all(math.isfinite(v) for v in cart[:6]):
        raise ValueError(f"Expected six finite Cartesian values: {line}")
    return {"cart6": cart[:6], "state": state_of(line), "raw": line}


@dataclass(frozen=True)
class CommandLimits:
    z_floor_mm: float = MIROBOT_CARTESIAN_LIMITS_MM[2][0]
    max_step_mm: float = 25.0
    max_rotation_deg: float = 20.0
    open_s: float = 40.0
    closed_s: float = 60.0
    max_radius_mm: float = REACH_WARN_MM
    max_angle_deg: float = ANGLE_WARN_DEG
    x_min_mm: float = MIROBOT_CARTESIAN_LIMITS_MM[0][0]
    x_max_mm: float = MIROBOT_CARTESIAN_LIMITS_MM[0][1]
    y_min_mm: float = MIROBOT_CARTESIAN_LIMITS_MM[1][0]
    y_max_mm: float = MIROBOT_CARTESIAN_LIMITS_MM[1][1]
    z_max_mm: float = MIROBOT_CARTESIAN_LIMITS_MM[2][1]

    def validate(self, command: str, current: list[float]) -> tuple[str, list[float] | None, float | None]:
        if not isinstance(command, str) or "\n" in command or "\r" in command:
            raise ValueError("Exactly one G-code command is required")
        command = command.strip().upper()
        if command in ("G90", "M20"):
            return command, None, None
        match = MOVE.fullmatch(command)
        if match:
            target = [float(v) for v in match.groups()]
            if not all(math.isfinite(v) for v in target):
                raise ValueError("Non-finite Cartesian command")
            for axis, value, low, high in (
                ("X", target[0], self.x_min_mm, self.x_max_mm),
                ("Y", target[1], self.y_min_mm, self.y_max_mm),
                ("Z", target[2], self.z_floor_mm, self.z_max_mm),
            ):
                if not low <= value <= high:
                    raise ValueError(f"Target {axis} {value:.2f} mm outside measured limits [{low:.2f}, {high:.2f}]")
            if math.hypot(*target[:2]) > self.max_radius_mm:
                raise ValueError(f"Target is outside horizontal radius {self.max_radius_mm:g} mm")
            if max(abs(v) for v in target[3:]) > self.max_angle_deg:
                raise ValueError(f"Target exceeds absolute angle limit {self.max_angle_deg:g} deg")
            distance = math.dist(target[:3], current[:3])
            rotation = max(abs((a-b+180) % 360-180) for a, b in zip(target[3:], current[3:]))
            if distance > self.max_step_mm or rotation > self.max_rotation_deg:
                raise ValueError(f"Move exceeds step limits: {distance:.2f} mm, {rotation:.2f} deg")
            return command, target, None
        match = GRIPPER.fullmatch(command)
        if match:
            value = float(match.group(1))
            if not math.isfinite(value) or not min(self.open_s, self.closed_s) <= value <= max(self.open_s, self.closed_s):
                raise ValueError("Gripper command outside calibrated open/closed endpoints")
            return command, None, value
        raise ValueError("Only full absolute G0 XYZABC, calibrated M4 S, G90 and M20 are accepted")


def lock_camera_options(sensors, rs, color_profile):
    """Use the same sensor controls and tolerances as W9's capture.py."""
    expected = color_profile["camera_options"]
    locked = {}
    for sensor in sensors:
        for auto, value in ((rs.option.enable_auto_exposure, rs.option.exposure),
                            (rs.option.enable_auto_white_balance, rs.option.white_balance)):
            if sensor.supports(auto) and sensor.supports(value):
                sensor.set_option(auto, 0)
                sensor.set_option(value, expected.get(str(value), sensor.get_option(value)))
                locked[str(value)] = sensor.get_option(value)
        for option in (rs.option.gain, rs.option.gamma, rs.option.saturation,
                       rs.option.brightness, rs.option.contrast, rs.option.hue, rs.option.sharpness):
            if sensor.supports(option):
                if str(option) in expected:
                    sensor.set_option(option, expected[str(option)])
                locked[str(option)] = sensor.get_option(option)
    for key, value in expected.items():
        if key not in locked or abs(locked[key]-value) > max(1, abs(value)*.001):
            raise ValueError(f"Cannot reproduce colour-profile camera setting {key}")
    return locked


class D405Camera:
    """One capture thread; bounded waits and host-receipt timestamps."""

    def __init__(self, serial_number=None, width=640, height=480, fps=30, color_profile=DEFAULT_COLOR_PROFILE,
                 video_path=None, video_dir=None):
        from docs.W9.d405.color_calibration import load_profile
        self.profile = load_profile(color_profile)
        self.requested_serial = serial_number or self.profile["camera_serial"]
        if (self.requested_serial != self.profile["camera_serial"] or
                (width, height, fps) != tuple(self.profile[k] for k in ("width", "height", "fps"))):
            raise ValueError("Requested camera serial/resolution/fps differs from colour profile")
        self.metadata = {"width": width, "height": height, "fps": fps, "encoding": "png",
                         "color_order": "RGB", "preprocessing": "none", "timestamp_basis": "host receipt"}
        self.condition = threading.Condition()
        self.frames = deque(maxlen=12)
        self.stop_event = threading.Event()
        self.error = "Camera starting"
        self.thread = None
        from robot.policy_video import PolicyVideo
        self.video = PolicyVideo(video_path, width, height, fps) if video_path is not None else None
        self.video_dir = Path(video_dir) if video_dir is not None else None
        self.recording_lock = threading.Lock()

    def start(self):
        self.thread = threading.Thread(target=self._run, name="d405-policy", daemon=True)
        self.thread.start()
        deadline = time.monotonic() + 10
        with self.condition:
            while not self.frames and self.thread.is_alive() and time.monotonic() < deadline:
                self.condition.wait(min(.1, max(0, deadline-time.monotonic())))
            if not self.frames:
                raise RuntimeError(self.error)

    def _run(self):
        pipe = None
        try:
            import cv2
            import numpy as np
            import pyrealsense2 as rs

            candidates = [d for d in rs.context().query_devices()
                          if "D405" in d.get_info(rs.camera_info.name)
                          and (not self.requested_serial or d.get_info(rs.camera_info.serial_number) == self.requested_serial)]
            if len(candidates) != 1:
                raise RuntimeError(f"Expected one D405, found {len(candidates)}; use --camera-serial")
            serial_number = candidates[0].get_info(rs.camera_info.serial_number)
            self.metadata.update(serial=serial_number, name=candidates[0].get_info(rs.camera_info.name))
            pipe, config = rs.pipeline(), rs.config()
            config.enable_device(serial_number)
            config.enable_stream(rs.stream.color, self.metadata["width"], self.metadata["height"],
                                 rs.format.rgb8, self.metadata["fps"])
            active_profile = pipe.start(config)
            for _ in range(15):
                pipe.wait_for_frames(2000)
            self.metadata["locked_camera_options"] = lock_camera_options(active_profile.get_device().query_sensors(), rs, self.profile)
            count = 0
            while not self.stop_event.is_set():
                frame = pipe.wait_for_frames(2000).get_color_frame()
                received = time.monotonic()
                if not frame:
                    continue
                count += 1
                if count <= 15:
                    continue  # let the camera's exposure settle before supplying observations
                rgb = np.asanyarray(frame.get_data())
                bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
                if self.video is not None:
                    self.video.write(bgr, received, int(frame.get_frame_number()), float(frame.get_timestamp()))
                ok, encoded = cv2.imencode(".png", bgr)
                if not ok:
                    raise RuntimeError("Could not encode D405 RGB frame")
                item = {"frame_monotonic_s": received, "frame_number": int(frame.get_frame_number()),
                        "device_ms": float(frame.get_timestamp()), "png": encoded.tobytes()}
                with self.condition:
                    self.frames.append(item)
                    self.error = ""
                    self.condition.notify_all()
        except Exception as exc:
            with self.condition:
                self.error = str(exc)
                self.condition.notify_all()
        finally:
            try:
                if self.video is not None:
                    self.video.stop()
            finally:
                if pipe is not None:
                    try:
                        pipe.stop()
                    except RuntimeError:
                        pass

    def snapshot(self, state_monotonic_s: float, max_age_s=.5, max_skew_s=.15) -> dict:
        with self.condition:
            if self.error or not self.frames:
                raise RuntimeError(self.error or "No camera frame")
            item = min(self.frames, key=lambda x: abs(x["frame_monotonic_s"]-state_monotonic_s)).copy()
        now = time.monotonic()
        age, skew = now-item["frame_monotonic_s"], item["frame_monotonic_s"]-state_monotonic_s
        if age > max_age_s or abs(skew) > max_skew_s:
            raise RuntimeError(f"Camera frame is stale or unsynchronized: age={age:.3f}s, skew={skew:.3f}s")
        item["image_rgb_png_base64"] = base64.b64encode(item.pop("png")).decode("ascii")
        return {**item, "frame_age_s": age, "frame_state_skew_s": skew, "camera": self.metadata.copy()}

    def close(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=3)
        if self.video is not None:
            self.video.stop()

    def start_recording(self, run_name=None):
        from robot.policy_video import PolicyVideo
        with self.recording_lock:
            if self.video_dir is not None:
                if not isinstance(run_name, str) or re.fullmatch(r"I[1-9][0-9]*", run_name) is None:
                    raise ValueError("Recording name must be I1, I2, ...")
                if self.video is not None and self.video.writer is not None:
                    raise RuntimeError("A recording is already active")
                path = self.video_dir / run_name / f"{run_name}.mp4"
                self.video = PolicyVideo(path, self.metadata["width"], self.metadata["height"], self.metadata["fps"])
            return self._start_recording()

    def recording_names(self):
        if self.video_dir is None or not self.video_dir.exists():
            return []
        return sorted(path.name for path in self.video_dir.iterdir()
                      if re.fullmatch(r"I[1-9][0-9]*", path.name))

    def _start_recording(self):
        if self.video is None:
            raise RuntimeError("Bridge recording is not configured; start with --video-out")
        if self.error:
            raise RuntimeError(self.error)
        return self.video.start()

    def stop_recording(self):
        if self.video is None:
            raise RuntimeError("Bridge recording is not configured; start with --video-out")
        return self.video.stop()

    def recording_file(self, name, kind):
        if (self.video is None or self.video.path.stem != name or
                self.video.writer is not None or not self.video.result):
            raise RuntimeError("Requested recording is not finalized")
        suffix = {"video": ".mp4", "frames": "_frames.jsonl", "metadata": "_video.json"}[kind]
        return self.video.path.with_name(name + suffix)


class RobotIO:
    def __init__(self, ser, *, execute=False, limits=None, timeout_s=30.0,
                 gripper_seconds=1.0, initial_s=40.0):
        self.ser = ser
        self.execute = execute
        self.limits = limits or CommandLimits()
        for name in ("z_floor_mm", "max_step_mm", "max_rotation_deg", "max_radius_mm", "max_angle_deg"):
            positive(getattr(self.limits, name), name)
        if (not all(math.isfinite(v) for v in (self.limits.open_s, self.limits.closed_s, initial_s))
                or self.limits.open_s == self.limits.closed_s
                or not min(self.limits.open_s, self.limits.closed_s) <= initial_s <= max(self.limits.open_s, self.limits.closed_s)):
            raise ValueError("Distinct finite gripper endpoints and an initial S between them are required")
        self.timeout_s = positive(timeout_s, "timeout_s")
        self.gripper_seconds = positive(gripper_seconds, "gripper_seconds")
        self.lock = threading.Lock()
        self.fault = ""
        self.completed = OrderedDict()
        self.pending = b""
        self.gripper_s = initial_s
        self.gripper_start = -math.inf
        self.gripper_from = self._closure(initial_s)
        self.absolute_mode = False  # explicitly establish G90 before accepting any G0
        self.preparations = OrderedDict()

    def prepare(self, request_id):
        from robot.policy_setup import prepare_with_probe
        from tools.probe_mirobot import Probe
        if not self.execute:
            raise PermissionError("Bridge is read-only; preparation requires --execute")
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 128:
            raise ValueError("A preparation request_id is required")
        with self.lock:
            if request_id in self.preparations:
                return self.preparations[request_id]
            if self.fault:
                raise RuntimeError(f"Restart bridge after checking the arm: {self.fault}")
            probe = Probe.__new__(Probe)
            probe.ser, probe.log_file = self.ser, io.StringIO()
            try:
                prepare_with_probe(probe)
                self.pending = b""
                self.gripper_s = 40.0
                self.gripper_start = -math.inf
                self.gripper_from = self._closure(40.0)
                self.absolute_mode = True
                result = dict(ok=True, prepared=True, request_id=request_id, **self._status(),
                              events=[json.loads(line) for line in probe.log_file.getvalue().splitlines()])
                self.preparations[request_id] = result
                while len(self.preparations) > 32:
                    self.preparations.popitem(last=False)
                return result
            except BaseException as error:
                self.fault = str(error) or type(error).__name__
                raise
            finally:
                probe.log_file.close()

    def _closure(self, value):
        return (value-self.limits.open_s)/(self.limits.closed_s-self.limits.open_s)

    def closure(self, now=None):
        now = time.monotonic() if now is None else now
        fraction = min(1, max(0, (now-self.gripper_start)/self.gripper_seconds))
        return self.gripper_from + (self._closure(self.gripper_s)-self.gripper_from)*fraction

    def _line(self):
        self.pending += self.ser.readline()
        if b"\n" not in self.pending:
            return None
        raw, self.pending = self.pending.split(b"\n", 1)
        line = raw.decode("ascii", errors="replace").strip()
        if is_error(line) or line.lower().startswith("alarm"):
            raise RuntimeError(f"Robot error: {line}")
        return line

    def _status(self, timeout_s=.5):
        # The I/O lock guarantees that no command is in flight here. Discard
        # queued replies to earlier polls, so this receipt timestamp describes
        # the newly requested state rather than a buffered pre-move pose.
        self.ser.reset_input_buffer()
        self.pending = b""
        started = time.monotonic()
        self.ser.write(b"?\n")
        while time.monotonic()-started < timeout_s:
            line = self._line()
            if line and is_status(line):
                now = time.monotonic()
                return {**cartesian_status(line), "state_monotonic_s": now,
                        "state_rtt_s": now-started, "gripper_s": self.gripper_s,
                        "closure": self.closure(now)}
        raise TimeoutError("No Cartesian status response to '?'")

    def status(self):
        with self.lock:
            return self._status()

    def command(self, command, request_id):
        if not self.execute:
            raise PermissionError("Bridge is read-only; start with --execute to enable policy commands")
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 128:
            raise ValueError("A unique request_id of 1..128 characters is required")
        with self.lock:
            if request_id in self.completed:
                previous = self.completed[request_id]
                if previous["command"] != command:
                    raise ValueError("request_id already used for a different command")
                return previous.copy()  # reconnect/retry cannot execute the same command twice
            if self.fault:
                raise RuntimeError(f"Bridge stopped after an uncertain robot command; restart after checking the arm: {self.fault}")
            current = self._status()
            if current["state"].lower() != "idle":
                raise RuntimeError(f"Robot must be Idle before a policy command: {current['state']}")
            normalized, target, grip = self.limits.validate(command, current["cart6"])
            if target is not None and not self.absolute_mode:
                raise ValueError("Send G90 successfully before the first Cartesian move")
            # No previous command is in flight under this lock. Discard old acknowledgments.
            self.ser.reset_input_buffer()
            self.pending = b""
            started = time.monotonic()
            try:
                self.ser.write((normalized+"\n").encode("ascii"))
                ack, last_status, stable = False, None, deque(maxlen=3)
                next_query = started
                while time.monotonic()-started < self.timeout_s:
                    now = time.monotonic()
                    if now >= next_query:
                        self.ser.write(b"?\n")
                        next_query = now+.05
                    line = self._line()
                    if not line:
                        continue
                    if is_ok(line):
                        ack = True
                    if is_status(line):
                        last_status = cartesian_status(line)
                        last_status["state_monotonic_s"] = time.monotonic()
                        stable.append(last_status["cart6"])
                    if not ack:
                        continue
                    if grip is not None and self.gripper_s != grip:
                        self.gripper_from = self.closure(started)
                        self.gripper_s, self.gripper_start = grip, started
                    if target is None:
                        if grip is None or now-started >= self.gripper_seconds:
                            break
                    elif last_status and len(stable) == 3 and last_status["state"].lower() == "idle":
                        if any(math.dist(a[:3], stable[-1][:3]) > .1 or
                               max(abs((x-y+180) % 360-180) for x, y in zip(a[3:], stable[-1][3:])) > .1
                               for a in stable):
                            continue
                        cart = last_status["cart6"]
                        if math.dist(cart[:3], target[:3]) > 2 or max(
                                abs((a-b+180) % 360-180) for a, b in zip(cart[3:], target[3:])) > 2:
                            raise RuntimeError("Idle pose differs from target by more than 2 mm/deg")
                        break
                else:
                    raise TimeoutError(f"No acknowledged, settled completion within {self.timeout_s:g}s: {normalized}")
                if normalized == "G90":
                    self.absolute_mode = True
                result = {"ok": True, "request_id": request_id, "command": command,
                          "acknowledged": True, "elapsed_s": time.monotonic()-started,
                          "sent_monotonic_s": started, **self._status()}
                self.completed[request_id] = result
                while len(self.completed) > 1024:
                    self.completed.popitem(last=False)
                return result.copy()
            except Exception as exc:
                self.fault = str(exc)
                raise


class PolicyBridge:
    def __init__(self, robot, camera, *, max_frame_age_s=.5, max_skew_s=.15):
        self.robot, self.camera = robot, camera
        self.max_frame_age_s = positive(max_frame_age_s, "max_frame_age_s")
        self.max_skew_s = positive(max_skew_s, "max_skew_s")

    def observation(self):
        state = self.robot.status()
        frame = self.camera.snapshot(state["state_monotonic_s"], self.max_frame_age_s, self.max_skew_s)
        now = time.monotonic()
        return {"ok": True, "protocol": PROTOCOL, **state, **frame,
                "observation_monotonic_s": now, "state_age_s": now-state["state_monotonic_s"],
                "execute_enabled": self.robot.execute, "fault": self.robot.fault}


def make_handler(bridge, token=None):
    class Handler(BaseHTTPRequestHandler):
        def _json(self, status, payload):
            body = json.dumps(payload, allow_nan=False, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _authorized(self):
            if token and not hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer "+token):
                self._json(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "Authentication required"})
                return False
            return True

        def do_GET(self):  # noqa: N802
            if not self._authorized():
                return
            try:
                if self.path == "/health":
                    self._json(HTTPStatus.OK, {"ok": not bridge.camera.error and not bridge.robot.fault,
                               "protocol": PROTOCOL, "execute_enabled": bridge.robot.execute,
                               "camera": bridge.camera.metadata, "camera_error": bridge.camera.error,
                               "serial_port": getattr(bridge.robot.ser, "port", None),
                               "fault": bridge.robot.fault})
                elif self.path == "/observation":
                    self._json(HTTPStatus.OK, bridge.observation())
                elif self.path == "/recording/names":
                    self._json(HTTPStatus.OK, {"ok": True, "names": bridge.camera.recording_names()})
                elif (match := re.fullmatch(r"/recording/(I[1-9][0-9]*)/(video|frames|metadata)", self.path)):
                    path = bridge.camera.recording_file(*match.groups())
                    with path.open("rb") as source:
                        self.send_response(HTTPStatus.OK)
                        self.send_header("Content-Type", "application/octet-stream")
                        self.send_header("Content-Length", str(path.stat().st_size))
                        self.end_headers()
                        while chunk := source.read(65536):
                            self.wfile.write(chunk)
                else:
                    self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Unknown endpoint"})
            except (ValueError, RuntimeError, TimeoutError, OSError) as exc:
                self._json(HTTPStatus.SERVICE_UNAVAILABLE, {"ok": False, "error": str(exc)})

        def do_POST(self):  # noqa: N802
            if not self._authorized():
                return
            if self.path not in ("/command", "/prepare", "/recording/start", "/recording/stop"):
                self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Unknown endpoint"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 65536:
                    raise ValueError("Request must be 1..65536 bytes")
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict):
                    raise ValueError("Request body must be a JSON object")
                if self.path == "/recording/start":
                    result = {"ok": True, **bridge.camera.start_recording(data.get("run_name"))}
                elif self.path == "/recording/stop":
                    result = {"ok": True, **bridge.camera.stop_recording()}
                elif self.path == "/prepare":
                    result = bridge.robot.prepare(data.get("request_id"))
                else:
                    result = bridge.robot.command(data.get("command"), data.get("request_id"))
                self._json(HTTPStatus.OK, result)
            except PermissionError as exc:
                self._json(HTTPStatus.FORBIDDEN, {"ok": False, "error": str(exc)})
            except (ValueError, TypeError) as exc:
                self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
            except (RuntimeError, TimeoutError, OSError) as exc:
                self._json(HTTPStatus.CONFLICT, {"ok": False, "error": str(exc), "fault": bridge.robot.fault})

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial-port", "--port", dest="serial_port", required=True,
                        help="Robot serial port, e.g. COM3 (Windows) or /dev/ttyUSB0 (Linux)")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--listen-host", default="127.0.0.1")
    parser.add_argument("--http-port", type=int, default=DEFAULT_POLICY_PORT)
    parser.add_argument("--camera-serial")
    video = parser.add_mutually_exclusive_group()
    video.add_argument("--video-out", type=Path,
                        help="MP4 path. Recording starts only when inference requests /recording/start")
    video.add_argument("--video-dir", type=Path, help="Directory for repeated remote I1, I2, ... recordings")
    parser.add_argument("--color-profile", type=Path, default=DEFAULT_COLOR_PROFILE,
                        help="Training colour profile: fixes camera identity, stream profile and sensor controls; RGB stays uncorrected")
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--execute", action="store_true", help="Enable validated policy commands; startup still sends no motion")
    parser.add_argument("--command-timeout", type=float, default=30)
    parser.add_argument("--max-step-mm", type=float, default=25)
    parser.add_argument("--max-rotation-deg", type=float, default=20)
    parser.add_argument("--z-floor", type=float, default=MIROBOT_CARTESIAN_LIMITS_MM[2][0])
    parser.add_argument("--max-radius-mm", type=float, default=REACH_WARN_MM)
    parser.add_argument("--max-angle-deg", type=float, default=ANGLE_WARN_DEG)
    parser.add_argument("--max-frame-age", type=float, default=.5)
    parser.add_argument("--max-skew", type=float, default=.15)
    parser.add_argument("--initial-s", type=float, default=40, help="Actual gripper S already set before starting; no command sent")
    parser.add_argument("--open-s", type=float, default=40)
    parser.add_argument("--closed-s", type=float, default=60)
    parser.add_argument("--gripper-seconds", type=float, default=1)
    args = parser.parse_args()
    for name in ("width", "height", "fps", "baud"):
        if getattr(args, name) <= 0:
            parser.error(f"--{name} must be positive")
    try:
        import serial
    except ImportError as exc:
        raise SystemExit("Install robot requirements and pyrealsense2 before starting the policy bridge") from exc
    camera = D405Camera(args.camera_serial, args.width, args.height, args.fps, args.color_profile,
                        video_path=args.video_out, video_dir=args.video_dir)
    server = None
    try:
        camera.start()
        with serial.Serial(args.serial_port, args.baud, timeout=.01, write_timeout=1) as ser:
            # Opening a USB serial device can reset firmware. Never follow that with a home/move.
            time.sleep(2)
            limits = CommandLimits(args.z_floor, args.max_step_mm, args.max_rotation_deg, args.open_s, args.closed_s,
                                   args.max_radius_mm, args.max_angle_deg)
            robot = RobotIO(ser, execute=args.execute, limits=limits, timeout_s=args.command_timeout,
                            gripper_seconds=args.gripper_seconds, initial_s=args.initial_s)
            initial = robot.status()
            bridge = PolicyBridge(robot, camera, max_frame_age_s=args.max_frame_age, max_skew_s=args.max_skew)
            token = os.environ.get("MIROBOT_POLICY_TOKEN")
            server = ThreadingHTTPServer((args.listen_host, args.http_port), make_handler(bridge, token))
            server.daemon_threads = True
            print(f"Policy bridge http://{args.listen_host}:{args.http_port} | {initial['state']} {initial['cart6']}", flush=True)
            print(f"Commands {'enabled' if args.execute else 'disabled (read-only)'}; no homing or startup movement.", flush=True)
            server.serve_forever(poll_interval=.2)
    except KeyboardInterrupt:
        pass
    finally:
        if server is not None:
            server.server_close()
        camera.close()


if __name__ == "__main__":
    main()
