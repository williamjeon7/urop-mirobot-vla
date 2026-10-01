"""Open the minimal scene's middle drawer using Panda actions only."""

import argparse
import json

import test_custom_bddl as validation
import cv2
import numpy as np
from scipy.spatial.transform import Rotation

JOINT_NAME = validation.JOINT_NAME
HANDLE_GEOM = "wooden_cabinet_1_g29"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--headless", action="store_true", help="Run without an OpenCV window.")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--size", type=int, default=512)
    args = parser.parse_args()
    env = validation.make_env(args.seed, args.size)
    writer = None
    try:
        obs = env.reset()
        initial_goal = bool(env.check_success())
        scene = validation.scene_info(env)
        initial_checks = validation.init_checks(env)
        if initial_goal or not all(initial_checks.values()):
            raise RuntimeError("Start with a correctly placed, closed middle drawer.")
        validation.save_frame(validation.IMAGES / "panda_drawer_action_initial.png", obs,
                              "Panda drawer action: initial | goal=False")
        video_path = validation.IMAGES / "panda_drawer_action.mp4"
        writer = validation.open_writer(video_path, args.size, fps=10)
        writer.write(validation.frame_from(obs, "Panda drawer action: initial | goal=False"))
        initial_joint = float(env.sim.data.get_joint_qpos(JOINT_NAME))
        print("Initial goal success:", initial_goal, flush=True)
        joint_id = env.sim.model.joint_name2id(JOINT_NAME)
        body_id = env.sim.model.jnt_bodyid[joint_id]
        rotation = env.sim.data.body_xmat[body_id].reshape(3, 3)
        axis_world = rotation @ env.sim.model.jnt_axis[joint_id]
        opening_direction = -axis_world / np.linalg.norm(axis_world)
        handle_id = env.sim.model.geom_name2id(HANDLE_GEOM)
        handle_pos = env.sim.data.geom_xpos[handle_id].copy()
        print("Handle position:", handle_pos, flush=True)
        print("Opening direction:", opening_direction, flush=True)
        tool_z = -opening_direction
        tool_x = np.array([0.0, 0.0, 1.0])
        tool_y = np.cross(tool_z, tool_x)
        target_rotation = np.column_stack((tool_x, tool_y, tool_z))
        step_count = 0
        eef_site_id = env.env.robots[0].eef_site_id
        phases = []
        verification_goals = []
        grasp_confirmed = False

        def eef_rotation():
            return env.sim.data.site_xmat[eef_site_id].reshape(3, 3).copy()

        def step_toward(target, gripper, phase):
            nonlocal obs, step_count
            rotation_error = Rotation.from_matrix(target_rotation @ eef_rotation().T).as_rotvec()
            action = np.zeros(7, dtype=np.float32)
            action[:3] = np.clip((target - obs["robot0_eef_pos"]) / .05, -.4, .4)
            action[3:6] = np.clip(rotation_error / .5, -.4, .4)
            action[6] = gripper
            obs, _, _, _ = env.step(action)
            step_count += 1
            if phase == "Verify":
                verification_goals.append(bool(env.check_success()))
            if step_count % 2 == 0:
                writer.write(validation.frame_from(obs, "{} | goal={}".format(phase, env.check_success())))
            if step_count % 25 == 0:
                print("{} | Step: {} | Joint: {:.4f} | Success: {}".format(
                    phase, step_count, env.sim.data.get_joint_qpos(JOINT_NAME), env.check_success()), flush=True)
            if not args.headless:
                cv2.imshow("Panda Drawer Action", validation.frame_from(obs, "{} | goal={}".format(
                    phase, env.check_success())))
                if cv2.waitKey(1) & 0xFF in (ord("q"), ord("Q"), 27):
                    raise KeyboardInterrupt

        def move_to(target, gripper, phase, max_steps=200, hold=False):
            target = np.asarray(target, dtype=float)
            start_step = step_count
            for _ in range(max_steps):
                step_toward(target, gripper, phase)
                error = np.linalg.norm(target - obs["robot0_eef_pos"])
                rotation_error = Rotation.from_matrix(target_rotation @ eef_rotation().T).magnitude()
                if not hold and error < .015 and rotation_error < .12:
                    break
            if not hold and (error >= .015 or rotation_error >= .12):
                raise RuntimeError("{}: EEF error={:.4f} m, rotation error={:.4f} rad".format(
                    phase, error, rotation_error))
            phases.append({"phase": phase, "steps": step_count - start_step,
                           "joint_qpos_m": float(env.sim.data.get_joint_qpos(JOINT_NAME)),
                           "goal": bool(env.check_success())})

        pregrasp = handle_pos + .10 * opening_direction
        above = pregrasp + np.array([0., 0., .15])
        move_to(above, -1., "Above handle")
        move_to(pregrasp, -1., "Before handle")
        move_to(handle_pos, -1., "Approach handle")
        move_to(handle_pos, 1., "Close gripper", max_steps=30, hold=True)
        cabinet = env.env.fixtures_dict["wooden_cabinet_1"]
        gripper = env.env.robots[0].gripper
        # Check both finger pads against the middle drawer's handle geometry.
        grasp_confirmed = bool(env.env._check_grasp(gripper, HANDLE_GEOM))
        start = obs["robot0_eef_pos"].copy()
        start_step = step_count
        for distance in np.linspace(0., .18, 180):
            step_toward(start + distance * opening_direction, 1., "Pull drawer")
            if env.check_success():
                break
        phases.append({"phase": "Pull drawer", "steps": step_count - start_step,
                       "joint_qpos_m": float(env.sim.data.get_joint_qpos(JOINT_NAME)),
                       "goal": bool(env.check_success())})
        if not env.check_success():
            raise RuntimeError("The Panda action did not open the drawer.")
        # Release and retreat, then verify the drawer stays open without hand support.
        released_position = obs["robot0_eef_pos"].copy()
        move_to(released_position, -1., "Release", max_steps=20, hold=True)
        move_to(released_position + .10 * opening_direction + [0., 0., .12], -1., "Retreat")
        move_to(obs["robot0_eef_pos"].copy(), -1., "Verify", max_steps=30, hold=True)
        success = bool(env.check_success())
        gripper_released = not bool(env.env.check_contact(gripper, cabinet))
        if not success or not all(verification_goals) or not gripper_released or not grasp_confirmed:
            raise RuntimeError("Final goal, grasp, release or stability check failed.")
        validation.save_frame(validation.IMAGES / "panda_drawer_action_result.png", obs,
                              "Panda drawer action complete | goal=True")
        result = {"bddl": "custom_tasks/custom_test.bddl", "seed": args.seed,
                  "camera_size": args.size, "scene": scene, "initial_goal": initial_goal,
                  "initial_checks": initial_checks, "initial_drawer_joint_m": initial_joint,
                  "action": {"steps": step_count, "phases": phases,
                    "goal_after_robot_action": success,
                    "final_drawer_joint_m": float(env.sim.data.get_joint_qpos(JOINT_NAME)),
                    "grasp_confirmed": grasp_confirmed, "gripper_released": gripper_released,
                    "verification_steps": len(verification_goals),
                    "goal_true_throughout_verification": all(verification_goals),
                    "direct_object_state_changes_during_action": False,
                    "control_frequency_hz": 20, "video_frequency_hz": 10,
                    "video": str(video_path.relative_to(validation.ROOT))}}
        output = validation.IMAGES / "panda_drawer_action_result.json"
        output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2), flush=True)
        print("Saved:", output, flush=True)
    finally:
        if writer is not None:
            writer.release()
        env.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Stopped by user.", flush=True)
