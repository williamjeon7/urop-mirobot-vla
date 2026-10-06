"""W5 NewTaskBDDL-style RGB tabletop monitor, with no media/file output."""

import argparse
import json
import logging
import os
import sys
import time

# Apply the same Windows settings as W5 before importing robosuite / LIBERO.
if sys.platform == "win32":
    os.environ["MUJOCO_GL"] = "wgl"
    os.environ.setdefault("NUMBA_DISABLE_JIT", "1")
else:
    os.environ.setdefault("MUJOCO_GL", "egl")

# robosuite 1.4.0 logs to /tmp by default, which need not exist on Windows.
# Disable just that file handler while importing; do not create an output file.
_file_handler = logging.FileHandler


def _no_robosuite_file(filename, *args, **kwargs):
    if str(filename).replace("\\", "/") == "/tmp/robosuite.log":
        return logging.NullHandler()
    return _file_handler(filename, *args, **kwargs)


if sys.platform == "win32":
    logging.FileHandler = _no_robosuite_file
try:
    import cv2
    import numpy as np

    if __package__:
        from .preview import BLOCK_SIZE_MM, create_env, scene_state
        from .tasks import TASK_NAMES
    else:
        from preview import BLOCK_SIZE_MM, create_env, scene_state
        from tasks import TASK_NAMES
finally:
    logging.FileHandler = _file_handler

# Code-level settings. The block edge itself is objects.py: BLOCK_SIZE_MM.
CAMERA_SIZE = 512
SEED = 0
MONITORING_STEPS = 60
WINDOW_NAME = "LIBERO Live - RGB blocks"


def make_env(seed=SEED, size=CAMERA_SIZE, task="scene"):
    return create_env(resolution=size, seed=seed, ignore_done=True, task=task)


def frame_from(obs, step, goal):
    frame = cv2.cvtColor(obs["agentview_image"][::-1], cv2.COLOR_RGB2BGR)
    caption = "RGB cubes {:g} mm | step {} | placement={}".format(BLOCK_SIZE_MM, step, goal)
    cv2.putText(frame, caption, (8, 25), cv2.FONT_HERSHEY_SIMPLEX,
                0.48, (255, 255, 255), 1, cv2.LINE_AA)
    return frame


def init_checks(env):
    return {"({})".format(" ".join(state)): bool(env.env._eval_predicate(state))
            for state in env.env.parsed_problem["initial_state"]}


def monitor(env, steps=MONITORING_STEPS, headless=False):
    """Same reset -> step -> observation -> goal loop as W5, without saving."""
    window_open = False
    try:
        obs = env.reset()
        initial_goal = bool(env.check_success())
        checks = init_checks(env)
        scene = env.env
        scene_state(env)
        print("Environment reset success", flush=True)
        print("Task:", env.rgb_task["name"], "|", env.rgb_task["language"], flush=True)
        print("Initial placement goal:", initial_goal, "(pickup is not implemented)", flush=True)
        print("Initial checks:", checks, flush=True)
        if not headless:
            cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_AUTOSIZE)
            window_open = True
            print("Live viewer: q / Q / ESC or close the window to finish", flush=True)

        action = np.zeros(7, dtype=np.float32)
        step = 0
        # Like W5, steps bounds headless monitoring; the viewer continues until quit.
        while not headless or step < steps:
            started = time.perf_counter()
            obs, reward, done, info = env.step(action)
            step += 1
            goal = bool(env.check_success())
            if not goal:
                raise RuntimeError("The RGB blocks left their initial table regions.")
            if not headless:
                cv2.imshow(WINDOW_NAME, frame_from(obs, step, goal))
                remaining_ms = round((1 / scene.control_freq - (time.perf_counter() - started)) * 1000)
                key = cv2.waitKey(max(1, remaining_ms)) & 0xFF
                if key in (ord("q"), ord("Q"), 27):
                    break
                if cv2.getWindowProperty(WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
                    break
        result = scene_state(env, require_contact=True)
        result.update({
            "objects": sorted(scene.objects_dict),
            "block_size_mm": BLOCK_SIZE_MM, "initial_goal": initial_goal,
            "initial_checks": checks, "monitoring_steps": step,
            "goal_after_monitoring": bool(env.check_success()),
            "image_shape": list(obs["agentview_image"].shape),
            "zero_actions_only": True, "saved_files": False,
        })
        return result
    finally:
        env.close()
        if window_open:
            cv2.destroyAllWindows()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--headless", action="store_true", help="Verify without an OpenCV window.")
    parser.add_argument("--steps", type=int, default=MONITORING_STEPS)
    parser.add_argument("--size", type=int, default=CAMERA_SIZE, help="Camera resolution, not block size.")
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--task", choices=TASK_NAMES, default="scene",
                        help="Prepare the scene for this target; does not execute pickup.")
    args = parser.parse_args()
    if args.steps < 1 or args.size < 128:
        parser.error("steps must be positive and size must be at least 128")
    if not args.headless and sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
        parser.error(
            "This SSH terminal has no DISPLAY. W5 NewTaskBDDL runs its OpenCV "
            "window on a local Windows PC. Run this script on that PC or a Linux "
            "desktop. On this server, --headless verifies the simulation without a window."
        )
    try:
        print(json.dumps(monitor(make_env(args.seed, args.size, args.task),
                                 args.steps, args.headless), indent=2))
    except KeyboardInterrupt:
        pass
    except (RuntimeError, cv2.error) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
