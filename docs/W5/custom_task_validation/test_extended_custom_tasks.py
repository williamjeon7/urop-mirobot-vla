"""Record physical Panda successes for the four section-9 implementation cases."""

import argparse
import json
from pathlib import Path

# Reuse the Windows renderer/logging setup and frame helpers from section 8.
import test_custom_task_variants as base
import cv2
import numpy as np
from scipy.spatial.transform import Rotation
from libero.libero.envs.env_wrapper import OffScreenRenderEnv
import libero.libero.envs.objects.custom_validation_objects  # noqa: F401
import libero.libero.envs.problems.libero_custom_support  # noqa: F401


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "images" / "extended_task_validation"
CASES = {
    "C": {"bddl": "custom_new_object_task.bddl", "object": "custom_marker_box_1",
          "target": "plate_1", "place_offset": 0.092},
    "D": {"bddl": "custom_new_fixture_task.bddl", "object": "milk_1",
          "target": "raised_support_1_top_region", "place_offset": 0.102,
          "transfer_offset": 0.23, "verify_steps": 40,
          "contact_target": "raised_support_1", "dtype": float},
    "E": {"bddl": "custom_new_predicate_task.bddl", "object": "milk_1",
          "target": "plate_1", "place_offset": 0.106},
    "F": {"bddl": "custom_camera_control_task.bddl", "object": "milk_1",
          "target": "plate_1", "place_offset": 0.106, "camera": "custom_overview"},
}


def register_extensions(case):
    if case == "E":
        from libero.libero.envs.predicates import get_predicate_fn_dict
        from libero.libero.envs.predicates.custom_validation_predicates import CenteredUprightOn
        get_predicate_fn_dict()["centereduprighton"] = CenteredUprightOn()
    if case == "F":
        import libero.libero.envs.problems.libero_custom_camera_control  # noqa: F401


def frame(obs, camera, caption):
    rgb = obs[camera + "_image"][::-1]
    result = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    cv2.putText(result, caption, (8, 24), cv2.FONT_HERSHEY_SIMPLEX, .48,
                (255, 255, 255), 2, cv2.LINE_AA)
    return result


def save_image(path, obs, camera, caption):
    if not cv2.imwrite(str(path), frame(obs, camera, caption)):
        raise RuntimeError("Could not save {}".format(path))


def run_case(case, seed, size, out):
    register_extensions(case)
    config = CASES[case]
    camera = config.get("camera", "agentview")
    moving = config["object"]
    target_name = config["target"]
    env = OffScreenRenderEnv(
        bddl_file_name=str(ROOT / "custom_tasks" / config["bddl"]),
        camera_names=[camera], camera_heights=size, camera_widths=size, horizon=3000,
    )
    writer = None
    try:
        env.seed(seed)
        obs = env.reset()
        initial_goal = bool(env.check_success())
        initial_on = {}
        for condition in env.env.parsed_problem["initial_state"]:
            if condition[0].lower() == "on":
                initial_on["(On {} {})".format(*condition[1:])] = bool(
                    env.env.object_states_dict[condition[2]].check_ontop(
                        env.env.object_states_dict[condition[1]]))
        if initial_goal or not all(initial_on.values()):
            raise RuntimeError("{} has an invalid initial state.".format(case))
        save_image(out / (case + "_initial.png"), obs, camera,
                   "{} initial | goal=False".format(case))
        video = out / (case + "_robot_action.mp4")
        writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"mp4v"),
                                 10., (size, size))
        if not writer.isOpened():
            raise RuntimeError("Could not record {}".format(video))
        writer.write(frame(obs, camera, "{} initial | goal=False".format(case)))
        rotation = np.array([[0., 1., 0.], [1., 0., 0.], [0., 0., -1.]])
        site = env.env.robots[0].eef_site_id
        phases = []
        steps = 0
        verification = []

        def step(target, grip, phase):
            nonlocal obs, steps
            current = env.sim.data.site_xmat[site].reshape(3, 3)
            action = np.zeros(7, dtype=config.get("dtype", np.float32))
            action[:3] = np.clip((target - obs["robot0_eef_pos"]) / .05, -.5, .5)
            action[3:6] = np.clip(
                Rotation.from_matrix(rotation @ current.T).as_rotvec() / .5, -.5, .5)
            action[6] = grip
            obs, _, _, _ = env.step(action)
            steps += 1
            if phase == "verify":
                verification.append(bool(env.check_success()))
            if steps % 2 == 0:
                writer.write(frame(obs, camera, "{} {} | goal={}".format(
                    case, phase, env.check_success())))

        def move(target, grip, phase, limit=200, hold=False):
            target = np.asarray(target, dtype=float)
            start = steps
            for _ in range(limit):
                step(target, grip, phase)
                error = np.linalg.norm(target - obs["robot0_eef_pos"])
                angle = Rotation.from_matrix(
                    rotation @ env.sim.data.site_xmat[site].reshape(3, 3).T).magnitude()
                if not hold and error < .008 and angle < .08:
                    break
            phases.append({"phase": phase, "steps": steps - start,
                           "eef_error_m": round(float(error), 4),
                           "object_position_m": base.object_pos(env, moving).tolist(),
                           "goal": bool(env.check_success())})
            print(json.dumps(phases[-1]), flush=True)

        move(obs["robot0_eef_pos"].copy(), -1., "settle", limit=20, hold=True)
        unwanted_contacts = [
            name for name, obj in env.env.objects_dict.items()
            if name != moving and env.env.check_contact(env.env.objects_dict[moving], obj)
        ] + [
            name for name, obj in env.env.fixtures_dict.items()
            if name != "main_table" and env.env.check_contact(env.env.objects_dict[moving], obj)
        ]
        if case == "D":
            support = env.env.fixtures_dict["raised_support_1"]
            support_contacts = [name for name, obj in env.env.objects_dict.items()
                                if env.env.check_contact(support, obj)]
        else:
            support_contacts = []
        initial = base.object_pos(env, moving)
        target = env.env.object_states_dict[target_name].get_geom_state()["pos"].copy()
        grasp = initial + [0., 0., .027]
        transfer = target + [0., 0., config.get("transfer_offset", .22)]
        place = target + [0., 0., config["place_offset"]]
        move(grasp + [0., 0., .16], -1., "approach")
        move(grasp, -1., "lower")
        move(grasp, 1., "grasp", limit=35, hold=True)
        grasped = bool(env.env._check_grasp(env.env.robots[0].gripper,
                                          env.env.objects_dict[moving]))
        move(grasp + [0., 0., .18], 1., "lift")
        lift = float(base.object_pos(env, moving)[2] - initial[2])
        move(transfer, 1., "transfer")
        move(place, 1., "place")
        move(place, -1., "release", limit=30, hold=True)
        move(transfer, -1., "retreat")
        move(obs["robot0_eef_pos"].copy(), -1., "verify",
             limit=config.get("verify_steps", 30), hold=True)
        released = not bool(env.env._check_grasp(env.env.robots[0].gripper,
                                               env.env.objects_dict[moving]))
        contact_target = config.get("contact_target", target_name)
        contact = bool(env.env.object_states_dict[contact_target].check_contact(
            env.env.object_states_dict[moving]))
        goal = bool(env.check_success())
        save_image(out / (case + "_action_end.png"), obs, camera,
                   "{} action end | goal={}".format(case, goal))
        final_metrics = {"target_contact": contact}
        if case == "E":
            from libero.libero.envs.predicates import get_predicate_fn_dict
            milk = env.env.object_states_dict[moving]
            plate = env.env.object_states_dict[target_name]
            body_id = env.env.obj_body_id[moving]
            final_metrics.update({
                "base_on": bool(get_predicate_fn_dict()["on"](milk, plate)),
                "centered_upright_on": bool(get_predicate_fn_dict()["centereduprighton"](milk, plate)),
                "xy_center_distance_m": round(float(np.linalg.norm(
                    base.object_pos(env, moving)[:2] - base.object_pos(env, target_name)[:2])), 6),
                "milk_local_y_world_z": round(float(
                    env.sim.data.body_xmat[body_id].reshape(3, 3)[2, 1]), 6),
            })
        result = {
            "task": case, "bddl": "custom_tasks/" + config["bddl"], "seed": seed,
            "camera_size": size, "camera": camera, "initial_goal": initial_goal,
            "initial_on_checks": initial_on, "initial_unwanted_contacts": unwanted_contacts,
            "initial_unwanted_support_contacts": support_contacts,
            "object": moving, "target": target_name,
            "controller_kp": env.env.robots[0].controller.kp.tolist(),
            "action": {"steps": steps, "phases": phases,
                       "goal_after_robot_action": goal,
                       "verification_steps": len(verification),
                       "goal_true_throughout_verification": all(verification),
                       "gripper_released": released, "grasp_confirmed": grasped,
                       "lift_height_m": round(lift, 4),
                       "direct_object_state_changes_during_action": False,
                       "video": video.name},
            "final_metrics": final_metrics,
        }
        # Finish the MP4 before writing the JSON that certifies this recording.
        writer.release()
        writer = None
        (out / (case + "_result.json")).write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        if (not goal or not all(verification) or not released or not grasped
                or lift < .1 or not contact or unwanted_contacts or support_contacts):
            raise RuntimeError("{} did not finish a valid physical pick and place.".format(case))
        return result
    finally:
        if writer is not None:
            writer.release()
        env.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=tuple(CASES) + ("all",), default="all")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--size", type=int, default=512)
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    for case in CASES if args.case == "all" else (args.case,):
        print(json.dumps(run_case(case, args.seed, args.size, args.output),
                         ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
