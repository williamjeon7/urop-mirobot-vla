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
from pathlib import Path
import sys
import time
from zoneinfo import ZoneInfo

from server.policy_runtime import CHUNK_SIZE, CosmosPolicy, PolicyConfig, REPO, W10_DATA
from common.workspace import MIROBOT_CARTESIAN_LIMITS_MM

DEFAULT_REFERENCE = REPO / "Mirobot_data/W10/L01_red"


def validate_goal(cart6, measured, args) -> dict:
    """Reject unsafe targets instead of changing the trained action silently."""
    cart6, measured = tuple(map(float, cart6)), tuple(map(float, measured))
    if len(cart6) != 6 or len(measured) != 6 or not all(map(math.isfinite, (*cart6, *measured))):
        raise ValueError("Target and measured Cartesian states need six finite values")
    if cart6[2] < args.z_floor:
        raise ValueError(f"Target Z {cart6[2]:.2f} mm below floor {args.z_floor:.2f}")
    for axis, value, (lower, upper) in zip("XYZ", cart6[:3], MIROBOT_CARTESIAN_LIMITS_MM):
        if not lower <= value <= upper:
            raise ValueError(f"Target {axis} {value:.2f} mm outside measured limits [{lower:.2f}, {upper:.2f}]")
    delta_mm = math.dist(cart6[:3], measured[:3])
    delta_deg = max(abs((a - b + 180) % 360 - 180) for a, b in zip(cart6[3:], measured[3:]))
    if math.hypot(*cart6[:2]) > args.max_radius:
        raise ValueError(f"Target exceeds {args.max_radius:g} mm horizontal radius")
    if max(abs(v) for v in cart6[3:]) > args.max_angle:
        raise ValueError(f"Target exceeds {args.max_angle:g} degree orientation limit")
    if delta_mm > args.max_step_mm or delta_deg > args.max_step_deg:
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
    MIN_COLOR_AREA = 8000
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
        count, _, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
        if count <= 1:
            self._clear_evidence()
            return None
        largest = max(range(1, count), key=lambda index: stats[index, cv2.CC_STAT_AREA])
        area = int(stats[largest, cv2.CC_STAT_AREA])
        center = tuple(float(value) for value in centroids[largest])
        if area < self.MIN_COLOR_AREA:
            self._clear_evidence()
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
        return dict(color=self.color, color_area_px=area, center_px=center,
                    lifted_mm=lift_mm, stable_observations=self.stable_observations)


class RunLog:
    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=False)
        self.directory = directory
        self.file = (directory / "events.jsonl").open("w", encoding="utf-8")

    def write(self, kind, **values):
        self.file.write(json.dumps(dict(kind=kind, time=datetime.now(ZoneInfo("Asia/Seoul")).isoformat(),
                                        **values), ensure_ascii=False) + "\n")
        self.file.flush()

    def image(self, wrist, query):
        import cv2
        path = self.directory / f"wrist_{query:04d}.png"
        ok, png = cv2.imencode(".png", cv2.cvtColor(wrist, cv2.COLOR_RGB2BGR))
        if not ok:
            raise RuntimeError("Cannot encode rollout observation")
        png.tofile(str(path))
        return path.name

    def finish(self, summary):
        (self.directory / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        self.file.close()


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
                          t5_embeddings=args.data_dir / "t5_embeddings.pkl", denoising_steps=args.denoising_steps)
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
    log = RunLog(directory)
    translator = FollowTranslator(frame)
    summary = dict(status="running", mode=mode, instruction=instruction, steps=0, queries=0,
                   checkpoint=str(config.checkpoint), directory=str(directory))
    print(f"Run log: {directory}")
    recording_requested = False
    until_pickup = getattr(args, "until_pickup", False)
    pickup_detector = VisualPickupDetector(args.color) if until_pickup else None
    pickup_confirmed = False
    pickup_deadline = None
    try:
        log.write("configuration", args={k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
                  instruction=instruction, policy={k: str(v) if isinstance(v, Path) else v for k, v in asdict(config).items()},
                  mapping=frame.settings)
        policy = CosmosPolicy(config)
        log.write("model_loaded", **policy.load_report)
        # Get a fresh observation after model initialization; it can take minutes.
        if client:
            observation = client.observation()
            wrist, state = live_input(observation, frame, profile, args.rotate)
        log.write("translator_initialized", **translator.initialize(observation["cart6"], observation["closure"]))
        if args.execute:
            client.command("G90")
            client.command("M20")
        if until_pickup:
            pickup_deadline = time.monotonic() + args.pickup_timeout
        previous_s = observation.get("gripper_s")
        while until_pickup or summary["steps"] < args.max_steps:
            if pickup_deadline is not None and time.monotonic() >= pickup_deadline:
                raise TimeoutError("Visual pickup was not confirmed before --pickup-timeout")
            if client and summary["queries"]:
                observation = client.observation()
                wrist, state = live_input(observation, frame, profile, args.rotate)
            gap = translator.gap(observation["cart6"])
            if gap["position_mm"] > args.max_drift_mm or gap["rotation_deg"] > args.max_step_deg:
                raise RuntimeError(f"Measured/virtual tracking gap exceeds limit: {gap}")
            if getattr(args, "record_video", False) and client and not recording_requested:
                # Model loading and device setup are excluded from the recording.
                # Set the flag first so a lost start reply still triggers a stop.
                recording_requested = True
                name = getattr(args, "recording_name", None)
                video = client.start_recording(name) if name else client.start_recording()
                summary["video"] = video
                log.write("recording_started", video=video)
                print(f"Recording started: {video['path']}", flush=True)
            actions = policy.predict(wrist, state, instruction)
            log.write("prediction", query=summary["queries"], image=log.image(wrist, summary["queries"]),
                      cart6=list(map(float, observation["cart6"])), proprio=list(map(float, state)),
                      seconds=policy.last_inference_seconds, actions=actions.tolist(), virtual_gap=gap)
            print(f"Query {summary['queries']}: {policy.last_inference_seconds:.2f} s, actions {actions.shape}")
            summary["queries"] += 1
            count = args.open_loop_steps if until_pickup else min(
                args.open_loop_steps if args.execute else CHUNK_SIZE,
                args.max_steps - summary["steps"])
            measured = list(observation["cart6"])
            for action in actions[:count]:
                if args.execute:
                    current = client.observation()
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
                try:
                    delta = validate_goal(target.cart6, measured, args)
                except ValueError as error:
                    log.write("target_rejected", step=summary["steps"], target=list(target.cart6), reason=str(error))
                    raise
                command = pose_command(target.cart6)
                print(f"{'send' if args.execute else 'preview'}: {command} ; M4 S{target.gripper_s:g}")
                log.write("target", step=summary["steps"], cart6=list(target.cart6),
                          virtual_cart6=list(target.virtual_cart6), command=command,
                          gripper_s=target.gripper_s, motion_scale=args.motion_scale,
                          executed=args.execute, **delta)
                if pickup_deadline is not None and time.monotonic() >= pickup_deadline:
                    raise TimeoutError("Visual pickup was not confirmed before --pickup-timeout")
                if args.execute:
                    result = client.command(command)
                    log.write("command_ack", command=command, result=result)
                    if previous_s != target.gripper_s:
                        result = client.command(f"M4 S{target.gripper_s:g}")
                        log.write("command_ack", command=f"M4 S{target.gripper_s:g}", result=result)
                        previous_s = target.gripper_s
                    # The bridge waits for Idle; observation verifies arrival.
                    settled = client.observation()
                    live_input(settled, frame, profile, args.rotate)
                    error_mm = math.dist(settled["cart6"][:3], target.cart6[:3])
                    error_deg = max(abs((a-b+180) % 360-180) for a, b in zip(settled["cart6"][3:], target.cart6[3:]))
                    if error_mm > args.arrival_tolerance_mm or error_deg > args.arrival_tolerance_deg:
                        raise RuntimeError(f"Robot did not reach target: {error_mm:.2f} mm / {error_deg:.2f} deg")
                    measured = settled["cart6"]
                    pickup = (pickup_detector.update(settled["rgb"], settled["cart6"], settled["closure"])
                              if pickup_detector else None)
                else:
                    measured = list(target.cart6)
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
            if pickup_confirmed:
                break
            if not args.execute:
                break  # preview never pretends the real robot followed the commands
        summary["status"] = "pickup_confirmed" if pickup_confirmed else "completed"
        print(f"Completed {summary['steps']} steps ({summary['status']}); log: {directory}")
    except BaseException as error:
        summary.update(status="interrupted" if isinstance(error, KeyboardInterrupt) else "failed", error=str(error))
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
            translator.close()
            log.finish(summary)
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
    p.add_argument("--z-floor", type=float, default=MIROBOT_CARTESIAN_LIMITS_MM[2][0])
    p.add_argument("--max-radius", type=float, default=280.0)
    p.add_argument("--max-angle", type=float, default=30.0)
    p.add_argument("--max-step-mm", type=float, default=10.0)
    p.add_argument("--max-step-deg", type=float, default=5.0)
    p.add_argument("--max-drift-mm", type=float, default=12.0)
    p.add_argument("--max-state-change-mm", type=float, default=2.0)
    p.add_argument("--arrival-tolerance-mm", type=float, default=2.0)
    p.add_argument("--arrival-tolerance-deg", type=float, default=1.0)
    p.add_argument("--log-dir", type=Path)
    p.add_argument("--record-video", action="store_true", help="Record live RGB from first inference to run completion")
    p.add_argument("--recording-name", help="Remote bridge recording name, e.g. I1")
    a = p.parse_args()
    if a.record_video and a.offline_smoke:
        p.error("--record-video needs a live camera bridge; it cannot be combined with --offline-smoke")
    if a.until_pickup:
        a.max_steps = None
        if not a.execute:
            p.error("--until-pickup requires --execute")
    if ((a.max_steps is not None and a.max_steps < 1) or
            not 1 <= a.open_loop_steps <= CHUNK_SIZE or a.denoising_steps < 1):
        p.error("Positive --max-steps/--denoising-steps and --open-loop-steps 1..16 required")
    for key in ("timeout", "max_radius", "max_angle", "max_step_mm", "max_step_deg", "max_drift_mm",
                "max_state_change_mm", "arrival_tolerance_mm", "arrival_tolerance_deg"):
        if not math.isfinite(getattr(a, key)) or getattr(a, key) <= 0:
            p.error(f"--{key.replace('_', '-')} must be finite and positive")
    if not math.isfinite(a.z_floor) or not math.isfinite(a.step_interval) or a.step_interval < 0:
        p.error("Finite --z-floor and nonnegative --step-interval required")
    if not math.isfinite(a.pickup_timeout) or a.pickup_timeout <= 0:
        p.error("--pickup-timeout must be finite and positive")
    if not math.isfinite(a.motion_scale) or a.motion_scale <= 0:
        p.error("--motion-scale must be finite and positive")
    for key in ("reference", "checkpoint", "data_dir", "log_dir"):
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
