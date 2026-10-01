"""Inspect the only task fixture and the Panda in the minimal drawer scene."""

import json
import test_custom_bddl as validation


def main():
    env = validation.make_env(seed=0, size=512)
    try:
        obs = env.reset()
        scene = validation.scene_info(env)
        joint_id = env.sim.model.joint_name2id(validation.JOINT_NAME)
        body_id = env.sim.model.jnt_bodyid[joint_id]
        local_axis = env.sim.model.jnt_axis[joint_id]
        world_axis = env.sim.data.body_xmat[body_id].reshape(3, 3) @ local_axis
        handle_id = env.sim.model.geom_name2id("wooden_cabinet_1_g29")
        result = {"scene": scene, "eef_position_m": obs["robot0_eef_pos"].tolist(),
                  "initial_goal": bool(env.check_success()),
                  "initial_checks": validation.init_checks(env),
                  "drawer_joint": validation.JOINT_NAME,
                  "drawer_joint_range_m": env.sim.model.jnt_range[joint_id].tolist(),
                  "drawer_joint_qpos_m": float(env.sim.data.get_joint_qpos(validation.JOINT_NAME)),
                  "drawer_joint_local_axis": local_axis.tolist(),
                  "drawer_joint_world_axis": world_axis.tolist(),
                  "handle_geom": "wooden_cabinet_1_g29",
                  "handle_position_m": env.sim.data.geom_xpos[handle_id].tolist()}
        validation.IMAGES.mkdir(parents=True, exist_ok=True)
        output = validation.IMAGES / "panda_drawer_info.json"
        output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2), flush=True)
        print("Saved:", output, flush=True)
    finally:
        env.close()


if __name__ == "__main__":
    main()
