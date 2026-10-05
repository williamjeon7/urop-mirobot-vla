#!/usr/bin/env python3
"""W5 세로 정렬 — 빈 탁상에서 Panda 집게를 내려 탁상에 닿는 높이를 잰다. (서버 .venv 전용)

    python -m tools.panda_touch_table

**왜** — 좌표 변환의 세로를 "시작 자세 ↔ 짝" 이 아니라 **"닿는 점 ↔ 닿는 점"** 으로 맞추려고 한다.
로봇 노트북은 Mirobot 집게 끝을 작업대에 대고 `?` 의 Z 를 읽는다. 여기서는 같은 일을 시뮬 Panda 로 한다.
닿는 상태끼리 짝지으면 두 집게의 생김새(Panda 손가락 길이, Mirobot `L`)가 저절로 들어간다.

    Mirobot 파지점 Z = Mirobot 닿는 점 Z + s × (Panda 파지점 z − Panda 닿는 점 z)

장면은 동료분이 만든 "책상과 Panda 만" 장면과 같다 (`docs/W5/custom_task_validation/test_panda_initial_pose.py`) —
탁상 1.0×1.2×0.05m, 윗면 0.90m, 로봇 베이스는 LIBERO 탁상과 같은 자리. 물체는 없다.

재는 법 — 집게를 수직(공구 축이 아래, Mirobot `A0 B0 C0` 와 같은 자세)으로 세우고 탁상 위 몇 군데로 간 뒤,
스텝마다 목표를 1mm 씩 낮춰 천천히 내린다. **집게 몸체와 탁상 충돌 형상 사이에 접촉이 처음 생기는 스텝**의
파지점 z(`robot0_eef_pos`)를 적는다. 집게를 연 채·닫은 채 둘 다.

남는 것 — data/calibration/<날짜>-<시각>--panda-touch.json
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from tools.libero_axis_probe import read_pose  # 환경 변수(MuJoCo 렌더러)도 여기서 정해진다

import numpy as np
from libero.libero import get_libero_path
from libero.libero.envs.arenas import TableArena
from libero.libero.envs.robots import MountedPanda  # noqa: F401 — robosuite 에 로봇을 등록한다
from robosuite.controllers import load_controller_config
from robosuite.environments.manipulation.single_arm_env import SingleArmEnv
from robosuite.models.tasks import ManipulationTask

from common.rotation import FRAME_F
from common.servo import pose_gap, servo_action

TABLE_FULL_SIZE = (1.0, 1.2, 0.05)
TABLE_OFFSET = (0.0, 0.0, 0.90)          # LIBERO 탁상과 같다 — 윗면 0.90m
TOP_DOWN = FRAME_F                       # 공구 축이 정확히 아래 (Mirobot A0 B0 C0 를 LIBERO 규약으로)
# 탁상 위 잴 자리 (탁상 좌표 = 월드 xy, m). 시작 근처와 Mirobot 이 닿는 영역(PIPELINE 4-4) 안쪽 몇 군데
POINTS_XY = [(-0.20, 0.00), (-0.10, 0.15), (-0.10, -0.15), (0.00, 0.00), (0.05, 0.10)]


class EmptyTableEnv(SingleArmEnv):
    """빈 탁상 + Panda. 동료분 `PandaInitialPoseEnv` 에서 카메라를 줄이고 접촉을 읽게만 했다."""

    def __init__(self):
        super().__init__(robots="MountedPanda",
                         controller_configs=load_controller_config(default_controller="OSC_POSE"),
                         initialization_noise=None, use_camera_obs=False, has_renderer=False,
                         has_offscreen_renderer=False, control_freq=20, horizon=100000)

    def _load_model(self):
        super()._load_model()
        robot = self.robots[0].robot_model
        robot.set_base_xpos(robot.base_xpos_offset["table"](TABLE_FULL_SIZE[0]))
        arena = TableArena(table_full_size=TABLE_FULL_SIZE, table_offset=TABLE_OFFSET,
                           table_friction=(0.6, 0.005, 0.0001),
                           xml=str(Path(get_libero_path("assets")) / "scenes" / "libero_tabletop_base_style.xml"),
                           floor_style="light-gray", wall_style="light-gray-plaster")
        arena.set_origin([0, 0, 0])
        self.model = ManipulationTask(mujoco_arena=arena, mujoco_robots=[robot], mujoco_objects=[])

    def reward(self, action=None):
        return 0.0

    def _check_success(self):
        return False


def table_contacts(sim) -> list[tuple[str, float]]:
    """탁상 충돌 형상과 닿은 로봇 형상 (이름, 침투 깊이 m). 양수 깊이는 겹침이다."""
    m, out = sim.model, []
    table = m.geom_name2id("table_collision")
    for i in range(sim.data.ncon):
        c = sim.data.contact[i]
        if table in (c.geom1, c.geom2):
            other = c.geom2 if c.geom1 == table else c.geom1
            name = m.geom_id2name(other) or f"geom{other}"
            body = m.body_id2name(m.geom_bodyid[other])
            if body.startswith(("gripper0", "robot0")):
                out.append((name, -c.dist))
    return out


def go_to(env, obs, target, quat, gripper, max_steps=400, tol_mm=0.5):
    """목표 파지점·자세로 가서 선다 (libero_follow 와 같은 수렴 루프)."""
    for _ in range(max_steps):
        p, q = read_pose(obs)
        obs, *_ = env.step(servo_action(p, q, target, quat, gripper))
        gp, gr = pose_gap(*read_pose(obs), target, quat)
        if gp * 1000 < tol_mm and gr < 0.2:
            break
    return obs


def touch_down(env, obs, gripper, step_mm=1.0, max_steps=600):
    """수직으로 내려가다 탁상과 처음 닿는 스텝의 파지점·접촉을 돌려준다."""
    for k in range(1, max_steps + 1):
        p, q = read_pose(obs)
        target = (p[0], p[1], p[2] - step_mm / 1000)
        obs, *_ = env.step(servo_action(p, q, target, TOP_DOWN, gripper))
        hit = table_contacts(env.sim)
        if hit:
            p, q = read_pose(obs)
            return obs, {"step": k, "grip_z": float(p[2]), "grip_xy": [float(p[0]), float(p[1])],
                         "tilt_deg": float(pose_gap(p, q, p, TOP_DOWN)[1]),
                         "contacts": [{"geom": n, "depth_mm": d * 1000} for n, d in hit]}
    raise SystemExit("탁상에 닿지 않았다")


def main() -> None:
    env = EmptyTableEnv()
    obs = env.reset()
    base = env.sim.data.body_xpos[env.sim.model.body_name2id("robot0_base")]
    start_grip, start_q = read_pose(obs)
    print(f"로봇 베이스 {np.round(base, 4)}  시작 파지점 {np.round(start_grip, 4)}  (탁상 윗면 {TABLE_OFFSET[2]:.3f})\n")
    print(f"{'자리 (x, y)':>14} | {'집게':4} | {'스텝':>4} | {'닿는 파지점 z':>12} | {'탁상 위':>8} | {'기울기':>6} | 처음 닿은 형상 (침투)")

    results = []
    for gripper, label in ((-1.0, "연"), (1.0, "닫은")):
        for x, y in POINTS_XY:
            obs = env.reset()
            # 닫은 채로 재려면 먼저 닫아 둔다
            for _ in range(15 if gripper > 0 else 0):
                obs, *_ = env.step([0, 0, 0, 0, 0, 0, gripper])
            obs = go_to(env, obs, (x, y, TABLE_OFFSET[2] + 0.12), TOP_DOWN, gripper)
            obs, hit = touch_down(env, obs, gripper)
            hit.update({"point_xy": [x, y], "gripper": label, "above_table_mm": (hit["grip_z"] - TABLE_OFFSET[2]) * 1000})
            results.append(hit)
            first = ", ".join(f"{c['geom']} ({c['depth_mm']:.2f}mm)" for c in hit["contacts"])
            print(f"({x:+.2f}, {y:+.2f}) | {label:4} | {hit['step']:4d} | {hit['grip_z']:10.4f}m | "
                  f"{hit['above_table_mm']:6.2f}mm | {hit['tilt_deg']:5.2f}° | {first}")

    zs = {lab: [r["above_table_mm"] for r in results if r["gripper"] == lab] for lab in ("연", "닫은")}
    print()
    for lab, v in zs.items():
        print(f"집게 {lab} 채 — 탁상 위 {np.mean(v):.2f}mm (최소 {min(v):.2f}, 최대 {max(v):.2f}, 폭 {max(v) - min(v):.2f}mm)")

    out_dir = Path("data") / "calibration"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{time.strftime('%Y_%m_%d-%H_%M_%S')}--panda-touch.json"
    out.write_text(json.dumps({"table_top_z": TABLE_OFFSET[2], "robot_base": [float(v) for v in base],
                               "start_grip": [float(v) for v in start_grip], "orientation": "top-down (FRAME_F)",
                               "step_mm": 1.0, "results": results}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"saved {out}")
    env.close()


if __name__ == "__main__":
    main()
