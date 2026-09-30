"""Test the new predicate's rejected states separately from the robot video."""

import json
from pathlib import Path

import test_custom_task_variants as base
import numpy as np
from scipy.spatial.transform import Rotation
from libero.libero.envs.env_wrapper import ControlEnv
from libero.libero.envs.predicates import get_predicate_fn_dict
from test_extended_custom_tasks import register_extensions


def main():
    register_extensions("E")
    env = ControlEnv(
        bddl_file_name=str(base.ROOT / "custom_tasks/custom_new_predicate_task.bddl"),
        use_camera_obs=False, has_offscreen_renderer=False,
    )
    try:
        env.seed(0)
        env.reset()
        # This is a predicate test, not the recorded Panda manipulation.
        base.probe_goal(env, "B")
        milk = env.env.object_states_dict["milk_1"]
        plate = env.env.object_states_dict["plate_1"]
        joint = env.env.objects_dict["milk_1"].joints[0]
        original = env.sim.data.get_joint_qpos(joint).copy()
        plate_pos = plate.get_geom_state()["pos"].copy()
        rows = []
        for name, dx, tilt in (("centered", 0., 0.), ("inside_1cm", .0099, 0.),
                               ("outside_1cm", .0101, 0.), ("off_center", .015, 0.),
                               ("tilted_20deg", 0., 20.)):
            qpos = original.copy()
            qpos[:2] = plate_pos[:2] + [dx, 0.]
            current = Rotation.from_quat(original[3:][[1, 2, 3, 0]])
            rotation = Rotation.from_euler("x", tilt, degrees=True) * current
            qpos[3:] = rotation.as_quat()[[3, 0, 1, 2]]
            env.sim.data.set_joint_qpos(joint, qpos)
            env.sim.forward()
            body_id = env.env.obj_body_id["milk_1"]
            axis_z = float(env.sim.data.body_xmat[body_id].reshape(3, 3)[2, 1])
            predicates = get_predicate_fn_dict()
            rows.append({"state": name, "xy_distance_m": round(float(np.linalg.norm(
                milk.get_geom_state()["pos"][:2] - plate_pos[:2])), 6),
                "milk_local_y_world_z": round(axis_z, 6),
                "on": bool(predicates["on"](milk, plate)),
                "centered_upright_on": bool(predicates["centereduprighton"](milk, plate))})
        expected = [True, True, False, False, False]
        if not all(row["on"] for row in rows):
            raise RuntimeError("The comparison must keep the existing On condition true.")
        if [row["centered_upright_on"] for row in rows] != expected:
            raise RuntimeError("New predicate did not reject the intended states.")
        result = {"test": "predicate_conditions", "direct_state_changes": True,
                  "part_of_robot_video": False, "conditions": rows}
        out = base.ROOT / "images/extended_task_validation/E_predicate_conditions.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2), flush=True)
    finally:
        env.close()


if __name__ == "__main__":
    main()
