import os

# robosuite / LIBERO import 전에 Windows 렌더링 설정
os.environ["MUJOCO_GL"] = "wgl"

from libero.libero.envs.env_wrapper import OffScreenRenderEnv


def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    bddl_path = os.path.join(base_dir, "custom_tasks", "custom_test.bddl")

    env = OffScreenRenderEnv(
        bddl_file_name=bddl_path,
        camera_heights=512,
        camera_widths=512,
    )

    try:
        obs = env.reset()

        # Panda End-Effector 현재 위치
        eef_pos = obs["robot0_eef_pos"]

        print("\n===== Panda / Drawer Info =====")
        print("EEF position:", eef_pos)
        print("Initial goal success:", env.check_success())

        # 가운데 서랍 joint
        joint_name = "wooden_cabinet_1_middle_level"
        joint_id = env.sim.model.joint_name2id(joint_name)

        # joint range와 local axis
        joint_range = env.sim.model.jnt_range[joint_id]
        joint_axis_local = env.sim.model.jnt_axis[joint_id]

        # 해당 joint가 연결된 body의 회전 행렬
        body_id = env.sim.model.jnt_bodyid[joint_id]
        body_rotation = env.sim.data.body_xmat[body_id].reshape(3, 3)

        # joint axis를 world 좌표계로 변환
        joint_axis_world = body_rotation @ joint_axis_local

        print("Drawer joint:", joint_name)
        print("Drawer joint range:", joint_range)
        print("Drawer joint local axis:", joint_axis_local)
        print("Drawer joint world axis:", joint_axis_world)

        # 서랍 손잡이와 관련된 site 이름과 위치 확인
        print("\n===== Cabinet / Handle Sites =====")

        for i in range(env.sim.model.nsite):
            name = env.sim.model.site_id2name(i)
            if name is not None:
                lower_name = name.lower()
                if "cabinet" in lower_name or "handle" in lower_name:
                    print("SITE:", name, "POSITION:", env.sim.data.site_xpos[i])

        # site 출력에서 손잡이를 찾기 어려울 때 참고할 geom 정보
        print("\n===== Cabinet / Handle Geoms =====")

        for i in range(env.sim.model.ngeom):
            name = env.sim.model.geom_id2name(i)
            if name is not None:
                lower_name = name.lower()
                if "cabinet" in lower_name or "handle" in lower_name:
                    print("GEOM:", name, "POSITION:", env.sim.data.geom_xpos[i])

    finally:
        env.close()


if __name__ == "__main__":
    main()
