"""Generate LIBERO OSC_POSE labels by following measured poses on an empty table.

The simulator supplies action dynamics only. It supplies no training images and
does not pretend that its block layout or grasp is the recorded real scene.
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np

from common.rotation import quat_xyzw_to_wxyz
from common.servo import pose_gap, servo_action


def create_translator():
    os.environ.setdefault('MUJOCO_GL', 'egl')
    os.environ.setdefault('HF_HUB_OFFLINE', '1')
    from robosuite.controllers import load_controller_config
    from robosuite.environments.manipulation.single_arm_env import SingleArmEnv
    from robosuite.models.tasks import ManipulationTask
    from libero.libero import get_libero_path
    from libero.libero.envs.arenas import TableArena
    from libero.libero.envs.robots import MountedPanda  # noqa: F401; registers LIBERO robot

    class EmptyTablePanda(SingleArmEnv):
        def __init__(self):
            self.table_full_size = (1.0, 1.2, 0.05)
            self.table_offset = (0.0, 0.0, 0.90)
            super().__init__(robots='MountedPanda',
                controller_configs=load_controller_config(default_controller='OSC_POSE'),
                initialization_noise=None, use_camera_obs=False, has_renderer=False,
                has_offscreen_renderer=False, control_freq=20, horizon=100000,
                ignore_done=True)

        def _load_model(self):
            super()._load_model()
            robot = self.robots[0].robot_model
            robot.set_base_xpos(robot.base_xpos_offset['table'](self.table_full_size[0]))
            arena = TableArena(table_full_size=self.table_full_size,
                table_offset=self.table_offset, table_friction=(0.6, 0.005, 0.0001),
                xml=str(Path(get_libero_path('assets'))/'scenes/libero_tabletop_base_style.xml'),
                floor_style='light-gray', wall_style='light-gray-plaster')
            arena.set_origin([0, 0, 0])
            self.model = ManipulationTask(mujoco_arena=arena,
                                         mujoco_robots=[robot], mujoco_objects=[])

        def reward(self, action=None):
            return 0.0

        def _check_success(self):
            return False

    return EmptyTablePanda()


def follow_actions(aligned, reference, scale, env_factory=create_translator):
    """Return action[k], targeting measured pose[k+1] from simulator obs[k]."""
    positions = np.asarray(aligned['positions'])
    quaternions = np.asarray(aligned['quaternions_wxyz'])
    gripper = np.asarray(aligned['gripper_actions'])
    if (positions.shape != (len(gripper)+1, 3) or
            quaternions.shape != (len(gripper)+1, 4)):
        raise ValueError('Pose arrays need one extra next-action target.')
    env = env_factory()
    try:
        obs = env.reset()
        q = quat_xyzw_to_wxyz(obs['robot0_eef_quat'])
        dp, dq = pose_gap(obs['robot0_eef_pos'], q,
                         reference['start_eef_pos'],
                         quat_xyzw_to_wxyz(reference['start_eef_quat_xyzw']))
        if dp > .001 or dq > .1:
            raise ValueError('Translator reset differs from the recorded mapping reference.')
        # Reach the first recorded physical pose before pairing any action/image.
        # The reset hand is tilted ~3.25 degrees relative to the real home pose.
        warmup = 0
        for warmup in range(101):
            q = quat_xyzw_to_wxyz(obs['robot0_eef_quat'])
            dp, dq = pose_gap(obs['robot0_eef_pos'], q, positions[0], quaternions[0])
            if dp <= .002 and dq <= .1:
                break
            if warmup == 100:
                raise ValueError(f'Translator warmup failed: {dp*1000:.3f} mm, {dq:.3f} deg.')
            action = servo_action(obs['robot0_eef_pos'], q, positions[0],
                                  quaternions[0], float(gripper[0]))
            obs, _, _, _ = env.step(action)
        actions, gaps = [], []
        for k, grip in enumerate(gripper):
            q = quat_xyzw_to_wxyz(obs['robot0_eef_quat'])
            dp, dq = pose_gap(obs['robot0_eef_pos'], q, positions[k], quaternions[k])
            gaps.append([dp*1000*scale, dq])
            action = servo_action(obs['robot0_eef_pos'], q,
                                  positions[k+1], quaternions[k+1], float(grip))
            actions.append(action)
            obs, _, _, _ = env.step(action)
        actions, gaps = np.asarray(actions, np.float32), np.asarray(gaps, np.float64)
        if not np.isfinite(actions).all() or not np.isfinite(gaps).all():
            raise ValueError('Non-finite action labels or tracking errors.')
        if np.max(np.abs(actions)) > 1.000001:
            raise ValueError('OSC_POSE action outside [-1,1].')
        return actions, gaps, dict(warmup_steps=warmup,
            method='LIBERO MountedPanda OSC_POSE, empty table, target pose[k+1], 20 Hz',
            max_follow_mm=float(gaps[:, 0].max()), max_follow_deg=float(gaps[:, 1].max()),
            follow_position_5mm_passed=bool((gaps[:, 0] <= 5).all()),
            follow_rotation_2deg_passed=bool((gaps[:, 1] <= 2).all()),
            simulator_images_used=False, simulator_grasp_evaluated=False)
    finally:
        env.close()
