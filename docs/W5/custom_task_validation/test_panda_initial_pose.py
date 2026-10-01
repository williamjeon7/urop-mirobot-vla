"""Render the LIBERO Panda's nominal pose on an empty table, without loading BDDL."""

import logging
import os
from pathlib import Path
import shutil

os.environ["MUJOCO_GL"] = "wgl"
os.environ.setdefault("NUMBA_DISABLE_JIT", "1")

ROOT = Path(__file__).resolve().parent
_file_handler = logging.FileHandler


def _workspace_file_handler(filename, *args, **kwargs):
    if filename == "/tmp/robosuite.log":
        filename = str(ROOT / "robosuite.log")
    return _file_handler(filename, *args, **kwargs)


logging.FileHandler = _workspace_file_handler

import cv2  # noqa: E402
import numpy as np  # noqa: E402
from robosuite.controllers import load_controller_config  # noqa: E402
from robosuite.environments.manipulation.single_arm_env import SingleArmEnv  # noqa: E402
from robosuite.models.tasks import ManipulationTask  # noqa: E402
from libero.libero import get_libero_path  # noqa: E402
from libero.libero.envs.arenas import TableArena  # noqa: E402
from libero.libero.envs.robots import MountedPanda  # noqa: E402, F401


class PandaInitialPoseEnv(SingleArmEnv):
    def __init__(self):
        # Use the same dimensions, top height and robot base as LIBERO tabletop.
        self.table_full_size = (1.0, 1.2, 0.05)
        self.table_offset = (0.0, 0.0, 0.90)
        super().__init__(
            robots="MountedPanda",
            controller_configs=load_controller_config(default_controller="OSC_POSE"),
            initialization_noise=None,
            use_camera_obs=True,
            has_renderer=False,
            has_offscreen_renderer=True,
            camera_names="initial_pose_view",
            camera_heights=512,
            camera_widths=512,
            control_freq=20,
        )

    def _load_model(self):
        super()._load_model()
        robot = self.robots[0].robot_model
        robot.set_base_xpos(robot.base_xpos_offset["table"](self.table_full_size[0]))
        arena = TableArena(
            table_full_size=self.table_full_size,
            table_offset=self.table_offset,
            table_friction=(0.6, 0.005, 0.0001),
            xml=str(Path(get_libero_path("assets")) / "scenes" /
                    "libero_tabletop_base_style.xml"),
            floor_style="light-gray",
            wall_style="light-gray-plaster",
        )
        arena.set_origin([0, 0, 0])
        arena.set_camera(
            "initial_pose_view",
            pos=[1.3, 1.2, 1.9],
            quat=[0.3703229234538559, 0.25072082555023156,
                  0.501441651100463, 0.7406458469077116],
        )
        self.model = ManipulationTask(
            mujoco_arena=arena,
            mujoco_robots=[robot],
            mujoco_objects=[],
        )

    def reward(self, action=None):
        return 0.0

    def _check_success(self):
        # This scene has no task or BDDL goal to evaluate.
        return False


def main():
    env = PandaInitialPoseEnv()
    try:
        obs = env.reset()
        if len(env.model.mujoco_objects) != 0:
            raise RuntimeError("The initial-pose scene must contain no task objects.")
        nominal = env.robots[0].robot_model.init_qpos
        measured = env.sim.data.qpos[env.robots[0]._ref_joint_pos_indexes]
        if not np.allclose(measured, nominal, atol=1e-8):
            raise RuntimeError("Robot reset did not use the nominal initial pose.")
        image = ROOT / "images" / "panda_initial_pose.png"
        image.parent.mkdir(parents=True, exist_ok=True)
        frame = cv2.cvtColor(obs["initial_pose_view_image"][::-1], cv2.COLOR_RGB2BGR)
        if not cv2.imwrite(str(image), frame):
            raise RuntimeError("Could not save {}".format(image))
        shared_image = ROOT.parent / "images" / image.name
        shared_image.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(image), str(shared_image))
        table_height = env.sim.data.site_xpos[
            env.sim.model.site_name2id("table_top")][2]
        print("Nominal Panda joint positions (rad):", measured.tolist(), flush=True)
        print("Tabletop height (m):", round(float(table_height), 3), flush=True)
        print("Task objects:", len(env.model.mujoco_objects), flush=True)
        print("Saved:", image, flush=True)
        print("Document copy:", shared_image, flush=True)
    finally:
        env.close()


if __name__ == "__main__":
    main()
