"""Panda pick up of one RGB block with OSC_POSE actions only; nothing is saved.

Phases follow W5 custom_task_validation task B (milk): approach -> lower ->
grasp -> lift, then hold the block in the air while the BDDL goal (Up) is checked.
"""

import argparse
import json
import os
import sys

if sys.platform == "win32":
    os.environ["MUJOCO_GL"] = "wgl"
    os.environ.setdefault("NUMBA_DISABLE_JIT", "1")
else:
    os.environ.setdefault("MUJOCO_GL", "egl")

import numpy as np
from scipy.spatial.transform import Rotation

if __package__:
    from .preview import create_env
else:
    from preview import create_env

# Top-down grasp: gripper z points down, fingers open along world y.
# This is close to the Panda's reset orientation, so no large wrist turn is needed.
TOP_DOWN = np.array([[0., 1., 0.], [1., 0., 0.], [0., 0., -1.]])
APPROACH_HEIGHT_M = 0.15   # above the block centre before lowering
LIFT_HEIGHT_M = 0.15       # Up needs block z >= 1.0 m; the block rests near 0.92 m
VERIFY_STEPS = 30


def block_pos(env, name):
    return env.env.object_states_dict[name].get_geom_state()["pos"].copy()


def eef_pose(env, obs):
    """EEF position (m) and extrinsic xyz Euler angles Rx, Ry, Rz (deg)."""
    site_id = env.env.robots[0].eef_site_id
    rotation = env.sim.data.site_xmat[site_id].reshape(3, 3)
    return {"xyz_m": [round(float(v), 4) for v in obs["robot0_eef_pos"]],
            "rxyz_deg": [round(float(v), 2)
                         for v in Rotation.from_matrix(rotation).as_euler("xyz", degrees=True)]}


def run_pickup(env, obs, target, on_step=None):
    """Pick up `target` (e.g. "red_block_1") from a fresh reset and keep holding it."""
    robot = env.env.robots[0]
    obj = env.env.objects_dict[target]
    others = [state for state in env.env.parsed_problem["initial_state"] if state[1] != target]
    steps = 0
    phases = []
    verify_goals = []

    def rotation_error():
        current = env.sim.data.site_xmat[robot.eef_site_id].reshape(3, 3)
        return Rotation.from_matrix(TOP_DOWN @ current.T).as_rotvec()

    def step_toward(goal_pos, gripper, phase):
        nonlocal obs, steps
        action = np.zeros(7, dtype=np.float32)
        # OSC_POSE scales inputs in [-1, 1] to 0.05 m and 0.5 rad per step.
        action[:3] = np.clip((goal_pos - obs["robot0_eef_pos"]) / 0.05, -0.5, 0.5)
        action[3:6] = np.clip(rotation_error() / 0.5, -0.5, 0.5)
        action[6] = gripper
        obs, _, _, _ = env.step(action)
        steps += 1
        goal = bool(env.check_success())
        if phase == "verify":
            verify_goals.append(goal)
        if on_step is not None:
            on_step(obs, steps, phase, goal)

    def move_to(goal_pos, gripper, phase, limit=200, tolerance=0.006, hold=False):
        goal_pos = np.asarray(goal_pos, dtype=float)
        start = steps
        for _ in range(limit):
            step_toward(goal_pos, gripper, phase)
            error = np.linalg.norm(goal_pos - obs["robot0_eef_pos"])
            if not hold and error < tolerance and np.linalg.norm(rotation_error()) < 0.08:
                break
        else:
            if not hold:
                raise RuntimeError("{}: EEF did not reach target (error {:.4f} m)".format(phase, error))
        row = {"phase": phase, "steps": steps - start, "eef": eef_pose(env, obs),
               "block_xyz_m": [round(float(v), 4) for v in block_pos(env, target)],
               "gripper_qpos": [round(float(v), 4) for v in obs["robot0_gripper_qpos"]],
               "goal": bool(env.check_success())}
        phases.append(row)
        print(json.dumps(row), flush=True)

    initial_goal = bool(env.check_success())
    move_to(obs["robot0_eef_pos"].copy(), -1., "settle", limit=20, hold=True)
    start_block = block_pos(env, target)
    grasp = start_block.copy()
    move_to(grasp + [0., 0., APPROACH_HEIGHT_M], -1., "approach")
    move_to(grasp, -1., "lower")
    move_to(grasp, 1., "grasp", limit=30, hold=True)
    grasped = bool(env.env._check_grasp(robot.gripper, obj))
    if not grasped:
        raise RuntimeError("grasp: both finger pads are not in contact with " + target)
    move_to(grasp + [0., 0., LIFT_HEIGHT_M], 1., "lift")
    move_to(obs["robot0_eef_pos"].copy(), 1., "verify", limit=VERIFY_STEPS, hold=True)
    return obs, {
        "target": target, "steps": steps,
        "initial_goal": initial_goal,
        "grasp_confirmed": grasped,
        "still_grasped": bool(env.env._check_grasp(robot.gripper, obj)),
        "lift_height_m": round(float(block_pos(env, target)[2] - start_block[2]), 4),
        "goal_true_throughout_verify": bool(verify_goals) and all(verify_goals),
        "final_goal": bool(env.check_success()),
        "other_blocks_in_place": all(bool(env.env._eval_predicate(s)) for s in others),
        "phases": phases,
    }


def pickup_success(result):
    """Target lifted (Up) while held, from a False start, other blocks untouched."""
    return (not result["initial_goal"] and result["grasp_confirmed"] and result["still_grasped"]
            and result["goal_true_throughout_verify"] and result["other_blocks_in_place"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", choices=("red", "green", "blue"), default="red")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--size", type=int, default=128, help="Camera resolution only.")
    args = parser.parse_args()
    env = create_env(resolution=args.size, seed=args.seed, ignore_done=True, task=args.task)
    try:
        obs = env.reset()
        print("Task:", env.rgb_task["language"], flush=True)
        _, result = run_pickup(env, obs, env.rgb_task["target_object"])
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        return 1
    finally:
        env.close()
    summary = {k: v for k, v in result.items() if k != "phases"}
    print(json.dumps(summary, indent=2))
    return 0 if pickup_success(result) else 1


if __name__ == "__main__":
    raise SystemExit(main())
