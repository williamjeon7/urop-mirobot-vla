"""Check a changed table size at reset; this does not run a manipulation task."""

import test_custom_task_variants as base
import numpy as np
from libero.libero.envs.env_wrapper import ControlEnv


def main():
    table_size = (1.1, 1.3, 0.05)
    env = ControlEnv(
        bddl_file_name=str(base.ROOT / "custom_tasks/custom_milk_task.bddl"),
        robots=["Panda"], initialization_noise=None,
        table_full_size=table_size,
        use_camera_obs=False, has_offscreen_renderer=False,
    )
    try:
        env.seed(0)
        env.reset()
        collision_id = env.sim.model.geom_name2id("table_collision")
        half_size = env.sim.model.geom_size[collision_id]
        robot_model = env.env.robots[0].robot_model
        root_id = env.sim.model.body_name2id(robot_model.root_body)
        base_position = env.sim.model.body_pos[root_id]
        assert tuple(env.env.table_full_size) == table_size
        assert np.allclose(half_size, np.asarray(table_size) / 2)
        assert np.isclose(base_position[0], -0.16 - table_size[0] / 2)
        print("Table full size (m):", env.env.table_full_size)
        print("Collision half size (m):", half_size.tolist())
        print("Robot base x (m):", float(base_position[0]))
        print("Configuration and reset verified; no robot action was run.")
    finally:
        env.close()


if __name__ == "__main__":
    main()
