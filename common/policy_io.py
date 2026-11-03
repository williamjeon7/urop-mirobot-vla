"""정책 action → Mirobot 목표 자세 (W10, docs/W10/POLICY_RUN.md).

학습 데이터를 만든 변환을 거꾸로 돌린다. 실행 루프와 오프라인 검사가 이 계산을 같이 쓴다.

* `apply_action` — OSC_POSE action 7칸이 뜻하는 목표 자세. robosuite 컨트롤러와 같은 식이다
  (`goal = 현재 + action × 스케일`, 회전은 월드 프레임 왼쪽 곱 — `common/servo.py`, `common/rotation.py`).
  `servo_action` 의 역: 자르기(크기 1 초과)가 없으면 `apply_action(현재, servo_action(현재, 목표)) == 목표`
* `libero_to_mirobot_pose` — LIBERO 파지점 자세 → Mirobot 플랜지 `X Y Z`(mm) · `A B C`(도).
  `common/proprio.py` `mirobot_to_libero_pose` 의 역이고, `tools/poses_to_gcode.py` `convert` 와 같은 계산이다
* 기준(시작 자세 짝·배율·공구)은 녹화 때 쓴 G-code 머리말과 손 좌표 기록 meta 에서 온다
  (`common.proprio.settings_from_gcode`, `reference.jsonl`). 세 색 seed 2 기준 파일은 이 값이 모두 같다

표준 라이브러리만 쓴다 (`common/` 규약).
"""

from __future__ import annotations

from common.proprio import align_sign
from common.rotation import (
    Quat,
    axis_angle_to_quat,
    libero_to_mirobot_quat,
    quat_mul,
    quat_normalize,
    quat_to_euler_xyz_deg,
)
from common.servo import POS_SCALE_M, ROT_SCALE_RAD
from common.workspace import Vec3, grip_to_flange, libero_to_mirobot_flange_mm


def apply_action(pos_m, q_wxyz: Quat, action) -> tuple[Vec3, Quat]:
    """현재 파지점 자세(LIBERO, m · wxyz) + OSC_POSE action → 컨트롤러가 향하는 목표 자세.

    action[6](그리퍼)은 쓰지 않는다. 부호는 현재 자세 쪽으로 맞춘다.
    """
    pos = tuple(c + a * POS_SCALE_M for c, a in zip(pos_m, action[:3]))
    dq = axis_angle_to_quat(tuple(a * ROT_SCALE_RAD for a in action[3:6]))
    return pos, align_sign(quat_normalize(quat_mul(dq, q_wxyz)), q_wxyz)


def libero_to_mirobot_pose(grip_pos_m, q_wxyz: Quat, ref_flange_m, ref_q_wxyz: Quat,
                           settings: dict) -> tuple[Vec3, Vec3]:
    """LIBERO 파지점 위치(m)·자세(wxyz) → Mirobot 플랜지 X Y Z(mm), A B C(도)."""
    if settings["orientation"] != "absolute":
        raise NotImplementedError("relative orientation mapping is not used by W9/W10 recordings")
    q_mirobot = libero_to_mirobot_quat(q_wxyz)
    flange = grip_to_flange(grip_pos_m, q_wxyz)
    xyz = libero_to_mirobot_flange_mm(flange, q_wxyz, q_mirobot, ref_flange_m, ref_q_wxyz, settings["point"],
                                      settings["scale"], settings["ref_mirobot_mm"], settings["tool_mm"])
    return xyz, quat_to_euler_xyz_deg(q_mirobot)


def gripper_s(action, open_s: float = 40.0, closed_s: float = 60.0) -> float:
    """action[6] → Mirobot 집게 `M4 S..` 값. 학습 라벨은 −1 열림 / +1 닫힘 (prepare.gripper_track)."""
    return closed_s if action[6] >= 0.0 else open_s
