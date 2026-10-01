"""Check the minimal drawer scene; record monitoring before any predicate probe."""

import argparse
import json
import logging
import os
from pathlib import Path

os.environ["MUJOCO_GL"] = "wgl"
os.environ.setdefault("NUMBA_DISABLE_JIT", "1")
ROOT = Path(__file__).resolve().parent
IMAGES = ROOT / "images"
JOINT_NAME = "wooden_cabinet_1_middle_level"
REGION_NAME = "wooden_cabinet_1_middle_region"
_original_file_handler = logging.FileHandler


def _workspace_file_handler(filename, *args, **kwargs):
    if filename == "/tmp/robosuite.log":
        filename = str(ROOT / "robosuite.log")
    return _original_file_handler(filename, *args, **kwargs)


logging.FileHandler = _workspace_file_handler

import cv2  # noqa: E402
import numpy as np  # noqa: E402
from libero.libero.envs.env_wrapper import OffScreenRenderEnv  # noqa: E402


def make_env(seed=0, size=512):
    env = OffScreenRenderEnv(
        bddl_file_name=str(ROOT / "custom_tasks" / "custom_test.bddl"),
        robots=["Panda"], initialization_noise=None,
        camera_heights=size, camera_widths=size,
        control_freq=20, horizon=3000, ignore_done=True,
    )
    env.seed(seed)
    return env


def frame_from(obs, caption):
    frame = cv2.cvtColor(obs["agentview_image"][::-1], cv2.COLOR_RGB2BGR)
    cv2.putText(frame, caption, (8, 25), cv2.FONT_HERSHEY_SIMPLEX,
                0.48, (255, 255, 255), 2, cv2.LINE_AA)
    return frame


def save_frame(path, obs, caption):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(path), frame_from(obs, caption)):
        raise RuntimeError("Could not save {}".format(path))


def open_writer(path, size, fps=20):
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"),
                             fps, (size, size))
    if not writer.isOpened():
        raise RuntimeError("Could not open video writer: {}".format(path))
    return writer


def scene_info(env):
    objects = list(env.env.objects_dict)
    fixtures = list(env.env.fixtures_dict)
    regions = list(env.env.parsed_problem["regions"])
    if objects or fixtures != ["wooden_cabinet_1"]:
        raise RuntimeError("The task must contain only the drawer cabinet.")
    return {"objects": objects, "fixtures": fixtures, "regions": regions,
            "objects_section_empty": env.env.parsed_problem["objects"] == {}}


def init_checks(env):
    return {"({})".format(" ".join(state)): bool(env.env._eval_predicate(state))
            for state in env.env.parsed_problem["initial_state"]}


def refresh_obs(env):
    env.sim.forward()
    env.env._update_observables(force=True)
    return env.env._get_observations(force_update=True)


def predicate_probe(env, obs, size):
    """Deliberately change only the drawer joint; never mix this with robot video."""
    path = IMAGES / "custom_bddl_predicate_test.mp4"
    writer = open_writer(path, size)
    rows = []
    try:
        frame = frame_from(obs, "Predicate probe: closed | goal=False")
        for _ in range(40):
            writer.write(frame)
        rows.append({"state": "closed", "joint_qpos_m": float(
            env.sim.data.get_joint_qpos(JOINT_NAME)),
            "goal": bool(env.check_success())})
        joint_id = env.sim.model.joint_name2id(JOINT_NAME)
        low, high = env.sim.model.jnt_range[joint_id]
        for name, fraction in (("high_direction", .9), ("open_direction", .1)):
            target = float(low + fraction * (high - low))
            env.sim.data.set_joint_qpos(JOINT_NAME, target)
            obs = refresh_obs(env)
            success = bool(env.check_success())
            rows.append({"state": name, "joint_qpos_m": target, "goal": success})
            frame = frame_from(obs, "Direct joint probe: {} | goal={}".format(name, success))
            for _ in range(40):
                writer.write(frame)
        if rows[0]["goal"] or rows[1]["goal"] or not rows[-1]["goal"]:
            raise RuntimeError("The drawer Open predicate did not match the joint states.")
        save_frame(IMAGES / "custom_bddl_goal_test.png", obs,
                   "Direct predicate test | goal=True")
        return obs, {"direct_state_changes": True, "part_of_robot_video": False,
                     "conditions": rows, "video": str(path.relative_to(ROOT))}
    finally:
        writer.release()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--headless", action="store_true", help="Run without an OpenCV window.")
    parser.add_argument("--steps", type=int, default=60, help="Initial zero-action monitoring steps.")
    parser.add_argument("--size", type=int, default=512)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--record", nargs="?", const="images/custom_bddl_monitoring.mp4",
                        help="Record monitoring; optionally supply an MP4 path.")
    parser.add_argument("--predicate-test", action="store_true",
                        help="Probe drawer joint states after monitoring recording closes.")
    args = parser.parse_args()
    if args.steps < 1 or args.size < 128:
        parser.error("steps must be positive and size must be at least 128")
    env = make_env(args.seed, args.size)
    writer = None
    monitoring_steps = 0
    monitoring_goals = []
    try:
        obs = env.reset()
        initial_goal = bool(env.check_success())
        info = scene_info(env)
        checks = init_checks(env)
        if initial_goal or not all(checks.values()):
            raise RuntimeError("The task must start with a correctly placed, closed drawer.")
        save_frame(IMAGES / "custom_bddl_test.png", obs,
                   "Drawer task: initial | goal=False")
        (ROOT / "custom_bddl_test.png").write_bytes(
            (IMAGES / "custom_bddl_test.png").read_bytes())
        print("Environment reset success", flush=True)
        print("Initial goal success:", initial_goal, flush=True)
        print("Scene:", info, flush=True)
        print("Initial checks:", checks, flush=True)
        video_path = Path(args.record) if args.record else None
        if video_path is not None:
            if not video_path.is_absolute():
                video_path = ROOT / video_path
            writer = open_writer(video_path, args.size)
            writer.write(frame_from(obs, "Zero-action monitoring | goal=False"))

        def monitor_step():
            nonlocal obs, monitoring_steps
            obs, _, _, _ = env.step(np.zeros(7, dtype=np.float32))
            monitoring_steps += 1
            goal = bool(env.check_success())
            monitoring_goals.append(goal)
            frame = frame_from(obs, "Zero-action monitoring | goal={}".format(goal))
            if writer is not None:
                writer.write(frame)
            if not args.headless:
                cv2.imshow("LIBERO Live - agentview", frame)
                return cv2.waitKey(1) & 0xFF in (ord("q"), ord("Q"), 27)
            return False

        stopped = False
        for _ in range(args.steps):
            if monitor_step():
                stopped = True
                break
        if not args.headless and not args.predicate_test:
            print("Live viewer: q / Q / ESC to finish", flush=True)
            while not stopped:
                stopped = monitor_step()
        if writer is not None:
            writer.release()
            writer = None
        save_frame(IMAGES / "libero_live_agentview.png", obs,
                   "Zero-action monitoring | goal={}".format(env.check_success()))
        save_frame(IMAGES / "bddl_zero_action_test.png", obs,
                   "Zero-action monitoring | goal={}".format(env.check_success()))
        if any(monitoring_goals):
            raise RuntimeError("A zero-action check must not already open the drawer.")
        result = {"bddl": "custom_tasks/custom_test.bddl", "seed": args.seed,
                  "camera_size": args.size, "initial_goal": initial_goal,
                  "initial_checks": checks, "scene": info,
                  "monitoring": {"action_steps": monitoring_steps,
                    "zero_actions_only": True, "goal_after_monitoring": bool(env.check_success()),
                    "direct_state_changes_during_video": False,
                    "control_frequency_hz": 20,
                    "video": str(video_path.relative_to(ROOT)) if video_path is not None and
                        ROOT in video_path.parents else str(video_path) if video_path else None}}
        if args.predicate_test:
            obs, result["predicate_test"] = predicate_probe(env, obs, args.size)
            if not args.headless:
                cv2.imshow("LIBERO Live - agentview", frame_from(obs, "Direct predicate test | goal=True"))
                cv2.waitKey(0)
        output = IMAGES / "custom_bddl_result.json"
        output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2), flush=True)
        print("Saved:", output, flush=True)
    finally:
        if writer is not None:
            writer.release()
        env.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
