import os
import cv2
import numpy as np

os.environ["MUJOCO_GL"] = "wgl"

from libero.libero.envs.env_wrapper import OffScreenRenderEnv


# --------------------------------------------------
# Custom BDDL 경로
# --------------------------------------------------

base_dir = os.path.dirname(os.path.abspath(__file__))

bddl_path = os.path.join(
    base_dir,
    "custom_tasks",
    "custom_test.bddl"
)


# --------------------------------------------------
# LIBERO 환경 생성
# --------------------------------------------------

env = OffScreenRenderEnv(
    bddl_file_name=bddl_path,
    camera_heights=512,
    camera_widths=512,
)


# --------------------------------------------------
# 7.1 초기 상태 생성 및 Goal Condition 확인
# --------------------------------------------------

obs = env.reset()

print("Environment reset success")

success = env.check_success()

print("Initial goal success:", success)


# --------------------------------------------------
# 7.2 Action Interface 동작 확인
# --------------------------------------------------

# Panda OSC_POSE action
# [dx, dy, dz, dRx, dRy, dRz, gripper]

action = np.zeros(7, dtype=np.float32)

for step in range(10):

    # zero action을 입력하고 제어 step 한 번 진행
    obs, reward, done, info = env.step(action)

    # 각 step 이후 goal condition 확인
    success = env.check_success()

    print(
        f"Step: {step:02d} | "
        f"Reward: {reward} | "
        f"Done: {done} | "
        f"Success: {success}"
    )


# --------------------------------------------------
# 7.3 BDDL Goal Condition 정상 동작 확인
# --------------------------------------------------

print("\n===== 7.3 Goal Condition Test =====")

drawer_region = "wooden_cabinet_1_middle_region"

# BDDL region과 연결된 MuJoCo joint 정보
drawer_site = env.env.object_sites_dict[drawer_region]

print("Drawer region:", drawer_region)
print("Drawer joints:", drawer_site.joints)

success_before = env.check_success()

print("Before opening drawer:", success_before)


# --------------------------------------------------
# 먼저 joint range의 high 방향으로 서랍 이동
# --------------------------------------------------

for joint_name in drawer_site.joints:

    joint_id = env.sim.model.joint_name2id(joint_name)

    joint_range = env.sim.model.jnt_range[joint_id]

    low = joint_range[0]
    high = joint_range[1]

    # joint limit에 완전히 붙이지 않고 90% 위치 사용
    target_qpos = low + 0.9 * (high - low)

    env.sim.data.set_joint_qpos(
        joint_name,
        target_qpos
    )

    print(
        f"{joint_name} -> "
        f"range={joint_range}, "
        f"target={target_qpos}"
    )


# 변경된 joint 상태를 MuJoCo에 반영
env.sim.forward()

success_after = env.check_success()

print("Goal after high-direction test:", success_after)


# --------------------------------------------------
# High 방향이 open 방향이 아니면 반대 방향 테스트
# --------------------------------------------------

if not success_after:

    print("High direction was not open. Trying opposite direction.")

    for joint_name in drawer_site.joints:

        joint_id = env.sim.model.joint_name2id(joint_name)

        joint_range = env.sim.model.jnt_range[joint_id]

        low = joint_range[0]
        high = joint_range[1]

        # 반대쪽 10% 위치
        target_qpos = low + 0.1 * (high - low)

        env.sim.data.set_joint_qpos(
            joint_name,
            target_qpos
        )

        print(
            f"{joint_name} -> "
            f"opposite target={target_qpos}"
        )

    env.sim.forward()

    success_after = env.check_success()


print("After opening drawer:", success_after)


if success_after:

    print("BDDL Goal Condition test SUCCESS")

else:

    print("BDDL Goal Condition test FAILED")


# --------------------------------------------------
# 실시간 Viewer
# --------------------------------------------------

print("LIBERO live viewer 시작")
print("종료: q / Q / ESC")


try:

    while True:

        # 7.3 이후에는 서랍 상태를 유지하며 viewer 확인
        # zero action으로 simulation만 진행
        action = np.zeros(7, dtype=np.float32)

        obs, reward, done, info = env.step(action)

        success = env.check_success()

        image = obs["agentview_image"]

        image = image[::-1]

        image = cv2.cvtColor(
            image,
            cv2.COLOR_RGB2BGR
        )

        cv2.putText(
            image,
            f"Success: {success}",
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2
        )

        cv2.imshow(
            "LIBERO Live - agentview",
            image
        )

        key = cv2.waitKey(20) & 0xFF

        if key in [ord("q"), ord("Q"), 27]:
            print("Viewer 종료")
            break


except KeyboardInterrupt:

    print("\nCtrl+C로 종료")


finally:

    env.close()
    cv2.destroyAllWindows()