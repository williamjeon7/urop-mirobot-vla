"""Panda pick up (or reach) of one RGB block with OSC_POSE actions only.

Phases follow W5 custom_task_validation task B (milk): approach -> lower ->
grasp -> lift, then hold the block in the air while the BDDL goal (Up) is checked.
`--mode reach` stops above the block instead (Mirobot check steps 1-2, W6 CHECKLIST 0).
Nothing is saved unless `--log` is given. The log is a Panda pose file (docs/W6/DIVISION.md 2):
tools/poses_to_gcode.py turns it into Mirobot G-code, tools/action_to_poses.py replays its actions.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

if sys.platform == "win32":
    os.environ["MUJOCO_GL"] = "wgl"
    os.environ.setdefault("NUMBA_DISABLE_JIT", "1")
else:
    os.environ.setdefault("MUJOCO_GL", "egl")

import numpy as np
from scipy.spatial.transform import Rotation

if __package__:
    from .preview import create_env
    from .scenarios import SCENARIOS, apply_scenario
else:
    from preview import create_env
    from scenarios import SCENARIOS, apply_scenario

REPO = Path(__file__).resolve().parents[3]
# Top-down grasp: gripper z points down, fingers open along world y.
# This is close to the Panda's reset orientation, so no large wrist turn is needed.
TOP_DOWN = np.array([[0., 1., 0.], [1., 0., 0.], [0., 0., -1.]])
APPROACH_HEIGHT_M = 0.15   # above the block centre before lowering
LIFT_HEIGHT_M = 0.15       # Up needs block z >= 1.0 m; the block rests near 0.92 m
# Grasp this far above the block centre. At the centre the Mirobot flange would go to
# Zt + s * (0.920 - 0.9092 m) = 63.5 mm, under run_gcode's 66 mm floor (W6 CHECKLIST 4).
GRASP_ABOVE_CENTRE_M = 0.015
VERIFY_STEPS = 30
# Reach mode hovers so the Mirobot fingertips stay 30 mm above its table (W5 CHECKLIST 9).
# Vertical alignment (docs/W5/TABLE_ALIGNMENT.md 4): fingertip height on Mirobot =
# s * (Panda grip z - touch point), touch point 0.9092 m, s 0.663.
PANDA_TOUCH_Z_M = 0.9092
MIROBOT_SCALE = 0.663
HOVER_TIP_MM = 30.0
HOVER_GRIP_Z_M = PANDA_TOUCH_Z_M + HOVER_TIP_MM / 1000 / MIROBOT_SCALE
HOVER_STEPS = 20
REACH_XY_TOLERANCE_M = 0.005


def block_pos(env, name):
    return env.env.object_states_dict[name].get_geom_state()["pos"].copy()


def eef_pose(env, obs):
    """EEF position (m) and extrinsic xyz Euler angles Rx, Ry, Rz (deg)."""
    site_id = env.env.robots[0].eef_site_id
    rotation = env.sim.data.site_xmat[site_id].reshape(3, 3)
    return {"xyz_m": [round(float(v), 4) for v in obs["robot0_eef_pos"]],
            "rxyz_deg": [round(float(v), 2)
                         for v in Rotation.from_matrix(rotation).as_euler("xyz", degrees=True)]}


class PandaMover:
    """Feedback OSC_POSE steps toward a top-down target; optional per-step record."""

    def __init__(self, env, obs, target, on_step=None, record=None):
        self.env, self.obs, self.target = env, obs, target
        self.robot = env.env.robots[0]
        self.on_step, self.record = on_step, record
        self.steps = 0
        self.phases = []
        self.verify_goals = []
        self.touched = set()

    def rotation_error(self):
        current = self.env.sim.data.site_xmat[self.robot.eef_site_id].reshape(3, 3)
        return Rotation.from_matrix(TOP_DOWN @ current.T).as_rotvec()

    def step_toward(self, goal_pos, gripper, phase):
        env = self.env
        action = np.zeros(7, dtype=np.float32)
        # OSC_POSE scales inputs in [-1, 1] to 0.05 m and 0.5 rad per step.
        action[:3] = np.clip((goal_pos - self.obs["robot0_eef_pos"]) / 0.05, -0.5, 0.5)
        action[3:6] = np.clip(self.rotation_error() / 0.5, -0.5, 0.5)
        action[6] = gripper
        self.obs, _, _, _ = env.step(action)
        self.steps += 1
        goal = bool(env.check_success())
        if phase == "verify":
            self.verify_goals.append(goal)
        for name, obj in env.env.objects_dict.items():
            if env.env.check_contact(self.robot.gripper, obj):
                self.touched.add(name)
        if self.record is not None:
            pose = eef_pose(env, self.obs)
            self.record.append({
                "step": self.steps, "phase": phase,
                "action": [float(v) for v in action],
                "eef_pos": [float(v) for v in self.obs["robot0_eef_pos"]],
                "eef_quat_xyzw": [float(v) for v in self.obs["robot0_eef_quat"]],
                "eef_rxyz_deg": pose["rxyz_deg"],
                "joint_pos": [float(env.sim.data.qpos[i]) for i in self.robot._ref_joint_pos_indexes],
                "gripper_qpos": [float(v) for v in self.obs["robot0_gripper_qpos"]],
                "goal": goal,
            })
        if self.on_step is not None:
            self.on_step(self.obs, self.steps, phase, goal)

    def move_to(self, goal_pos, gripper, phase, limit=200, tolerance=0.006, hold=False):
        goal_pos = np.asarray(goal_pos, dtype=float)
        start = self.steps
        for _ in range(limit):
            self.step_toward(goal_pos, gripper, phase)
            error = np.linalg.norm(goal_pos - self.obs["robot0_eef_pos"])
            if not hold and error < tolerance and np.linalg.norm(self.rotation_error()) < 0.08:
                break
        else:
            if not hold:
                raise RuntimeError("{}: EEF did not reach target (error {:.4f} m)".format(phase, error))
        row = {"phase": phase, "steps": self.steps - start, "eef": eef_pose(self.env, self.obs),
               "block_xyz_m": [round(float(v), 4) for v in block_pos(self.env, self.target)],
               "gripper_qpos": [round(float(v), 4) for v in self.obs["robot0_gripper_qpos"]],
               "goal": bool(self.env.check_success())}
        self.phases.append(row)
        print(json.dumps(row), flush=True)


OTHERS_MOVE_LIMIT_M = 0.01


def others_in_place(env, target):
    return all(bool(env.env._eval_predicate(s))
               for s in env.env.parsed_problem["initial_state"] if s[1] != target)


def others_positions(env, target):
    return {n: block_pos(env, n) for n in env.env.objects_dict if n != target}


def others_max_move(env, start):
    return max(float(np.linalg.norm(block_pos(env, n) - p)) for n, p in start.items())


def run_pickup(env, obs, target, on_step=None, record=None, check_regions=True,
               grasp_offset_m=GRASP_ABOVE_CENTRE_M):
    """Pick up `target` (e.g. "red_block_1") from a fresh reset and keep holding it.

    Other blocks must not move more than 1 cm. `check_regions=False` skips their BDDL
    `On region` check, for scenarios that start neighbours outside their regions.
    """
    mover = PandaMover(env, obs, target, on_step, record)
    obj = env.env.objects_dict[target]
    initial_goal = bool(env.check_success())
    mover.move_to(mover.obs["robot0_eef_pos"].copy(), -1., "settle", limit=20, hold=True)
    others_start = others_positions(env, target)
    start_block = block_pos(env, target)
    grasp = start_block + [0., 0., grasp_offset_m]
    mover.move_to(grasp + [0., 0., APPROACH_HEIGHT_M], -1., "approach")
    mover.move_to(grasp, -1., "lower")
    mover.move_to(grasp, 1., "grasp", limit=30, hold=True)
    grasped = bool(env.env._check_grasp(mover.robot.gripper, obj))
    if not grasped:
        raise RuntimeError("grasp: both finger pads are not in contact with " + target)
    mover.move_to(grasp + [0., 0., LIFT_HEIGHT_M], 1., "lift")
    mover.move_to(mover.obs["robot0_eef_pos"].copy(), 1., "verify", limit=VERIFY_STEPS, hold=True)
    return mover.obs, {
        "mode": "pickup", "target": target, "steps": mover.steps,
        "initial_goal": initial_goal,
        "grasp_confirmed": grasped,
        "still_grasped": bool(env.env._check_grasp(mover.robot.gripper, obj)),
        "lift_height_m": round(float(block_pos(env, target)[2] - start_block[2]), 4),
        "goal_true_throughout_verify": bool(mover.verify_goals) and all(mover.verify_goals),
        "final_goal": bool(env.check_success()),
        "others_max_move_m": round(others_max_move(env, others_start), 4),
        "other_blocks_in_place": (others_max_move(env, others_start) < OTHERS_MOVE_LIMIT_M
                                  and (not check_regions or others_in_place(env, target))),
        "phases": mover.phases,
    }


def run_reach(env, obs, target, on_step=None, record=None):
    """Hover over `target` without touching any block, then return to the start pose."""
    mover = PandaMover(env, obs, target, on_step, record)
    initial_goal = bool(env.check_success())
    mover.move_to(mover.obs["robot0_eef_pos"].copy(), -1., "settle", limit=20, hold=True)
    start_eef = mover.obs["robot0_eef_pos"].copy()
    block = block_pos(env, target)
    hover = np.array([block[0], block[1], HOVER_GRIP_Z_M])
    mover.move_to(block + [0., 0., APPROACH_HEIGHT_M], -1., "approach")
    mover.move_to(hover, -1., "hover")
    mover.move_to(hover, -1., "hover_hold", limit=HOVER_STEPS, hold=True)
    hover_eef = mover.obs["robot0_eef_pos"].copy()
    mover.move_to(block + [0., 0., APPROACH_HEIGHT_M], -1., "rise")
    mover.move_to(start_eef, -1., "return")
    return mover.obs, {
        "mode": "reach", "target": target, "steps": mover.steps,
        "initial_goal": initial_goal,
        "hover_xy_error_m": round(float(np.linalg.norm(hover_eef[:2] - block[:2])), 4),
        "hover_grip_z_m": round(float(hover_eef[2]), 4),
        "hover_tip_on_mirobot_mm": round((float(hover_eef[2]) - PANDA_TOUCH_Z_M) * 1000 * MIROBOT_SCALE, 1),
        "touched_blocks": sorted(mover.touched),
        "return_error_m": round(float(np.linalg.norm(mover.obs["robot0_eef_pos"] - start_eef)), 4),
        "final_goal": bool(env.check_success()),
        "other_blocks_in_place": others_in_place(env, target),
        "target_in_place": all(bool(env.env._eval_predicate(s))
                               for s in env.env.parsed_problem["initial_state"] if s[1] == target),
        "phases": mover.phases,
    }


def pickup_success(result):
    """Target lifted (Up) while held, from a False start, other blocks untouched."""
    return (not result["initial_goal"] and result["grasp_confirmed"] and result["still_grasped"]
            and result["goal_true_throughout_verify"] and result["other_blocks_in_place"])


def reach_success(result):
    """Hovered over the target without touching any block, and came back."""
    return (not result["initial_goal"] and result["hover_xy_error_m"] < REACH_XY_TOLERANCE_M
            and not result["touched_blocks"] and result["other_blocks_in_place"]
            and result["target_in_place"] and not result["final_goal"])


def write_log(path, env, args, result, record, start_pos, start_quat_xyzw):
    """Panda pose JSONL (docs/W6/DIVISION.md 2): a meta line, then one line per step."""
    path.parent.mkdir(parents=True, exist_ok=True)
    spec = env.rgb_task
    meta = {
        "format": "panda-poses/1",
        "source": "docs/W6/rgb_blocks/pickup.py", "mode": args.mode, "task": spec["name"],
        "instruction": spec["language"], "target": spec["target_object"], "seed": args.seed,
        "bddl": str(Path(spec["bddl_file"]).resolve().relative_to(REPO)),
        "register": "docs/W6/rgb_blocks/objects.py:register_blocks",
        "block_size_mm": env.rgb_size_mm,
        # The settle phase is already in the actions, so the translator adds no dummy steps.
        "settle": 0, "pos_unit": "m, world", "quat_order_raw": "xyzw",
        "point": "grip (robot0_eef_pos)", "rxyz": "scipy extrinsic xyz, deg, LIBERO frame",
        "joint_pos": "Panda 7 joints, rad (sim.data.qpos)",
        # Pair reference on the Panda side: the hand pose right before the first action.
        "start_eef_pos": [float(v) for v in start_pos],
        "start_eef_quat_xyzw": [float(v) for v in start_quat_xyzw],
        "scenario": getattr(args, "scenario", "none"),
    }
    with path.open("w", encoding="utf-8") as out:
        out.write(json.dumps({"meta": meta}, ensure_ascii=False) + "\n")
        for row in record:
            out.write(json.dumps(row) + "\n")
        summary = {k: v for k, v in result.items() if k != "phases"}
        out.write(json.dumps({"result": summary}, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", choices=("red", "green", "blue"), default="red")
    parser.add_argument("--mode", choices=("pickup", "reach"), default="pickup")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--scenario", choices=SCENARIOS, default="none",
                        help="Start layout: neighbours close to the target along y (pickup mode only).")
    parser.add_argument("--gap-mm", type=float, default=20.0,
                        help="Face-to-face gap between the target and its neighbours for --scenario.")
    parser.add_argument("--size", type=int, default=128, help="Camera resolution only.")
    parser.add_argument("--log", nargs="?", const="auto", type=str,
                        help="Write a JSONL log (default path data/pickup/<time>-<mode>-<task>-s<seed>.jsonl).")
    args = parser.parse_args()
    if args.scenario != "none" and args.mode != "pickup":
        parser.error("--scenario is for --mode pickup")
    env = create_env(resolution=args.size, seed=args.seed, ignore_done=True, task=args.task)
    record = [] if args.log else None
    try:
        obs = env.reset()
        start_pos, start_quat = obs["robot0_eef_pos"].copy(), obs["robot0_eef_quat"].copy()
        print("Task:", env.rgb_task["language"], "| mode:", args.mode, flush=True)
        target = env.rgb_task["target_object"]
        if args.mode == "pickup":
            moved = apply_scenario(env, args.scenario, target, args.gap_mm)
            if moved:
                print("Scenario", args.scenario, "moved", moved, flush=True)
            _, result = run_pickup(env, obs, target, record=record,
                                   check_regions=args.scenario == "none")
        else:
            _, result = run_reach(env, obs, target, record=record)
        if args.log:
            path = (REPO / "data" / "pickup" / "{}-{}-{}-s{}.jsonl".format(
                        time.strftime("%Y_%m_%d-%H_%M_%S"), args.mode, args.task, args.seed)
                    if args.log == "auto" else Path(args.log))
            write_log(path, env, args, result, record, start_pos, start_quat)
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        return 1
    finally:
        env.close()
    summary = {k: v for k, v in result.items() if k != "phases"}
    print(json.dumps(summary, indent=2))
    if args.log:
        print("saved", path)
    ok = pickup_success(result) if args.mode == "pickup" else reach_success(result)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
