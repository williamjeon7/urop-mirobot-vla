"""목표 자세로 가는 액션 계산 — LIBERO(OSC_POSE) 용.

LIBERO 액션은 **변화량**이라 "여기로 가라" 가 없다. 목표를 고정해 두고 매 스텝
`(목표 − 현재)` 로 액션을 다시 계산하면 수렴한다 (`docs/W3/CONTROL.md` 3절 ③ — 9스텝에 1mm 안).

    액션 = (목표 − 현재) / 한 스텝 목표 오프셋      위치 0.05m, 회전 0.5rad

이러면 컨트롤러의 목표(`goal = 현재 + 액션 × 스케일`)가 **정확히 우리 목표**가 된다.
`1` 을 넘으면 **방향을 유지한 채 크기만** 줄인다 — robosuite 는 성분마다 자르기 때문에
(`base_controller.py:120`) 그대로 두면 여러 축이 섞일 때 방향이 틀어진다.

표준 라이브러리만 쓴다 (`common/` 규약). 회전 계산은 `common/rotation.py`.
"""

from __future__ import annotations

import math

from common.rotation import Quat, quat_error_axis_angle

# robosuite `controllers/config/osc_pose.json` 의 output_max — 액션 1.0 이 뜻하는 크기
POS_SCALE_M = 0.05
ROT_SCALE_RAD = 0.5
GRIPPER_OPEN = -1.0  # libero_utils.py:42

DEFAULT_POS_TOL_M = 0.002  # 2mm
DEFAULT_ROT_TOL_DEG = 1.0


def fit_to_unit(vec) -> tuple[float, ...]:
    """가장 큰 성분이 1 을 넘으면 **전체를 같은 비율로** 줄인다. 방향은 그대로."""
    biggest = max(abs(v) for v in vec)
    return tuple(vec) if biggest <= 1.0 else tuple(v / biggest for v in vec)


def pose_error(p_current, q_current: Quat, p_target, q_target: Quat):
    """(위치 오차 3개(m), 회전 오차 3개(rad, 월드 axis-angle)). 회전 부호는 함수 안에서 맞춘다."""
    return ([t - c for c, t in zip(p_current, p_target)],
            list(quat_error_axis_angle(q_current, q_target)))


def servo_action(p_current, q_current: Quat, p_target, q_target: Quat,
                 gripper: float = GRIPPER_OPEN) -> list[float]:
    """목표 자세로 가는 OSC_POSE 액션 7칸. 위치와 회전은 단위가 다르므로 **따로** 줄인다."""
    d_pos, d_rot = pose_error(p_current, q_current, p_target, q_target)
    a_pos = fit_to_unit([v / POS_SCALE_M for v in d_pos])
    a_rot = fit_to_unit([v / ROT_SCALE_RAD for v in d_rot])
    return list(a_pos) + list(a_rot) + [gripper]


def pose_gap(p_current, q_current: Quat, p_target, q_target: Quat) -> tuple[float, float]:
    """(위치 오차 m, 자세 오차 도). 도착 판정과 기록에 쓴다."""
    d_pos, d_rot = pose_error(p_current, q_current, p_target, q_target)
    return math.sqrt(sum(v * v for v in d_pos)), math.degrees(math.sqrt(sum(v * v for v in d_rot)))


def reached(p_current, q_current: Quat, p_target, q_target: Quat,
            pos_tol_m: float = DEFAULT_POS_TOL_M, rot_tol_deg: float = DEFAULT_ROT_TOL_DEG) -> bool:
    """목표에 닿았나. **멈췄는지는 따로 본다** — 오차가 작아도 지나가는 중일 수 있다."""
    gap_pos, gap_rot = pose_gap(p_current, q_current, p_target, q_target)
    return gap_pos <= pos_tol_m and gap_rot <= rot_tol_deg
