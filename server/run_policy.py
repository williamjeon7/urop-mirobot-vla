"""Run the trained W10 policy through the D405/Mirobot bridge.

Without --execute this predicts one chunk and writes a G-code preview only.
--offline-smoke uses a recorded observation without connecting to hardware.
See docs/W10/DEPLOY_MIROBOT.md for the three-terminal procedure.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime
import json
import math
import re
from pathlib import Path
import sys
import time
from zoneinfo import ZoneInfo

from server.policy_runtime import CHUNK_SIZE, CosmosPolicy, PolicyConfig, REPO, W10_DATA
from common.workspace import MIROBOT_CARTESIAN_LIMITS_MM
from server.start_pose import move, segment_mm
from server.experiment_log import (export_trial, layout_document, manifest, serializable,
                                   trial_root, write_json)

DEFAULT_REFERENCE = REPO / "Mirobot_data/W10/L01_red"


# Where the arm can actually go, measured 2026-11-06 (tested edges, no extra margin).
REACH_LIMITS_MM = ((140.0, 270.0), (-180.0, 180.0), (None, 280.0))  # Z lower bound = --z-floor


def reach_bounds(args):
    (x, y, (_, z_top)) = REACH_LIMITS_MM
    return (x, y, (args.z_floor, z_top))


LEGACY_BRIDGE_Z_FLOOR_MM = 66.0  # floor of Windows bridges installed before 11/08


def bridge_z_floor(client):
    """Use the floor the bridge enforces, so a clamped target is never refused by the bridge."""
    health = getattr(client, "health", None)
    if not callable(health):
        return LEGACY_BRIDGE_Z_FLOOR_MM
    try:
        value = (health().get("limits") or {}).get("z_floor_mm")
    except (OSError, RuntimeError, ValueError):
        value = None
    return float(value) if value is not None else LEGACY_BRIDGE_Z_FLOOR_MM


def clamp_goal(cart6, args, measured=None):
    """Bring any target inside every limit instead of stopping (never refuse a policy action).

    Position (X/Y/Z box, horizontal radius), orientation and, given `measured`, the per-move
    step are all clamped. Returns (cart6, clamped) where clamped records what was cut.
    """
    cart6 = [float(v) for v in cart6]
    clamped = {}
    for index, (axis, (lower, upper)) in enumerate(zip("XYZ", reach_bounds(args))):
        value = cart6[index]
        if value < lower:
            cart6[index], clamped[axis] = lower, round(value - lower, 3)
        elif value > upper:
            cart6[index], clamped[axis] = upper, round(value - upper, 3)
    radius = math.hypot(*cart6[:2])
    if radius > args.max_radius - 0.01:
        scale = (args.max_radius - 0.01) / radius  # stays inside after 3-decimal rounding
        cart6[0], cart6[1] = cart6[0] * scale, cart6[1] * scale
        clamped["radius"] = round(radius - args.max_radius, 3)
    limit = args.max_angle - 0.01
    for index, axis in enumerate("ABC", start=3):
        if abs(cart6[index]) > limit:
            clamped[axis] = round(cart6[index], 3)
            cart6[index] = math.copysign(limit, cart6[index])
    if measured is not None:
        measured = [float(v) for v in measured]
        distance = math.dist(cart6[:3], measured[:3])
        if distance > args.max_step_mm:
            fraction = args.max_step_mm / distance
            cart6[:3] = [m + (c - m) * fraction for c, m in zip(cart6[:3], measured[:3])]
            clamped["step_mm"] = round(distance, 3)
        turn = [((c - m + 180) % 360) - 180 for c, m in zip(cart6[3:], measured[3:])]
        largest = max(abs(t) for t in turn)
        if largest > args.max_step_deg:
            fraction = args.max_step_deg / largest
            cart6[3:] = [m + t * fraction for m, t in zip(measured[3:], turn)]
            clamped["step_deg"] = round(largest, 3)
    return tuple(cart6), clamped


def validate_goal(cart6, measured, args) -> dict:
    """Final check after clamp_goal: values must be finite and inside every limit."""
    cart6, measured = tuple(map(float, cart6)), tuple(map(float, measured))
    if len(cart6) != 6 or len(measured) != 6 or not all(map(math.isfinite, (*cart6, *measured))):
        raise ValueError("Target and measured Cartesian states need six finite values")
    if cart6[2] < args.z_floor - 1e-6:
        raise ValueError(f"Target Z {cart6[2]:.2f} mm below floor {args.z_floor:.2f}")
    for axis, value, (lower, upper) in zip("XYZ", cart6[:3], reach_bounds(args)):
        if not lower - 1e-6 <= value <= upper + 1e-6:
            raise ValueError(f"Target {axis} {value:.2f} mm outside reach [{lower:.2f}, {upper:.2f}]")
    delta_mm = math.dist(cart6[:3], measured[:3])
    delta_deg = max(abs((a - b + 180) % 360 - 180) for a, b in zip(cart6[3:], measured[3:]))
    if math.hypot(*cart6[:2]) > args.max_radius:
        raise ValueError(f"Target exceeds {args.max_radius:g} mm horizontal radius")
    if max(abs(v) for v in cart6[3:]) > args.max_angle:
        raise ValueError(f"Target exceeds {args.max_angle:g} degree orientation limit")
    if delta_mm > args.max_step_mm + 1e-6 or delta_deg > args.max_step_deg + 1e-6:
        raise ValueError(f"Target step too large: {delta_mm:.2f} mm, {delta_deg:.2f} deg")
    return dict(delta_mm=delta_mm, delta_deg=delta_deg)


def pose_command(cart6) -> str:
    return "G0 " + " ".join(f"{axis}{value:.3f}" for axis, value in zip("XYZABC", cart6))


def scale_motion_action(action, scale: float) -> tuple[float, ...]:
    values = tuple(float(value) for value in action)
    if len(values) != 7 or not math.isfinite(scale) or scale <= 0:
        raise ValueError("A seven-value action and positive finite motion scale are required")
    return tuple(max(-1.0, min(1.0, value * scale)) if index < 3 else value
                 for index, value in enumerate(values))


class VisualPickupDetector:
    MIN_CLOSED_FRACTION = 0.8
    MIN_LIFT_MM = 15.0
    # 11/08, from 7 reviewed pickups: blocks really held measured 32k-72k px and touched the dark
    # fingers on 1.5k-2.4k px; false confirmations (block left on the table) were 17k-21k px and
    # 84-275 px. Thresholds sit between the two groups.
    MIN_COLOR_AREA = 26000
    MIN_FINGER_CONTACT_PX = 800
    MAX_CENTER_SHIFT_PX = 40.0
    REQUIRED_STABLE_OBSERVATIONS = 3

    def __init__(self, color: str):
        self.color = color
        self.grasp_z = None
        self.previous = None
        self.stable_observations = 0

    def _clear_evidence(self):
        self.previous = None
        self.stable_observations = 0

    def update(self, rgb, cart6, closure):
        if closure < self.MIN_CLOSED_FRACTION:
            self.grasp_z = None
            self._clear_evidence()
            return None

        z = float(cart6[2])
        if self.grasp_z is None:
            self.grasp_z = z
            return None
        lift_mm = z - self.grasp_z
        if lift_mm < self.MIN_LIFT_MM:
            self._clear_evidence()
            return None

        import cv2

        hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
        if self.color == "red":
            mask = (cv2.inRange(hsv, (0, 100, 50), (12, 255, 255)) |
                    cv2.inRange(hsv, (168, 100, 50), (179, 255, 255)))
        elif self.color == "green":
            mask = cv2.inRange(hsv, (35, 70, 40), (90, 255, 255))
        else:
            mask = cv2.inRange(hsv, (90, 70, 40), (140, 255, 255))
        count, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
        if count <= 1:
            self._clear_evidence()
            return None
        largest = max(range(1, count), key=lambda index: stats[index, cv2.CC_STAT_AREA])
        area = int(stats[largest, cv2.CC_STAT_AREA])
        center = tuple(float(value) for value in centroids[largest])
        if area < self.MIN_COLOR_AREA:
            self._clear_evidence()
            return None
        contact = self.finger_contact(hsv, labels == largest)
        if contact < self.MIN_FINGER_CONTACT_PX:
            self._clear_evidence()  # a block lying on the table, not one between the fingers
            return None

        if self.previous is None:
            self.stable_observations = 1
        else:
            previous_area, previous_center = self.previous
            ratio = area / previous_area
            shift = math.dist(center, previous_center)
            if shift <= self.MAX_CENTER_SHIFT_PX and 0.6 <= ratio <= 1.67:
                self.stable_observations += 1
            else:
                self.stable_observations = 1
        self.previous = (area, center)
        if self.stable_observations < self.REQUIRED_STABLE_OBSERVATIONS:
            return None
        return dict(color=self.color, color_area_px=area, center_px=center, finger_contact_px=contact,
                    lifted_mm=lift_mm, stable_observations=self.stable_observations)

    @staticmethod
    def finger_contact(hsv, region):
        """Dark-grey gripper pixels within ~7 px of the colour region."""
        import cv2
        import numpy as np
        dark = cv2.inRange(hsv, (0, 0, 0), (179, 90, 70)) > 0
        ring = cv2.dilate(region.astype(np.uint8), np.ones((15, 15), np.uint8)) > 0
        return int((ring & dark).sum())


class RunLog:
    def __init__(self, directory: Path | None):
        self.started = time.monotonic()
        self.rollout_started = None
        self.observation_count = 0
        self.directory = directory
        self.file = None
        if directory is None:
            return
        directory.mkdir(parents=True, exist_ok=False)
        self.file = (directory / "events.jsonl").open("w", encoding="utf-8")

    def write(self, kind, **values):
        if self.file is None:
            return
        self.file.write(json.dumps(dict(kind=kind, time=datetime.now(ZoneInfo("Asia/Seoul")).isoformat(),
                                        t_s=time.monotonic()-self.started,
                                        rollout_t_s=(time.monotonic()-self.rollout_started
                                                     if self.rollout_started is not None else None),
                                        **serializable(values)), ensure_ascii=False, allow_nan=False) + "\n")
        self.file.flush()

    def image(self, wrist, query, prefix="wrist"):
        if self.file is None:
            return None
        import cv2
        path = self.directory / f"{prefix}_{query:04d}.png"
        ok, png = cv2.imencode(".png", cv2.cvtColor(wrist, cv2.COLOR_RGB2BGR))
        if not ok:
            raise RuntimeError("Cannot encode rollout observation")
        png.tofile(str(path))
        return path.name

    def observation(self, observation, phase, **values):
        image = self.image(observation["rgb"], self.observation_count, prefix="rgb") if "rgb" in observation else None
        self.observation_count += 1
        self.write("observation", phase=phase, image=image,
                   observation={k: v for k, v in observation.items() if k != "rgb"}, **values)

    def configure(self, args, config):
        if self.file is None:
            return
        root = trial_root(self.directory)
        write_json(root / "experiment.json", manifest(root, args, config))
        layout = layout_document(getattr(args, "layout_json", None))
        layout.pop("_photo_source", None)
        write_json(root / "layout.json", layout)

    def features(self, policy, query):
        if self.file is None:
            return None
        arrays = getattr(policy, "last_features", None)
        if not arrays:
            return None
        import numpy as np
        path = self.directory / f"features_{query:04d}.npz"
        np.savez_compressed(path, **arrays)
        return path.name

    def finish(self, summary):
        summary["duration_s"] = time.monotonic() - self.started
        if self.file is not None:
            try:
                write_json(self.directory / "summary.json", summary)
                export_trial(self.directory)
            finally:
                self.file.close()


def wants_recording(args, client):
    return bool(getattr(args, "record_video", False) and client)


def start_recording(args, client, summary, log, attempts=500):
    name = getattr(args, "recording_name", None)
    legacy = re.fullmatch(r"I([1-9][0-9]*)", name or "")
    for _ in range(attempts if legacy else 1):
        try:
            video = client.start_recording(name) if name else client.start_recording()
            break
        except RuntimeError as error:
            # An older Windows bridge refuses a name it already used ("File exists"); try the next one.
            if not legacy or "exist" not in str(error).lower():
                raise
            log.write("recording_name_taken", name=name)
            name = f"I{int(re.fullmatch(r'I([0-9]+)', name)[1]) + 1}"
    else:
        raise RuntimeError("No free Windows recording name found")
    summary["recording_name"] = name
    summary["video"] = video
    log.write("recording_started", video=video)
    print(f"Recording started: {video['path']}", flush=True)


def offline_observation(path, index, frame):
    import h5py
    import numpy as np
    from common.rotation import quat_xyzw_to_wxyz
    with h5py.File(path, "r") as source:
        demo = source["data/demo_0"]
        if not 0 <= index < len(demo["actions"]):
            raise ValueError("--sample-index outside the recorded episode")
        state = np.asarray(demo["robot_states"][index], dtype=np.float32)
        wrist = demo["obs/eye_in_hand_rgb"][index]
    xyz, abc = frame.to_mirobot(state[2:5], quat_xyzw_to_wxyz(state[5:9]))
    return dict(cart6=list((*xyz, *abc)), closure=0.0, state="Idle"), wrist, state


def live_input(observation, frame, profile, rotate):
    from tools.policy_obs import wrist_from_rgb
    camera = observation.get("camera", {})
    if (camera.get("serial") != profile["camera_serial"] or
            any(camera.get(key) != profile[key] for key in ("width", "height", "fps"))):
        raise RuntimeError("Bridge camera identity/resolution/fps differs from the training colour profile")
    locked = camera.get("locked_camera_options", {})
    for key, value in profile["camera_options"].items():
        actual = locked.get(key)
        if not isinstance(actual, (int, float)) or not math.isfinite(actual) or abs(actual-value) > max(1, abs(value)*.001):
            raise RuntimeError(f"Bridge camera setting {key} differs from the training colour profile")
    if str(observation["state"]).lower() != "idle":
        raise RuntimeError(f"Robot must be Idle, got {observation['state']!r}")
    wrist = wrist_from_rgb(observation["rgb"], profile, rotate)
    return wrist, frame.proprio(observation["cart6"], observation["closure"])


def run(args):
    from docs.W9.d405.color_calibration import load_profile
    from server.follow_translator import FollowTranslator
    from tools.policy_obs import MirobotFrame

    instruction = f"pick up the {args.color} block on the table"
    frame = MirobotFrame.from_files(args.reference / "reference.jsonl", args.reference / "source.gcode")
    profile = load_profile(args.reference / "color_profile.json")
    config = PolicyConfig(checkpoint=args.checkpoint, statistics=args.data_dir / "dataset_statistics.json",
                          t5_embeddings=args.data_dir / "t5_embeddings.pkl", denoising_steps=args.denoising_steps,
                          capture_features=not getattr(args, "no_save", False))
    client = None
    if args.offline_smoke:
        files = sorted((args.data_dir / "mirobot_real").glob(f"MIROBOT_L01_{args.color}_*.hdf5"))
        if len(files) != 1:
            raise ValueError("Expected exactly one L01 HDF5 for --color in --data-dir")
        observation, wrist, state = offline_observation(files[0], args.sample_index, frame)
    else:
        from server.policy_client import PolicyClient
        client = PolicyClient(args.bridge_url, timeout_s=args.timeout)
        observation = client.observation()
        wrist, state = live_input(observation, frame, profile, args.rotate)
        if args.bridge_check:
            print(json.dumps({k: v for k, v in observation.items() if k != "rgb"}, indent=2, ensure_ascii=False))
            print("Bridge, latest RGB, Cartesian state and preprocessing: OK (no commands sent)")
            return
        if args.execute and not observation.get("execute_enabled"):
            raise RuntimeError("Bridge is read-only; restart robot.policy_bridge with --execute")

    stamp = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y%m%d_%H%M%S_%f")
    mode = "execute" if args.execute else "offline_smoke" if args.offline_smoke else "preview"
    directory = args.log_dir or REPO / "cosmos-policy/W10/evaluations/real" / f"{stamp}_{args.color}_{mode}"
    log = RunLog(None if getattr(args, "no_save", False) else directory)
    translator = None
    summary = dict(status="running", mode=mode, instruction=instruction, steps=0, queries=0,
                   checkpoint=str(config.checkpoint), directory=str(directory))
    print(f"Run log: {directory}")
    live = None
    if client is not None and getattr(args, "live_view_port", 0):
        from server.live_view import attach

        def describe(observation):
            cart = observation.get("cart6") or [float("nan")] * 3
            return (f"{args.color} | query {summary['queries']} step {summary['steps']} | "
                    f"{summary.get('stage', '')} | X {cart[0]:.0f} Y {cart[1]:.0f} Z {cart[2]:.0f} mm")
        live = attach(client, args.live_view_port, describe, log=lambda text: print(text, flush=True))
    recording_requested = False
    until_pickup = getattr(args, "until_pickup", False)
    # Watch every colour: lifting a block of another colour ends the run as a failure.
    pickup_detectors = {c: VisualPickupDetector(c) for c in ("red", "green", "blue")} if until_pickup else None
    pickup_confirmed = False
    wrong_pickup = None
    segment = None
    pickup_deadline = None
    rollout_started = None
    try:
        log.configure(args, config)
        log.observation(observation, "initial", query=0, step=0)
        log.write("configuration", args={k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
                  instruction=instruction, policy={k: str(v) if isinstance(v, Path) else v for k, v in asdict(config).items()},
                  mapping=frame.settings)
        summary["stage"] = "model_loading"
        policy = CosmosPolicy(config)
        log.write("model_loaded", **policy.load_report)
        translator = FollowTranslator(frame)
        # Get a fresh observation after model initialization; it can take minutes.
        if client:
            observation = client.observation()
            wrist, state = live_input(observation, frame, profile, args.rotate)
        log.observation(observation, "ready", query=0, step=0)
        summary["stage"] = "translator_initialization"
        log.write("translator_initialized", **translator.initialize(observation["cart6"], observation["closure"]))
        if args.execute:
            for setup in ("G90", "M20"):
                log.write("command_ack", command=setup, result=client.command(setup), step=0, query=0)
        if getattr(args, "z_floor", None) is None:
            args.z_floor = bridge_z_floor(client)
        log.write("limits", z_floor=args.z_floor, reach=reach_bounds(args), max_radius=args.max_radius,
                  max_angle=args.max_angle, max_step_mm=args.max_step_mm, max_step_deg=args.max_step_deg)
        if args.execute:
            segment = segment_mm(client)
            log.write("move_segmentation", max_segment_mm=segment)
        rollout_started = time.monotonic()
        log.rollout_started = rollout_started
        if until_pickup:
            pickup_deadline = time.monotonic() + args.pickup_timeout
        previous_s = observation.get("gripper_s")
        while until_pickup or summary["steps"] < args.max_steps:
            summary["stage"] = "observation"
            if pickup_deadline is not None and time.monotonic() >= pickup_deadline:
                raise TimeoutError("Visual pickup was not confirmed before --pickup-timeout")
            if client and summary["queries"]:
                observation = client.observation()
                wrist, state = live_input(observation, frame, profile, args.rotate)
            log.observation(observation, "query", query=summary["queries"], step=summary["steps"])
            gap = translator.gap(observation["cart6"])
            # Off by default (inf): clamping makes the real arm lag the virtual one on purpose.
            if gap["position_mm"] > args.max_drift_mm or gap["rotation_deg"] > getattr(args, "max_drift_deg", math.inf):
                raise RuntimeError(f"Measured/virtual tracking gap exceeds limit: {gap}")
            if not args.execute and not recording_requested and wants_recording(args, client):
                recording_requested = True  # set first so a lost start reply still triggers a stop
                start_recording(args, client, summary, log)
            summary["stage"] = "policy_inference"
            actions = policy.predict(wrist, state, instruction)
            log.write("prediction", query=summary["queries"], image=log.image(wrist, summary["queries"]),
                      cart6=list(map(float, observation["cart6"])), proprio=list(map(float, state)),
                      seconds=policy.last_inference_seconds, actions=actions.tolist(), virtual_gap=gap,
                      features=log.features(policy, summary["queries"]),
                      feature_metadata=getattr(policy, "feature_metadata", {"status": "unavailable"}))
            print(f"Query {summary['queries']}: {policy.last_inference_seconds:.2f} s, actions {actions.shape}")
            summary["queries"] += 1
            count = args.open_loop_steps if until_pickup else min(
                args.open_loop_steps if args.execute else CHUNK_SIZE,
                args.max_steps - summary["steps"])
            measured = list(observation["cart6"])
            for action in actions[:count]:
                if args.execute:
                    summary["stage"] = "pre_command_observation"
                    current = client.observation()
                    log.observation(current, "before_command", query=summary["queries"]-1, step=summary["steps"])
                    live_input(current, frame, profile, args.rotate)
                    # A robot moved during inference invalidates that observation.
                    if math.dist(current["cart6"][:3], measured[:3]) > args.max_state_change_mm:
                        raise RuntimeError("Robot changed position during inference or between commands")
                    angle_change = max(abs((a-b+180) % 360-180) for a, b in zip(current["cart6"][3:], measured[3:]))
                    if angle_change > args.max_step_deg:
                        raise RuntimeError("Robot changed orientation during inference or between commands")
                    measured = current["cart6"]
                motion_action = scale_motion_action(action, args.motion_scale)
                target = translator.target(motion_action)
                summary["stage"] = "target_validation"
                goal, clamped = clamp_goal(target.cart6, args, measured)
                if clamped:
                    summary["clamped_steps"] = summary.get("clamped_steps", 0) + 1
                try:
                    delta = validate_goal(goal, measured, args)
                except ValueError as error:
                    log.write("target_rejected", step=summary["steps"], target=list(target.cart6),
                              clamped_target=list(goal), reason=str(error))
                    raise
                command = pose_command(goal)
                print(f"{'send' if args.execute else 'preview'}: {command} ; M4 S{target.gripper_s:g}")
                log.write("target", step=summary["steps"], cart6=list(goal), policy_cart6=list(target.cart6),
                          clamped=clamped, virtual_cart6=list(target.virtual_cart6), command=command,
                          gripper_s=target.gripper_s, motion_scale=args.motion_scale,
                          query=summary["queries"]-1, policy_action=list(map(float, action)),
                          applied_action=list(motion_action), executed=args.execute, **delta)
                if pickup_deadline is not None and time.monotonic() >= pickup_deadline:
                    raise TimeoutError("Visual pickup was not confirmed before --pickup-timeout")
                if args.execute:
                    if not recording_requested and wants_recording(args, client):
                        # Homing, initial pose and model loading are over: record from the first policy motion.
                        recording_requested = True  # set first so a lost start reply still triggers a stop
                        start_recording(args, client, summary, log)
                    summary["stage"] = "robot_command"
                    step_no, query_no = summary["steps"], summary["queries"]-1
                    # Old bridges may refuse a single move longer than 2 mm (see server/start_pose.py):
                    # send it in short segments and wait on this side until the arm has stopped.
                    move(client, measured, goal, segment, sleep=time.sleep,
                         on_command=lambda c, r: log.write("command_ack", command=c, result=r,
                                                           step=step_no, query=query_no))
                    if previous_s != target.gripper_s:
                        result = client.command(f"M4 S{target.gripper_s:g}")
                        log.write("command_ack", command=f"M4 S{target.gripper_s:g}", result=result,
                                  step=summary["steps"], query=summary["queries"]-1)
                        previous_s = target.gripper_s
                    # The bridge waits for Idle; observation verifies arrival.
                    settled = client.observation()
                    log.observation(settled, "after_command", query=summary["queries"]-1, step=summary["steps"])
                    live_input(settled, frame, profile, args.rotate)
                    error_mm = math.dist(settled["cart6"][:3], goal[:3])
                    error_deg = max(abs((a-b+180) % 360-180) for a, b in zip(settled["cart6"][3:], goal[3:]))
                    log.write("arrival_check", step=summary["steps"], query=summary["queries"]-1,
                              error_mm=error_mm, error_deg=error_deg, cart6=settled["cart6"],
                              target=list(goal))
                    if error_mm > args.arrival_tolerance_mm or error_deg > args.arrival_tolerance_deg:
                        raise RuntimeError(f"Robot did not reach target: {error_mm:.2f} mm / {error_deg:.2f} deg")
                    measured = settled["cart6"]
                    found = ({c: d.update(settled["rgb"], settled["cart6"], settled["closure"])
                              for c, d in pickup_detectors.items()} if pickup_detectors else {})
                    pickup = found.get(args.color)
                    if pickup is None:
                        wrong_pickup = next((v for c, v in found.items() if c != args.color and v), None)
                else:
                    measured = list(goal)
                    pickup = None
                translator.advance(motion_action)
                summary["steps"] += 1
                if args.execute:
                    time.sleep(args.step_interval)
                if pickup is not None:
                    summary["pickup"] = pickup
                    log.write("pickup_confirmed", step=summary["steps"], **pickup)
                    print(f"Pickup visually confirmed after {summary['steps']} actions")
                    pickup_confirmed = True
                    break
                if wrong_pickup is not None:
                    summary["wrong_pickup"] = wrong_pickup
                    log.write("wrong_color_pickup", step=summary["steps"], requested=args.color, **wrong_pickup)
                    print(f"Wrong colour lifted ({wrong_pickup['color']}, requested {args.color}) "
                          f"after {summary['steps']} actions: stopping as failure")
                    break
            if pickup_confirmed or wrong_pickup is not None:
                break
            if not args.execute:
                break  # preview never pretends the real robot followed the commands
        summary["status"] = ("pickup_confirmed" if pickup_confirmed else
                             "wrong_color_pickup" if wrong_pickup is not None else "completed")
        summary["termination_reason"] = ("visual_pickup_heuristic" if pickup_confirmed else
                                         "wrong_color_pickup" if wrong_pickup is not None else "step_limit")
        print(f"Completed {summary['steps']} steps ({summary['status']}); log: {directory}")
    except BaseException as error:
        summary.update(status="interrupted" if isinstance(error, KeyboardInterrupt) else "failed", error=str(error))
        summary["termination_reason"] = ("operator_interrupt" if isinstance(error, KeyboardInterrupt)
                                         else "timeout" if isinstance(error, TimeoutError) else summary.get("stage"))
        summary["error_type"] = type(error).__name__
        log.write("stopped", **summary)
        raise
    finally:
        video_error = None
        try:
            if recording_requested:
                try:
                    video = client.stop_recording()
                    summary["video"] = video
                    log.write("recording_stopped", video=video)
                    if not video["frames"]:
                        raise RuntimeError("The camera did not record any video frames")
                    print(f"Recording saved: {video['path']} ({video['frames']} frames)", flush=True)
                except (OSError, RuntimeError, ValueError) as error:
                    summary["video_error"] = str(error)
                    print(f"Recording stop failed: {error}", file=sys.stderr)
                    if summary["status"] == "completed":
                        summary["status"] = "failed"
                        video_error = RuntimeError(f"Video could not be finalized: {error}")
        finally:
            summary["rollout_duration_s"] = time.monotonic() - rollout_started if rollout_started is not None else None
            if client is not None:
                summary["stale_observation_retries"] = getattr(client, "stale_retries", 0)
                summary["command_retries"] = getattr(client, "command_retries", 0)
            try:
                if translator is not None:
                    translator.close()
            finally:
                log.finish(summary)
                if live is not None:
                    live.close()
        if video_error is not None:
            raise video_error


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--color", choices=("red", "green", "blue"), default="red")
    p.add_argument("--bridge-url", default="http://127.0.0.1:8891")
    p.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    p.add_argument("--checkpoint", type=Path, default=PolicyConfig().checkpoint)
    p.add_argument("--data-dir", type=Path, default=W10_DATA)
    modes = p.add_mutually_exclusive_group()
    modes.add_argument("--execute", action="store_true", help="Send validated commands to the armed bridge")
    modes.add_argument("--offline-smoke", action="store_true", help="Infer one recorded observation and preview actions")
    modes.add_argument("--bridge-check", action="store_true", help="Check live observation only, without loading the model")
    stop = p.add_mutually_exclusive_group()
    stop.add_argument("--max-steps", type=int, default=4)
    stop.add_argument("--until-pickup", action="store_true", help="Continue until visual pickup confirmation")
    p.add_argument("--pickup-timeout", type=float, default=600.0,
                   help="Safety timeout in seconds for --until-pickup")
    p.add_argument("--open-loop-steps", type=int, default=1, help="Actions to execute before observing/predicting again (1..16)")
    p.add_argument("--motion-scale", type=float, default=1.0,
                   help="Scale XYZ action deltas before applying the same action to the virtual translator")
    p.add_argument("--sample-index", type=int, default=0)
    p.add_argument("--denoising-steps", type=int, default=5)
    p.add_argument("--rotate", type=int, choices=(0, 90, 180, 270), default=0)
    p.add_argument("--timeout", type=float, default=40.0)
    p.add_argument("--step-interval", type=float, default=0.05)
    p.add_argument("--z-floor", type=float, default=None,
                   help="Lowest flange Z (mm). Default: the floor the Windows bridge reports, else 66")
    p.add_argument("--max-radius", type=float, default=280.0)
    p.add_argument("--limit-margin-mm", type=float, default=math.inf,
                   help="(kept for old commands; targets are always clamped inside the limits)")
    p.add_argument("--max-angle", type=float, default=30.0)
    p.add_argument("--max-step-mm", type=float, default=10.0)
    p.add_argument("--max-step-deg", type=float, default=5.0)
    p.add_argument("--max-drift-mm", type=float, default=math.inf,
                   help="Stop when real and virtual arm differ by more than this (default: never)")
    p.add_argument("--max-drift-deg", type=float, default=math.inf)
    p.add_argument("--max-state-change-mm", type=float, default=2.0)
    p.add_argument("--arrival-tolerance-mm", type=float, default=2.0)
    p.add_argument("--arrival-tolerance-deg", type=float, default=1.0)
    p.add_argument("--log-dir", type=Path)
    p.add_argument("--record-video", action="store_true", help="Record live RGB from the first policy motion (first inference in preview) to the end of the run")
    p.add_argument("--recording-name", help="Remote bridge recording name, e.g. I1")
    p.add_argument("--layout-json", type=Path, help="Initial block layout in the dataset paper coordinate frame (cm)")
    p.add_argument("--no-save", action="store_true", help="One-off check without experiment files or video")
    p.add_argument("--live-view-port", type=int, default=8893,
                   help="Browser view of the observations this run receives (0 turns it off)")
    a = p.parse_args()
    if a.no_save:
        a.record_video = False
    if a.record_video and a.offline_smoke:
        p.error("--record-video needs a live camera bridge; it cannot be combined with --offline-smoke")
    if a.until_pickup:
        a.max_steps = None
        if not a.execute:
            p.error("--until-pickup requires --execute")
    if ((a.max_steps is not None and a.max_steps < 1) or
            not 1 <= a.open_loop_steps <= CHUNK_SIZE or a.denoising_steps < 1):
        p.error("Positive --max-steps/--denoising-steps and --open-loop-steps 1..16 required")
    for key in ("timeout", "max_radius", "max_angle", "max_step_mm", "max_step_deg",
                "max_state_change_mm", "arrival_tolerance_mm", "arrival_tolerance_deg"):
        if not math.isfinite(getattr(a, key)) or getattr(a, key) <= 0:
            p.error(f"--{key.replace('_', '-')} must be finite and positive")
    if (a.z_floor is not None and not math.isfinite(a.z_floor)) or not math.isfinite(a.step_interval) or a.step_interval < 0:
        p.error("Finite --z-floor and nonnegative --step-interval required")
    for key in ("max_drift_mm", "max_drift_deg"):
        if math.isnan(getattr(a, key)) or getattr(a, key) <= 0:
            p.error(f"--{key.replace('_', '-')} must be positive (inf disables it)")
    if not math.isfinite(a.pickup_timeout) or a.pickup_timeout <= 0:
        p.error("--pickup-timeout must be finite and positive")
    if not math.isfinite(a.motion_scale) or a.motion_scale <= 0:
        p.error("--motion-scale must be finite and positive")
    for key in ("reference", "checkpoint", "data_dir", "log_dir", "layout_json"):
        value = getattr(a, key)
        if value is not None:
            setattr(a, key, value.absolute())
    try:
        run(a)
    except KeyboardInterrupt:
        p.exit(130, "Interrupted; no further commands will be sent.\n")
    except (OSError, ValueError, RuntimeError) as error:
        p.exit(1, f"Policy stopped: {error}\n")


if __name__ == "__main__":
    main()
