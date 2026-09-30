import argparse
import os

os.environ["MUJOCO_GL"] = "wgl"

import cv2
import numpy as np
from scipy.spatial.transform import Rotation

from libero.libero.envs.env_wrapper import OffScreenRenderEnv


JOINT_NAME = "wooden_cabinet_1_middle_level"
HANDLE_GEOM = "wooden_cabinet_1_g29"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--headless", action="store_true", help="OpenCV 창 없이 실행")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    base_dir = os.path.dirname(os.path.abspath(__file__))
    env = OffScreenRenderEnv(
        bddl_file_name=os.path.join(base_dir, "custom_tasks", "custom_test.bddl"),
        camera_heights=128 if args.headless else 512,
        camera_widths=128 if args.headless else 512,
    )

    try:
        env.seed(args.seed)
        obs = env.reset()
        print("Initial goal success:", env.check_success())
        if env.check_success():
            raise RuntimeError("서랍이 닫힌 초기 상태에서 시작해야 합니다.")

        joint_id = env.sim.model.joint_name2id(JOINT_NAME)
        body_id = env.sim.model.jnt_bodyid[joint_id]
        rotation = env.sim.data.body_xmat[body_id].reshape(3, 3)
        axis_world = rotation @ env.sim.model.jnt_axis[joint_id]
        # 이 task는 joint qpos의 음수 방향으로 서랍이 열린다.
        opening_direction = -axis_world / np.linalg.norm(axis_world)

        handle_id = env.sim.model.geom_name2id(HANDLE_GEOM)
        handle_pos = env.sim.data.geom_xpos[handle_id].copy()
        print("Handle position:", handle_pos)
        print("Opening direction:", opening_direction)

        # 손가락은 손잡이 위아래로 닫히고, 손끝은 서랍을 향한다.
        tool_z = -opening_direction
        tool_x = np.array([0.0, 0.0, 1.0])
        tool_y = np.cross(tool_z, tool_x)
        target_rotation = np.column_stack((tool_x, tool_y, tool_z))

        step_count = 0
        eef_site_id = env.env.robots[0].eef_site_id

        def eef_rotation():
            # obs의 eef_quat은 hand body 기준이며 grip_site와 회전 offset이 있다.
            return env.sim.data.site_xmat[eef_site_id].reshape(3, 3).copy()

        def step_toward(target, gripper, phase):
            nonlocal obs, step_count
            # OSC_POSE는 정규화된 delta action을 받는다.
            # 기본 output_max: 위치 0.05 m, 회전 0.5 rad.
            current_rotation = eef_rotation()
            rotation_error = Rotation.from_matrix(
                target_rotation @ current_rotation.T
            ).as_rotvec()
            action = np.zeros(7, dtype=np.float32)
            action[:3] = np.clip((target - obs["robot0_eef_pos"]) / 0.05, -0.4, 0.4)
            action[3:6] = np.clip(rotation_error / 0.5, -0.4, 0.4)
            action[6] = gripper
            obs, reward, done, info = env.step(action)
            step_count += 1
            if step_count % 25 == 0:
                print(
                    f"{phase} | Step: {step_count} | "
                    f"Joint: {env.sim.data.get_joint_qpos(JOINT_NAME):.4f} | "
                    f"Success: {env.check_success()}"
                )
            if not args.headless:
                frame = cv2.cvtColor(obs["agentview_image"][::-1], cv2.COLOR_RGB2BGR)
                cv2.putText(
                    frame, f"{phase} | Success: {env.check_success()}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2,
                )
                cv2.imshow("Panda Drawer Action", frame)
                if cv2.waitKey(1) & 0xFF in (ord("q"), ord("Q"), 27):
                    raise KeyboardInterrupt

        def move_to(target, gripper, phase, max_steps=200):
            for _ in range(max_steps):
                step_toward(target, gripper, phase)
                error = np.linalg.norm(target - obs["robot0_eef_pos"])
                rotation_error = Rotation.from_matrix(
                    target_rotation @ eef_rotation().T
                ).magnitude()
                if error < 0.015 and rotation_error < 0.12:
                    return
            raise RuntimeError(
                f"{phase}: 목표 위치에 도달하지 못했습니다. "
                f"EEF error={error:.4f} m, rotation error={rotation_error:.4f} rad"
            )

        # 1. 손잡이 앞쪽 위에서 자세를 맞춘 뒤 서랍에 접근한다.
        pregrasp = handle_pos + 0.10 * opening_direction
        above = pregrasp + np.array([0.0, 0.0, 0.15])
        move_to(above, -1.0, "Above handle")
        move_to(pregrasp, -1.0, "Before handle")

        # 2. 손잡이 중앙에 접근한 뒤 gripper를 닫는다.
        grasp = handle_pos.copy()
        move_to(grasp, -1.0, "Approach handle")
        for _ in range(30):
            step_toward(grasp, 1.0, "Close gripper")

        # 3. 손잡이를 잡은 상태로 서랍의 opening 방향으로 당긴다.
        start = obs["robot0_eef_pos"].copy()
        for distance in np.linspace(0.0, 0.18, 180):
            step_toward(start + distance * opening_direction, 1.0, "Pull drawer")
            if env.check_success():
                break

        success = env.check_success()
        print("Final drawer joint:", env.sim.data.get_joint_qpos(JOINT_NAME))
        print("Final goal success:", success)
        output_path = os.path.join(base_dir, "images", "panda_drawer_action_result.png")
        frame = cv2.cvtColor(obs["agentview_image"][::-1], cv2.COLOR_RGB2BGR)
        cv2.putText(
            frame, f"Success: {success}", (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2,
        )
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        if not cv2.imwrite(output_path, frame):
            raise RuntimeError("결과 이미지 저장 실패")
        print("Saved:", output_path)
        if not success:
            raise RuntimeError("서랍 열기에 실패했습니다. 접근 위치와 grasp 상태를 확인하세요.")

    finally:
        env.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("사용자가 실행을 종료했습니다.")
