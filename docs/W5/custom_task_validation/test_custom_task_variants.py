"""Record Panda actions and verify two custom BDDL tasks at seed 0."""

import argparse
import json
import logging
import os
from pathlib import Path

os.environ.setdefault("MUJOCO_GL", "wgl")
# Numba JIT initialization is prohibitively slow in the Windows LIBERO setup.
os.environ.setdefault("NUMBA_DISABLE_JIT", "1")

# robosuite 1.4 writes to /tmp/robosuite.log even on Windows. Keep that log
# beside the existing test scripts so the check is reproducible here.
_file_handler = logging.FileHandler


def _workspace_file_handler(filename, *args, **kwargs):
    if filename == "/tmp/robosuite.log":
        filename = str(Path(__file__).resolve().parent / "robosuite.log")
    return _file_handler(filename, *args, **kwargs)


logging.FileHandler = _workspace_file_handler

import cv2  # noqa: E402
import numpy as np  # noqa: E402
from scipy.spatial.transform import Rotation  # noqa: E402
from libero.libero.envs.env_wrapper import OffScreenRenderEnv  # noqa: E402


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "images" / "custom_task_validation"
TASKS = {
    "A": ("custom_goal_change.bddl", "plate_1", "main_table_stove_front_region"),
    "B": ("custom_milk_task.bddl", "milk_1", "plate_1"),
}


def frame_from(obs, caption):
    frame = cv2.cvtColor(obs["agentview_image"][::-1], cv2.COLOR_RGB2BGR)
    cv2.putText(frame, caption, (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.48,
                (255, 255, 255), 2, cv2.LINE_AA)
    return frame


def save_frame(path, obs, caption):
    if not cv2.imwrite(str(path), frame_from(obs, caption)):
        raise RuntimeError("Could not save image: {}".format(path))


def object_pos(env, name):
    return env.env.object_states_dict[name].get_geom_state()["pos"].copy()


def run_robot_attempt(env, obs, task, video_path):
    """Move the real Panda using feedback on position and grip-site orientation."""
    target_rotation = (np.diag([1., -1., -1.]) if task == "A" else
                       np.array([[0., 1., 0.], [1., 0., 0.], [0., 0., -1.]]))
    site_id = env.env.robots[0].eef_site_id
    size = obs["agentview_image"].shape[0]
    writer = cv2.VideoWriter(str(video_path), cv2.VideoWriter_fourcc(*"mp4v"),
                             10.0, (size, size))
    if not writer.isOpened():
        raise RuntimeError("Could not open video writer: {}".format(video_path))
    steps = 0
    phases = []
    verification_goals = []
    grasp_confirmed = False
    lift_height = 0.0
    object_contact_steps = 0
    push_heights = []

    def step_toward(target, gripper, phase):
        nonlocal obs, steps, object_contact_steps
        current = env.sim.data.site_xmat[site_id].reshape(3, 3)
        rotation_error = Rotation.from_matrix(target_rotation @ current.T).as_rotvec()
        action = np.zeros(7, dtype=float if task == "A" else np.float32)
        limit = 0.4 if task == "A" else 0.5
        action[:3] = np.clip((target - obs["robot0_eef_pos"]) / 0.05, -limit, limit)
        action[3:6] = np.clip(rotation_error / 0.5, -limit, limit)
        action[6] = gripper
        obs, _, _, _ = env.step(action)
        steps += 1
        object_contact_steps += int(env.env.check_contact(
            env.env.robots[0].gripper, env.env.objects_dict[TASKS[task][1]]))
        if task == "A" and phase.startswith("push"):
            push_heights.append(float(object_pos(env, "plate_1")[2]))
        if phase == "verify":
            verification_goals.append(bool(env.check_success()))
        if steps % 2 == 0:
            writer.write(frame_from(obs, "{} {} | goal={}".format(task, phase, env.check_success())))

    def move_to(target, gripper, phase, limit=200, tolerance=0.008, hold=False):
        target = np.asarray(target, dtype=float)
        start = steps
        for _ in range(limit):
            step_toward(target, gripper, phase)
            error = np.linalg.norm(target - obs["robot0_eef_pos"])
            rotation = Rotation.from_matrix(
                target_rotation @ env.sim.data.site_xmat[site_id].reshape(3, 3).T).magnitude()
            if not hold and error < tolerance and rotation < 0.08:
                break
        result = {"phase": phase, "steps": steps - start,
                  "eef_error_m": round(float(error), 4),
                  "eef_position_m": obs["robot0_eef_pos"].tolist(),
                  "goal": bool(env.check_success()),
                  "object_position_m": object_pos(env, TASKS[task][1]).tolist(),
                  "gripper_qpos": obs["robot0_gripper_qpos"].tolist()}
        result["robot_contacts"] = sorted(set(
            (env.sim.model.geom_id2name(c.geom1) or "") + " / " +
            (env.sim.model.geom_id2name(c.geom2) or "")
            for c in env.sim.data.contact[:env.sim.data.ncon]
            if any((env.sim.model.geom_id2name(g) or "").startswith(("robot0", "gripper0"))
                   for g in (c.geom1, c.geom2))))
        phases.append(result)
        print(json.dumps(result), flush=True)

    try:
        writer.write(frame_from(obs, "{} initial | goal={}".format(task, env.check_success())))
        move_to(obs["robot0_eef_pos"].copy(), 1. if task == "A" else -1.,
                "settle", limit=20, hold=True)
        plate = object_pos(env, "plate_1")
        if task == "B":
            milk = object_pos(env, "milk_1")
            grasp = milk + [0., 0., 0.027]
            move_to(grasp + [0., 0., 0.16], -1., "approach")
            move_to(grasp, -1., "lower")
            move_to(grasp, 1., "grasp", limit=35, hold=True)
            grasp_confirmed = bool(env.env._check_grasp(
                env.env.robots[0].gripper, env.env.objects_dict["milk_1"]))
            move_to(grasp + [0., 0., 0.18], 1., "lift")
            lift_height = float(object_pos(env, "milk_1")[2] - milk[2])
            move_to(plate + [0., 0., 0.22], 1., "transfer")
            move_to(plate + [0., 0., 0.106], 1., "place")
            move_to(plate + [0., 0., 0.106], -1., "release", limit=30, hold=True)
            move_to(plate + [0., 0., 0.22], -1., "retreat")
        else:
            target = env.sim.data.site_xpos[env.sim.model.site_name2id(
                "main_table_stove_front_region")].copy()
            # Maintain frictional contact on the plate surface; do not lift it.
            point = plate + [0., 0., 0.008]
            move_to(point + [0., 0., 0.18], 1., "approach", limit=180, tolerance=0.005)
            move_to(point, 1., "contact", limit=180, tolerance=0.005)
            move_to(point, 1., "contact_hold", limit=30, hold=True)
            destination = point.copy()
            destination[1] = target[1]
            for waypoint in np.linspace(point, destination, 220):
                step_toward(waypoint, 1., "push_y")
            move_to(destination, 1., "push_y_hold", limit=25, hold=True)
            endpoint = destination.copy()
            endpoint[0] = target[0]
            for waypoint in np.linspace(destination, endpoint, 160):
                step_toward(waypoint, 1., "push_x")
            move_to(endpoint, 1., "push_x_hold", limit=25, hold=True)
            move_to(obs["robot0_eef_pos"] + [0., 0., 0.18], 1., "retreat",
                    limit=180, tolerance=0.005)
        move_to(obs["robot0_eef_pos"].copy(), -1., "verify",
                limit=40 if task == "A" else 30, hold=True)
    finally:
        writer.release()
    return obs, {"steps": steps, "phases": phases,
                 "goal_after_robot_action": bool(env.check_success()),
                 "verification_steps": len(verification_goals),
                 "goal_true_throughout_verification": all(verification_goals),
                 "gripper_released": not bool(env.env._check_grasp(
                     env.env.robots[0].gripper, env.env.objects_dict[TASKS[task][1]])),
                 "grasp_confirmed": grasp_confirmed if task == "B" else None,
                 "lift_height_m": round(lift_height, 4) if task == "B" else None,
                 "direct_object_state_changes_during_action": False,
                 "object_contact_steps": object_contact_steps,
                 "push_object_z_range_m": [round(min(push_heights), 5), round(max(push_heights), 5)]
                     if push_heights else None,
                 "control_frequency_hz": 20, "video_frequency_hz": 10,
                 "video": video_path.name}


def probe_goal(env, task):
    """Change MuJoCo state directly to test the BDDL predicate in isolation."""
    # Let objects rest on the table before testing a directly constructed state.
    for _ in range(20):
        env.step(np.array([0., 0., 0., 0., 0., 0., -1.]))
    moving = TASKS[task][1]
    joint = env.env.objects_dict[moving].joints[0]
    original = env.sim.data.get_joint_qpos(joint).copy()
    before = bool(env.check_success())
    if task == "A":
        target = env.sim.data.site_xpos[
            env.sim.model.site_name2id("main_table_stove_front_region")].copy()
        offsets = [0.0]
    else:
        target = object_pos(env, "plate_1")
        # Plate centre surface is about 6 mm above its body; milk bottom is
        # 69.75 mm below its body. Avoid deeply overlapping collision shapes.
        offsets = [0.0755, 0.0758, 0.076]
    success = False
    chosen = None
    for dz in offsets:
        qpos = original.copy()
        qpos[:2] = target[:2]
        qpos[2] = (original[2] if task == "A" else target[2] + dz)
        env.sim.data.set_joint_qpos(joint, qpos)
        env.sim.forward()
        if env.check_success():
            for _ in range(30):
                env.step(np.array([0., 0., 0., 0., 0., 0., -1.]))
            success = bool(env.check_success())
            chosen = [round(float(v), 5) for v in object_pos(env, moving)]
            if success:
                break
    return {"goal_before_direct_state_change": before,
            "goal_after_direct_state_change": bool(success),
            "position_after_settling_m": chosen, "settling_steps": 30}


def run_one(task, seed, size):
    bddl = ROOT / "custom_tasks" / TASKS[task][0]
    env = OffScreenRenderEnv(bddl_file_name=str(bddl),
                             camera_heights=size, camera_widths=size,
                             camera_names=["agentview"], horizon=3000)
    try:
        env.seed(seed)
        obs = env.reset()
        expected_objects = {"plate_1"} if task == "A" else {"plate_1", "milk_1"}
        # LIBERO implements main_table as the arena and omits it from fixtures_dict.
        expected_fixtures = {"flat_stove_1"} if task == "A" else set()
        if (set(env.env.objects_dict) != expected_objects
                or set(env.env.fixtures_dict) != expected_fixtures
                or env.env.workspace_name != "main_table"):
            raise RuntimeError("Task {} must contain only its required scene elements.".format(task))
        initial = bool(env.check_success())
        if TASKS[task][1] not in env.env.objects_dict:
            raise RuntimeError("Missing object: {}".format(TASKS[task][1]))
        region_name = ("main_table_plate_region" if task == "A"
                       else "main_table_milk_region")
        initial_region_valid = bool(
            env.env.object_states_dict[region_name].check_ontop(
                env.env.object_states_dict[TASKS[task][1]]))
        initial_on_checks = {}
        for condition in env.env.parsed_problem["initial_state"]:
            if condition[0].lower() == "on":
                name = "(On {} {})".format(condition[1], condition[2])
                initial_on_checks[name] = bool(
                    env.env.object_states_dict[condition[2]].check_ontop(
                        env.env.object_states_dict[condition[1]]))
        moving_object = env.env.objects_dict[TASKS[task][1]]
        unwanted_contacts = [
            name for name, obj in env.env.objects_dict.items()
            if name != TASKS[task][1] and env.env.check_contact(moving_object, obj)
        ] + [
            name for name, obj in env.env.fixtures_dict.items()
            if name != "main_table" and env.env.check_contact(moving_object, obj)
        ]
        save_frame(OUT / "{}_initial.png".format(task), obs,
                   "{} reset | goal={}".format(task, initial))
        obs, action_result = run_robot_attempt(
            env, obs, task, OUT / "{}_robot_action.mp4".format(task))
        save_frame(OUT / "{}_action_end.png".format(task), obs,
                   "{} action end | goal={}".format(task, env.check_success()))
        # A second reset ensures that the predicate probe is independent of the robot attempt.
        env.seed(seed)
        env.reset()
        predicate_result = probe_goal(env, task)
        probe_obs = env.env._get_observations(force_update=True)
        save_frame(OUT / "{}_predicate_probe.png".format(task), probe_obs,
                   "{} direct state | goal={}".format(
                       task, predicate_result["goal_after_direct_state_change"]))
        return {"task": task, "bddl": str(bddl.relative_to(ROOT)), "seed": seed,
                "camera_size": size, "initial_goal": initial,
                "initial_region_valid": initial_region_valid,
                "initial_on_checks": initial_on_checks,
                "initial_unwanted_contacts": unwanted_contacts,
                "objects": list(env.env.objects_dict),
                "fixtures": list(env.env.fixtures_dict),
                "workspace": env.env.workspace_name,
                "action": action_result, "predicate_probe": predicate_result}
    finally:
        env.close()


def main():
    global OUT
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", choices=("A", "B", "both"), default="both")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--size", type=int, default=512)
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    OUT = args.output.resolve()
    OUT.mkdir(parents=True, exist_ok=True)
    names = TASKS if args.task == "both" else (args.task,)
    for task in names:
        result = run_one(task, args.seed, args.size)
        path = OUT / "{}_result.json".format(task)
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
        action = result["action"]
        if (result["initial_goal"] or not result["initial_region_valid"]
                or len(result["initial_on_checks"]) != 2
                or not all(result["initial_on_checks"].values())
                or result["initial_unwanted_contacts"]
                or not action["goal_after_robot_action"]
                or not action["goal_true_throughout_verification"]
                or not action["gripper_released"]
                or not result["predicate_probe"]["goal_after_direct_state_change"]):
            raise RuntimeError("Task {} did not reach its goal through robot actions.".format(task))
        if task == "B" and (not action["grasp_confirmed"] or action["lift_height_m"] < 0.1):
            raise RuntimeError("Milk was not grasped and lifted before placement.")


if __name__ == "__main__":
    main()
